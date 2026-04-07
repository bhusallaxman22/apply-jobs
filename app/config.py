from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8095
    database_url: str = "sqlite:///./job-agent.db"
    redis_url: str = "redis://localhost:6379/0"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    storage_root: str = "./storage"
    headless: bool = True
    require_human_approval: bool = True
    max_agent_steps: int = 15
    planner_temperature: float = 0.1
    llm_timeout_seconds: int = 60
    navigation_timeout_ms: int = 45_000
    slow_mo_ms: int = 0
    browser_desktop_enabled: bool = False
    browser_desktop_port: int = 7900
    browser_desktop_public_url: str | None = None
    captcha_wait_timeout_seconds: int = 900

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root).expanduser().resolve()

    @property
    def screenshots_path(self) -> Path:
        return self.storage_path / "screenshots"

    @property
    def traces_path(self) -> Path:
        return self.storage_path / "traces"

    @property
    def browser_states_path(self) -> Path:
        return self.storage_path / "browser-states"

    @property
    def html_path(self) -> Path:
        return self.storage_path / "html"

    @property
    def resumes_path(self) -> Path:
        return self.storage_path / "resumes"

    @property
    def resume_variants_path(self) -> Path:
        return self.resumes_path / "variants"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def ensure_storage_dirs() -> None:
    settings = get_settings()
    for path in (
        settings.storage_path,
        settings.screenshots_path,
        settings.traces_path,
        settings.browser_states_path,
        settings.html_path,
        settings.resumes_path,
        settings.resume_variants_path,
    ):
        path.mkdir(parents=True, exist_ok=True)
