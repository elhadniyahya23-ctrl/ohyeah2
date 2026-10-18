from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("sslmode", None)
        params.pop("channel_binding", None)
        query = urlencode({k: v[0] for k, v in params.items()})
        url = urlunparse(parsed._replace(query=query))
    return url


def _host_requires_ssl(database_url: str) -> bool:
    host = (urlparse(database_url).hostname or "").lower()
    return host not in {"", "localhost", "127.0.0.1", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://localhost:5432/usersniper"
    database_ssl: bool | None = None

    cors_origins: str = "http://localhost:3000"
    redis_url: str = "redis://localhost:6379/0"
    user_data_dir: str = "/var/lib/usersniper/data"
    turbo_workers: int = 160
    # Local development guardrail: keep the dashboard/API usable while blocking
    # live outbound sniping jobs and webhook test calls.
    local_safe_mode: bool = False

    # control = public API gateway; sniper = dedicated turbo process (one job at a time)
    api_mode: str = "control"
    sniper_vps_pool: str = "vps1"
    sniper_node_id: str = ""
    sniper_node_max_jobs: int = 1
    # When true, control API enqueues jobs for sniper-node processes (production).
    sniper_distributed: bool = True
    # Soft documentation of Discord fleet size (deploy scales sniper-node to this).
    sniper_discord_max_concurrent: int = 12

    # Billing (manual PayPal F&F + crypto — overridable via env)
    paypal_email: str = "ovapaf@gmail.com"
    crypto_btc_address: str = "bc1qzftnp5pft7tmxmm79ra5hq6qeala74h743v5q7"
    crypto_eth_address: str = "0x05CB9bE55693C34d8e53920748B607122FE5ae88"
    crypto_ltc_address: str = "LNPrm5HV2TPZuqQKj7qUyA2sfDtPBizZCq"
    crypto_usdt_address: str = "0x05CB9bE55693C34d8e53920748B607122FE5ae88"
    # When true, verified crypto payments auto-activate the plan (PayPal stays manual)
    billing_auto_activate: bool = False
    crypto_auto_activate: bool = True
    # Newline- or comma-separated proxy lines for Free Trial sniping (shared pool)
    # Free Trial shared pool (DataImpulse) — no country pin so exits diversify.
    trial_proxy_lines: str = ""
    # Comma-separated local source IPs for datacenter direct mode (no proxies).
    # Multi-IP VPS spreads Discord checks across its own addresses.
    sniper_source_ips: str = ""
    # Comma-separated owner session tokens with admin access (was hardcoded).
    admin_owner_tokens: str = ""

    @property
    def async_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ssl_required(self) -> bool:
        if self.database_ssl is not None:
            return self.database_ssl
        return _host_requires_ssl(self.database_url)


settings = Settings()
