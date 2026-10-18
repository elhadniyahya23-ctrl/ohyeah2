from __future__ import annotations

import re
import threading
from pathlib import Path

from config import settings


def _require_token(token: str) -> str:
    safe = "".join(c for c in token if c.isalnum() or c in "-_")
    if not safe:
        raise ValueError("Invalid user storage token")
    return safe


def user_dir(token: str) -> Path:
    safe = _require_token(token)
    path = Path(settings.user_data_dir) / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def names_file(token: str) -> Path:
    return user_dir(token) / "names_to_check.txt"


def proxies_file(token: str) -> Path:
    return user_dir(token) / "proxies.txt"


def read_names(token: str) -> list[str]:
    path = names_file(token)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def count_names(token: str) -> int:
    path = names_file(token)
    if not path.is_file():
        return 0
    total = 0
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                total += 1
    return total


def write_names(token: str, names: list[str]) -> None:
    names_file(token).write_text("\n".join(names), encoding="utf-8")


_name_locks: dict[str, threading.Lock] = {}
_name_locks_guard = threading.Lock()


def names_lock(token: str) -> threading.Lock:
    """Serialize name-list read/merge/write per user (stack-safe)."""
    with _name_locks_guard:
        lock = _name_locks.get(token)
        if lock is None:
            lock = threading.Lock()
            _name_locks[token] = lock
        return lock


def names_stack_file(token: str) -> Path:
    return user_dir(token) / "names_stack.json"


def read_stack_layers(token: str) -> list[dict]:
    import json

    path = names_stack_file(token)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    layers = data.get("layers") if isinstance(data, dict) else None
    if not isinstance(layers, list):
        return []
    out: list[dict] = []
    for layer in layers:
        if isinstance(layer, dict) and layer.get("type"):
            out.append(
                {
                    "type": str(layer["type"])[:32],
                    "count": int(layer.get("count") or 0),
                }
            )
    return out


def write_stack_layers(token: str, layers: list[dict]) -> None:
    import json

    names_stack_file(token).write_text(
        json.dumps({"layers": layers}, indent=2),
        encoding="utf-8",
    )


def clear_stack_layers(token: str) -> None:
    path = names_stack_file(token)
    if path.is_file():
        path.unlink()


def stack_count(token: str) -> int:
    return len(read_stack_layers(token))


_PROXY_TOKEN_RE = re.compile(
    r"(?:"
    r"https?://[^\s,;]+"
    r"|"
    r"[^\s,;/@]+@[a-z0-9._\[\]-]+:\d{2,5}"  # user:pass@host:port (no scheme)
    r"|"
    r"[a-z0-9._\[\]-]+:\d{2,5}:[^\s,;]+"  # host:port:user:pass...
    r")",
    re.IGNORECASE,
)


def _split_glued_proxy_line(line: str) -> list[str]:
    """Split accidentally concatenated / space-separated proxy pastes."""
    raw = line.strip()
    if not raw:
        return []

    # Comma / semicolon separated lists from dashboards.
    chunks = [c.strip() for c in re.split(r"[,;]+", raw) if c.strip()]
    out: list[str] = []
    for chunk in chunks:
        # Break before a mid-string http(s):// (common copy/paste glue).
        pieces = re.split(r"(?=(?:https?://))", chunk)
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            piece_parts = [
                p.strip()
                for p in re.split(r"(?<=[\w\-])(?=https?://)", piece)
                if p.strip()
            ]
            for part in piece_parts or [piece]:
                tokens = _PROXY_TOKEN_RE.findall(part)
                # 2+ proxy-looking tokens on one line (space / glue separated).
                if len(tokens) >= 2:
                    out.extend(t.strip() for t in tokens if t.strip())
                else:
                    out.append(part)
    return out or [raw]


def normalize_proxy_lines(lines: list[str]) -> list[str]:
    """Dedupe, split glued pastes, and drop lines that do not parse as proxies."""
    return normalize_proxy_lines_detailed(lines)["proxies"]


def normalize_proxy_lines_detailed(lines: list[str]) -> dict:
    """Split glued pastes and drop unparseable lines. Keep duplicates for the UI list.

    Runtime ProxyRotator still collapses identical lines so worker budget / perf
    are not multiplied by copy-paste spam.
    """
    from sniper.proxy import ProxyConfig

    out: list[str] = []
    seen: set[str] = set()
    invalid = 0
    duplicates = 0
    for raw in lines:
        pieces = _split_glued_proxy_line(raw)
        if not pieces:
            continue
        for line in pieces:
            if not line or line.startswith("#"):
                continue
            cfg = ProxyConfig.from_line(line)
            if cfg is None:
                invalid += 1
                continue
            compact = f"{cfg.host}:{cfg.port}:{cfg.user}:{cfg.password}"
            if compact in seen:
                duplicates += 1
                continue
            seen.add(compact)
            out.append(compact)
    return {
        "proxies": out,
        "duplicates": duplicates,
        "invalid": invalid,
        "input_count": invalid + duplicates + len(out),
    }


def read_proxies(token: str) -> list[str]:
    path = proxies_file(token)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return normalize_proxy_lines(lines)


def write_proxies(token: str, proxies: list[str]) -> None:
    proxies_file(token).write_text("\n".join(normalize_proxy_lines(proxies)), encoding="utf-8")


def settings_file(token: str) -> Path:
    return user_dir(token) / "settings.json"


def read_settings(token: str) -> dict:
    path = settings_file(token)
    if not path.is_file():
        return {}
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def write_settings(token: str, payload: dict) -> None:
    import json

    settings_file(token).write_text(json.dumps(payload, indent=2), encoding="utf-8")
