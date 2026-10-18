from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routers import admin, auth, billing, health, names, proxies, sniper
from routers import settings as settings_router
from services.local_redis import LocalRedis
from services.sniper_janitor import SniperJanitor
from services.sniper_node_runner import SniperNodeRunner

try:
    import redis.asyncio as aioredis
except ModuleNotFoundError:  # Local memory mode can run without redis-py.
    aioredis = None


def _build_redis():
    if settings.redis_url.startswith("memory://"):
        return LocalRedis()
    if aioredis is None:
        raise RuntimeError(
            "redis package is not installed. Use REDIS_URL=memory://local for local dev "
            "or install the dependencies from requirements.txt."
        )
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only the control API owns schema migrations — sniper replicas must not
    # stampede Neon with create_all() on every fleet scale-up.
    if (settings.api_mode or "control").strip().lower() != "sniper":
        await init_db()
    app.state.redis = _build_redis()
    try:
        await app.state.redis.ping()
    except Exception:
        pass

    app.state.sniper_node_runner = None
    app.state.sniper_janitor = None
    if settings.api_mode == "sniper":
        pool = settings.sniper_vps_pool
        if pool not in ("vps1", "vps2", "vps3"):
            raise RuntimeError(f"Invalid SNIPER_VPS_POOL: {pool}")
        runner = SniperNodeRunner(app.state.redis, pool)  # type: ignore[arg-type]
        await runner.start()
        app.state.sniper_node_runner = runner
    else:
        # Control plane: periodically kill orphan / expired-trial sessions.
        janitor = SniperJanitor(app.state.redis)
        await janitor.start()
        app.state.sniper_janitor = janitor

    yield

    if app.state.sniper_janitor is not None:
        await app.state.sniper_janitor.shutdown()
    if app.state.sniper_node_runner is not None:
        await app.state.sniper_node_runner.shutdown()
    await app.state.redis.aclose()


app = FastAPI(title="UserSniper API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_origins=[o for o in settings.cors_origin_list if not o.startswith("https://*.")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(names.router, prefix="/api", tags=["names"])
app.include_router(proxies.router, prefix="/api", tags=["proxies"])
app.include_router(settings_router.router, prefix="/api", tags=["settings"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(sniper.router, prefix="/api/sniper", tags=["sniper"])
