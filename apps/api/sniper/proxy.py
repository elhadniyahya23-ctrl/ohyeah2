from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass
from urllib.parse import quote, unquote

# FlashProxy + common reseller gateways (same -session- auth style).
_FLASHPROXY_MARKERS = (
    "flashproxy.io",
    "flashproxy.com",
    "proxyserver.bot",
    "adam.flashproxy",
)
_DATAIMPULSE_MARKERS = ("dataimpulse.com", "dataimpulse.net")


def _looks_like_host(value: str) -> bool:
    v = value.lower().strip("[]")
    if not v or " " in v or "/" in v:
        return False
    if v.replace(".", "").isdigit():  # IPv4-ish
        return True
    # hostname, localhost, or provider host
    return bool(re.fullmatch(r"[a-z0-9._-]+", v))


def _looks_like_port(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 65535


@dataclass(slots=True)
class ProxyConfig:
    host: str
    port: int
    user: str
    password: str
    speed: str = "speed-fast"
    rotate_sessions: bool = False
    _session_i: int = 0

    @classmethod
    def from_line(cls, raw: str, *, rotate_sessions: bool = False) -> ProxyConfig | None:
        """
        Accept common proxy paste formats:
          - host:port:user:pass
          - user:pass@host:port
          - http(s)://user:pass@host:port
          - user:pass:host:port
          - host:port@user:pass  (rare swap)
        DataImpulse usernames may contain __cr.us / __sessid — keep them intact.
        """
        line = raw.strip()
        if not line or line.startswith("#"):
            return None

        # Strip scheme
        if "://" in line:
            line = line.split("://", 1)[1]

        # user:pass@host:port  (DataImpulse / standard URI)
        if "@" in line:
            left, right = line.rsplit("@", 1)
            # Normal: creds @ host:port
            if ":" in right and _looks_like_port(right.rsplit(":", 1)[1]):
                host, port_s = right.rsplit(":", 1)
                if ":" not in left:
                    return None
                user, password = left.split(":", 1)
                return cls(
                    host=host.strip("[]"),
                    port=int(port_s),
                    user=unquote(user),
                    password=unquote(password),
                    rotate_sessions=rotate_sessions,
                )
            # Rare swap: host:port @ user:pass
            if ":" in left and _looks_like_port(left.rsplit(":", 1)[1]) and ":" in right:
                host, port_s = left.rsplit(":", 1)
                user, password = right.split(":", 1)
                return cls(
                    host=host.strip("[]"),
                    port=int(port_s),
                    user=unquote(user),
                    password=unquote(password),
                    rotate_sessions=rotate_sessions,
                )
            return None

        parts = line.split(":")
        # host:port:user:pass[...]  (FlashProxy / IP:port:user:pass)
        if len(parts) >= 4 and _looks_like_port(parts[1]) and _looks_like_host(parts[0]):
            host, port_s = parts[0], parts[1]
            user = parts[2]
            password = ":".join(parts[3:])
            return cls(
                host=host.strip("[]"),
                port=int(port_s),
                user=unquote(user),
                password=unquote(password),
                rotate_sessions=rotate_sessions,
            )

        # user:pass:host:port
        if len(parts) >= 4 and _looks_like_port(parts[-1]) and _looks_like_host(parts[-2]):
            port_s = parts[-1]
            host = parts[-2]
            # user may contain colons rarely; take first as user, middle as pass
            user = parts[0]
            password = ":".join(parts[1:-2])
            if user and password:
                return cls(
                    host=host.strip("[]"),
                    port=int(port_s),
                    user=unquote(user),
                    password=unquote(password),
                    rotate_sessions=rotate_sessions,
                )

        return None

    @classmethod
    def from_user_record(cls, proxy_string: str) -> ProxyConfig:
        cfg = cls.from_line(proxy_string)
        if cfg is None:
            raise ValueError(f"Invalid proxy: {proxy_string!r}")
        return cfg

    def _provider_session_mode(self) -> str:
        """Return flashproxy | dataimpulse | none — auto from host/user, no manual brand pick."""
        user_l = self.user.lower()
        host_l = self.host.lower()
        if "-session-" in self.user or "__sessid" in user_l or ";sessid." in user_l:
            return "none"
        if any(m in host_l for m in _FLASHPROXY_MARKERS):
            return "flashproxy"
        if any(m in host_l for m in _DATAIMPULSE_MARKERS) or "__cr." in user_l:
            return "dataimpulse"
        if self.rotate_sessions:
            # Forced rotation for unknown hosts (legacy trial default).
            return "flashproxy"
        return "none"

    def _auth_user(self, session_id: str | None = None) -> str:
        mode = self._provider_session_mode()
        sid = session_id or uuid.uuid4().hex[:10]
        if mode == "flashproxy":
            return f"{self.user}-session-{sid}-{self.speed}"
        if mode == "dataimpulse":
            # Sticky/rotating exit: login__cr.xx__sessid.ID
            base = re.sub(r"(__sessid\.[A-Za-z0-9_-]+|;sessid\.[A-Za-z0-9_-]+)", "", self.user)
            return f"{base}__sessid.{sid}"
        return self.user

    def workers_budget(self) -> int:
        """Safe concurrent Discord workers for this single proxy line."""
        mode = self._provider_session_mode()
        host_l = self.host.lower()
        if mode == "flashproxy" or any(m in host_l for m in _FLASHPROXY_MARKERS):
            return 6
        if mode == "dataimpulse" or any(m in host_l for m in _DATAIMPULSE_MARKERS):
            return 6
        return 4

    def rotate_url(self) -> str:
        mode = self._provider_session_mode()
        if mode == "flashproxy":
            # Bounded sticky pool for FlashProxy gateways.
            sid = f"ps{self._session_i % 128:03d}"
            self._session_i += 1
            user = self._auth_user(sid)
        elif mode == "dataimpulse":
            # Fresh sessid every request. A shared trial login must not recycle the
            # same 128 sticky exits across every Free Trial Discord job (429 storm).
            user = self._auth_user(uuid.uuid4().hex[:12])
        else:
            user = self._auth_user()
        return (
            f"http://{quote(user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}:{self.port}"
        )

    def bump_session(self, steps: int = 1) -> None:
        self._session_i += max(1, steps)

    def url_for_slot(self, slot: int) -> str:
        mode = self._provider_session_mode()
        if mode == "none":
            return self.rotate_url()
        user = self._auth_user(f"ps{slot % 256:03d}")
        return (
            f"http://{quote(user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}:{self.port}"
        )


class DirectIPRotator:
    """Datacenter egress without proxy lines — the server's own IP(s) hit Discord.

    Drop-in for ProxyRotator on the turbo engine: same lease/report/slot API.
    Optional source-IP binding via SNIPER_SOURCE_IPS (comma-separated local
    addresses) lets one multi-IP VPS spread load across its own IPs.
    """

    def __init__(self, source_ips: list[str] | None = None) -> None:
        self._ips = [ip.strip() for ip in (source_ips or []) if ip.strip()]
        self._i = 0

    @property
    def line_count(self) -> int:
        return max(1, len(self._ips))

    @property
    def rotate_sessions(self) -> bool:
        return False

    @property
    def workers_budget(self) -> int:
        # One datacenter IP tolerates far less Discord concurrency than a
        # residential rotating pool — RL is per-IP.
        return 6 * self.line_count

    def _next_local_address(self) -> str | None:
        if not self._ips:
            return None
        with threading.Lock():
            ip = self._ips[self._i % len(self._ips)]
            self._i += 1
        return ip

    def next_lease(self) -> tuple[str, int]:
        # Empty proxy_url = direct connection (http_util.proxy_dict returns None).
        return "", self._i

    def next_url(self) -> str:
        return ""

    def url_for_slot(self, slot: int) -> str:
        return ""

    def report(self, idx: int, status: str) -> None:
        # Direct egress: nothing to rotate — the engine's adaptive cap handles RL.
        return


class ProxyRotator:
    """Round-robin with live success scoring — prefer lines that still produce valid checks."""

    def __init__(self, configs: list[ProxyConfig]) -> None:
        if not configs:
            raise ValueError("At least one proxy config required")
        self._configs = configs
        self._i = 0
        n = len(configs)
        self._ok = [0] * n
        self._bad = [0] * n
        self._cooldown_until = [0.0] * n
        self._lock = threading.Lock()

    @property
    def line_count(self) -> int:
        return len(self._configs)

    @property
    def rotate_sessions(self) -> bool:
        return any(c._provider_session_mode() != "none" for c in self._configs)

    @property
    def workers_budget(self) -> int:
        return max(1, sum(c.workers_budget() for c in self._configs))

    def _score(self, idx: int) -> float:
        ok = self._ok[idx]
        bad = self._bad[idx]
        return (ok + 3.0) / (ok + bad + 6.0)

    def next_lease(self) -> tuple[str, int]:
        """Fair share across every pasted line (FlashProxy / DataImpulse / …).

        Round-robin so N providers each get ~1/N of the traffic. Skip cooling /
        dead lines when healthier alternatives exist; never pin all workers on one.
        """
        with self._lock:
            now = time.monotonic()
            n = len(self._configs)
            # First pass: strict round-robin among ready lines.
            for _ in range(n):
                idx = self._i % n
                self._i += 1
                if self._cooldown_until[idx] > now:
                    continue
                # Soft-skip a line that is clearly dying if others are alive.
                if self._bad[idx] >= 12 and self._ok[idx] * 3 < self._bad[idx]:
                    alt_alive = any(
                        j != idx
                        and self._cooldown_until[j] <= now
                        and not (self._bad[j] >= 12 and self._ok[j] * 3 < self._bad[j])
                        for j in range(n)
                    )
                    if alt_alive:
                        continue
                return self._configs[idx].rotate_url(), idx

            # Everything cooling or sick — clear cool, pick least-bad, keep RR cursor.
            self._cooldown_until = [0.0] * n
            ranked = sorted(range(n), key=self._score, reverse=True)
            idx = ranked[0]
            self._i = idx + 1
            return self._configs[idx].rotate_url(), idx

    def next_url(self) -> str:
        url, _idx = self.next_lease()
        return url

    def report(self, idx: int, status: str) -> None:
        with self._lock:
            if idx < 0 or idx >= len(self._configs):
                return
            if status in ("available", "taken"):
                self._ok[idx] += 1
                if self._bad[idx] > 0:
                    self._bad[idx] -= 1
                self._cooldown_until[idx] = 0.0
                return
            if status == "rate_limited":
                self._bad[idx] += 1
                # Jump to a fresh exit; cool longer as RL stacks so we don't stampede.
                self._configs[idx].bump_session(31)
                cool = 0.7 if self._bad[idx] < 8 else 1.6
                if self._bad[idx] >= 16:
                    cool = 2.8
                self._cooldown_until[idx] = max(
                    self._cooldown_until[idx], time.monotonic() + cool
                )
                return
            if status == "proxy_late":
                self._bad[idx] += 1
                self._configs[idx].bump_session(9)
                if self._bad[idx] >= 8 and self._ok[idx] <= 2:
                    self._cooldown_until[idx] = time.monotonic() + 8.0
                elif self._bad[idx] >= 16 and self._ok[idx] * 3 < self._bad[idx]:
                    self._cooldown_until[idx] = time.monotonic() + 14.0
                return

    def url_for_slot(self, slot: int) -> str:
        cfg = self._configs[slot % len(self._configs)]
        return cfg.url_for_slot(slot // len(self._configs))

    @classmethod
    def from_lines(
        cls, lines: list[str], *, rotate_sessions: bool = False
    ) -> ProxyRotator:
        configs: list[ProxyConfig] = []
        seen: set[str] = set()
        for line in lines:
            key = line.strip()
            if key in seen:
                continue
            seen.add(key)
            cfg = ProxyConfig.from_line(line, rotate_sessions=rotate_sessions)
            if cfg is not None:
                configs.append(cfg)
        if not configs:
            raise ValueError("No valid proxy lines")
        return cls(configs)
