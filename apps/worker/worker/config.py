from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    user_data_dir: str = "/var/lib/usersniper/data"
    worker_platforms: str = "discord"
    workers_per_proxy_line: int = 8
    max_proxy_lines: int = 128
    max_workers: int = 48
    request_timeout_sec: float = 5.0
    rate_limit_backoff_sec: float = 0.2
    rate_limit_backoff_max_sec: float = 4.0
    rate_limit_hard_pause_max_sec: float = 4.0
    long_rate_limit_retry_after_sec: float = 30.0
    long_rate_limit_pause_min_sec: float = 6.0
    long_rate_limit_pause_max_sec: float = 12.0
    long_rate_limit_max_retries: int = 1
    discord_recovery_interval_sec: float = 4.0
    max_retries_per_name: int = 5
    status_flush_interval_sec: float = 0.5

    @property
    def platform_list(self) -> list[str]:
        return [p.strip() for p in self.worker_platforms.split(",") if p.strip()]


settings = Settings()
