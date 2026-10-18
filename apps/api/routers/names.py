import asyncio
import random

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from database import User
from deps import get_current_user, user_storage_token
from services import name_gen_jobs
from services.name_generator import (
    MAX_STACK_LAYERS,
    PREVIEW_LIMIT,
    NameGenError,
    generate_names,
    merge_names,
    names_preview,
)
from services.user_store import (
    clear_stack_layers,
    count_names,
    names_lock,
    read_names,
    read_stack_layers,
    stack_count,
    write_names,
    write_stack_layers,
)

router = APIRouter()
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class NamesBody(BaseModel):
    names: str = ""
    append: bool = False


class GenerateBody(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    include_verbs: bool = True
    append: bool = False


def _parse_manual_names(raw: str) -> list[str]:
    return [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _count_response(names: list[str], token: str) -> dict:
    preview = names_preview(names, stack_count=stack_count(token))
    return {
        "count": preview["count"],
        "limited": preview["is_large"],
        "stack_count": preview["stack_count"],
        "stack_limit": preview["stack_limit"],
    }


def _assert_can_stack(token: str, *, append: bool, existing_count: int | None = None) -> None:
    if not append:
        return
    layers = read_stack_layers(token)
    depth = len(layers)
    if depth == 0:
        prior = count_names(token) if existing_count is None else existing_count
        if prior > 0:
            depth = 1
    if depth >= MAX_STACK_LAYERS:
        raise NameGenError(
            f"Stack limit reached ({MAX_STACK_LAYERS} lists). Clear the list or turn stack off."
        )


def _record_stack_layer(
    token: str,
    *,
    append: bool,
    layer_type: str,
    added: int,
    prior_count: int = 0,
) -> int:
    if not append:
        layers = [{"type": layer_type, "count": added}]
    else:
        layers = read_stack_layers(token)
        if not layers and prior_count > 0:
            layers = [{"type": "existing", "count": prior_count}]
        if len(layers) >= MAX_STACK_LAYERS:
            raise NameGenError(
                f"Stack limit reached ({MAX_STACK_LAYERS} lists). Clear the list or turn stack off."
            )
        layers.append({"type": layer_type, "count": added})
    write_stack_layers(token, layers)
    return len(layers)


@router.get("/names")
async def get_names(user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    names = await asyncio.to_thread(read_names, token)
    return names_preview(names, stack_count=stack_count(token))


@router.get("/names/count")
async def get_names_count(user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    total = await asyncio.to_thread(count_names, token)
    layers = await asyncio.to_thread(stack_count, token)
    return {
        "count": total,
        "is_large": total > PREVIEW_LIMIT,
        "stack_count": layers,
        "stack_limit": MAX_STACK_LAYERS,
    }


@router.post("/names")
async def set_names(body: NamesBody, user: User = Depends(get_current_user)):
    token = user_storage_token(user)

    if not body.names.strip():
        if not body.append:
            await asyncio.to_thread(write_names, token, [])
            await asyncio.to_thread(clear_stack_layers, token)
        names = await asyncio.to_thread(read_names, token)
        return _count_response(names, token)

    lines = _parse_manual_names(body.names)
    existing = await asyncio.to_thread(read_names, token)
    try:
        await asyncio.to_thread(
            _assert_can_stack,
            token,
            append=body.append,
            existing_count=len(existing),
        )
    except NameGenError as exc:
        raise HTTPException(400, exc.detail) from exc
    merged = merge_names(existing, lines, append=body.append)
    await asyncio.to_thread(write_names, token, merged)
    await asyncio.to_thread(
        _record_stack_layer,
        token,
        append=body.append,
        layer_type="manual",
        added=len(lines),
        prior_count=len(existing),
    )
    return _count_response(merged, token)


@router.post("/names/shuffle")
async def shuffle_names(user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    names = await asyncio.to_thread(read_names, token)
    if not names:
        raise HTTPException(400, "No names loaded")
    shuffled = list(names)
    random.shuffle(shuffled)
    await asyncio.to_thread(write_names, token, shuffled)
    return {"count": len(shuffled), "action": "shuffle", "stack_count": stack_count(token)}


@router.post("/names/reverse")
async def reverse_names(user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    names = await asyncio.to_thread(read_names, token)
    if not names:
        raise HTTPException(400, "No names loaded")
    reversed_names = list(reversed(names))
    await asyncio.to_thread(write_names, token, reversed_names)
    return {
        "count": len(reversed_names),
        "action": "reverse",
        "stack_count": stack_count(token),
    }


@router.get("/names/job/{job_id}")
async def names_job_status(job_id: str, user: User = Depends(get_current_user)):
    token = user_storage_token(user)
    job = name_gen_jobs.get_job(job_id, token)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/names/generate")
async def generate_name_list(body: GenerateBody, user: User = Depends(get_current_user)):
    token = user_storage_token(user)

    def _run() -> dict:
        # Generate outside the lock (4C can take a while), then merge under lock
        # so stacked jobs never clobber each other with a stale snapshot.
        _assert_can_stack(token, append=body.append)
        combos = generate_names(body.type, include_verbs=body.include_verbs)
        with names_lock(token):
            existing = read_names(token)
            _assert_can_stack(token, append=body.append, existing_count=len(existing))
            merged = merge_names(existing, combos, append=body.append)
            write_names(token, merged)
            stack_depth = _record_stack_layer(
                token,
                append=body.append,
                layer_type=body.type.strip().upper(),
                added=len(combos),
                prior_count=len(existing),
            )
        payload = _count_response(merged, token)
        payload["stack_count"] = stack_depth
        payload["added"] = len(combos)
        payload["type"] = body.type.strip().upper()
        return payload

    if name_gen_jobs.is_heavy_generator(body.type):
        try:
            _assert_can_stack(token, append=body.append)
            job_id = name_gen_jobs.create_job(body.type, token)
        except NameGenError as exc:
            raise HTTPException(400, exc.detail) from exc
        except RuntimeError as exc:
            raise HTTPException(429, str(exc)) from exc
        asyncio.create_task(name_gen_jobs.run_job(job_id, _run))
        return {"job_id": job_id, "status": "pending", "async": True}

    try:
        return await asyncio.to_thread(_run)
    except NameGenError as exc:
        raise HTTPException(400, exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/upload/names")
async def upload_names(
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    append: str = Form(default="false"),
):
    token = user_storage_token(user)
    is_append = str(append).lower() == "true"
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 2 MB)")
    lines = [
        line.strip()
        for line in content.decode("utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    existing = await asyncio.to_thread(read_names, token)
    try:
        await asyncio.to_thread(
            _assert_can_stack,
            token,
            append=is_append,
            existing_count=len(existing),
        )
    except NameGenError as exc:
        raise HTTPException(400, exc.detail) from exc
    merged = merge_names(existing, lines, append=is_append)
    await asyncio.to_thread(write_names, token, merged)
    await asyncio.to_thread(
        _record_stack_layer,
        token,
        append=is_append,
        layer_type="import",
        added=len(lines),
        prior_count=len(existing),
    )
    return _count_response(merged, token)
