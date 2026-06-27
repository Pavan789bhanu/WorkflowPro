"""Application configuration.

All settings can be overridden via environment variables / the project root
`.env` file. Paths default to locations inside the project but can be
re-pointed (e.g. inside Docker) with DATA_DIR / SCREENSHOT_DIR / DATABASE_URL.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os
import secrets
import warnings
from pathlib import Path

# Get project root (3 levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "WorkflowPro"
    VERSION: str = "2.0.0"

    # CORS Settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5179",
        "http://localhost:5176",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    # Database (SQLite for simplicity, can upgrade to PostgreSQL later)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_ROOT}/ui_capture.db")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 * 24 * 7  # 7 days

    # ------------------------------------------------------------------
    # LLM provider configuration
    # ------------------------------------------------------------------
    # LLM_PROVIDER: "openai" | "anthropic" | "auto"
    #   "auto" picks whichever provider has an API key configured
    #   (OpenAI wins if both are set, unless LLM_PROVIDER says otherwise).
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").lower()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", os.getenv("LLM_MODEL", "gpt-4o"))
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    # Kept for backwards compatibility with older code paths.
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

    # ------------------------------------------------------------------
    # Agent / automation settings
    # ------------------------------------------------------------------
    SCREENSHOT_DIR: Path = Path(os.getenv("SCREENSHOT_DIR", str(BACKEND_ROOT / "captured_dataset")))
    AGENT_MAX_STEPS: int = int(os.getenv("AGENT_MAX_STEPS", "25"))
    AGENT_STEP_TIMEOUT: int = int(os.getenv("AGENT_STEP_TIMEOUT", "60"))  # seconds per LLM+action cycle
    # Cost guard: end the run early after this many consecutive ineffective
    # actions (each wasted action costs an LLM call).
    AGENT_MAX_CONSECUTIVE_FAILURES: int = int(os.getenv("AGENT_MAX_CONSECUTIVE_FAILURES", "5"))

    # Workflow Engine Configuration (legacy engine + agent shared knobs)
    LOOP_DETECTION_WINDOW: int = 6
    MAX_INACTIVITY_SECONDS: int = int(os.getenv("MAX_INACTIVITY_SECONDS", "90"))
    MAX_ADAPTIVE_CYCLES: int = 6

    # URL Validation (SSRF Prevention)
    BLOCKED_IP_RANGES: List[str] = [
        "127.0.0.0/8",      # Localhost
        "10.0.0.0/8",       # Private network
        "172.16.0.0/12",    # Private network
        "192.168.0.0/16",   # Private network
        "169.254.0.0/16",   # Link-local
        "::1/128",          # IPv6 localhost
        "fc00::/7",         # IPv6 private
    ]
    BLOCKED_URL_SCHEMES: List[str] = ["file", "ftp", "data", "javascript"]
    ALLOWED_URL_SCHEMES: List[str] = ["http", "https"]
    USER_DATA_DIR: Path = Path(os.getenv("USER_DATA_DIR", str(PROJECT_ROOT / "browser_session_data")))
    STORAGE_STATE_PATH: Path = Path(os.getenv("STORAGE_STATE_PATH", str(PROJECT_ROOT / "storage_state.json")))
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))

    # Browser Settings
    TIMEOUT: int = int(os.getenv("TIMEOUT", "10000"))
    DEFAULT_HEADLESS: bool = os.getenv("DEFAULT_HEADLESS", "true").lower() == "true"
    # Playwright engine: chromium (default) | firefox | webkit.
    # Some sites are less hostile to Firefox — switchable without code changes.
    BROWSER_ENGINE: str = os.getenv("BROWSER_ENGINE", "chromium").lower()

    # Screenshot Analysis
    SCREENSHOT_DEDUPLICATION_ENABLED: bool = True
    SCREENSHOT_DEDUPLICATION_THRESHOLD: int = 20
    SCREENSHOT_DELETE_DUPLICATES: bool = True

    # Login Credentials (optional, for automation)
    LOGIN_EMAIL: Optional[str] = os.getenv("LOGIN_EMAIL")
    LOGIN_PASSWORD: Optional[str] = os.getenv("LOGIN_PASSWORD")

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # SECRET_KEY: required in production; auto-generated (with a loud
        # warning) in development so a fresh checkout still boots.
        if not self.SECRET_KEY:
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    "SECRET_KEY environment variable is required in production. "
                    "Generate one with: openssl rand -hex 32"
                )
            self.SECRET_KEY = secrets.token_hex(32)
            warnings.warn(
                "SECRET_KEY not set — generated an ephemeral key for this session. "
                "Tokens/encrypted credentials will not survive restarts. "
                "Set SECRET_KEY in .env (openssl rand -hex 32).",
                stacklevel=1,
            )

        # At least one LLM API key is needed for AI automation. We don't hard
        # crash at import time (health checks / db admin should still work) —
        # the LLM client gives a clear error when actually used.
        if not self.OPENAI_API_KEY and not self.ANTHROPIC_API_KEY:
            warnings.warn(
                "No OPENAI_API_KEY or ANTHROPIC_API_KEY configured — "
                "AI automation endpoints will return errors until one is set in .env.",
                stacklevel=1,
            )

    @property
    def active_llm_provider(self) -> str:
        """Resolve the provider to use, honoring LLM_PROVIDER and available keys."""
        provider = (self.LLM_PROVIDER or "auto").lower()
        if provider == "openai":
            return "openai"
        if provider == "anthropic":
            return "anthropic"
        # auto
        if self.OPENAI_API_KEY:
            return "openai"
        if self.ANTHROPIC_API_KEY:
            return "anthropic"
        return "none"


# Default app URL mappings
DEFAULT_APP_URL_MAPPINGS = {
    "notion": "https://www.notion.so",
    "linear": "https://linear.app",
    "slack": "https://app.slack.com",
    "asana": "https://app.asana.com",
    "monday": "https://monday.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "jira": "https://id.atlassian.com/login",
    "confluence": "https://id.atlassian.com/login",
    "figma": "https://figma.com",
    "trello": "https://trello.com",
    "miro": "https://miro.com",
    "airtable": "https://airtable.com",
    "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google calendar": "https://calendar.google.com",
    "gmail": "https://mail.google.com",
    "salesforce": "https://salesforce.com",
    "hubspot": "https://app.hubspot.com",
    "zendesk": "https://zendesk.com",
    "intercom": "https://app.intercom.io",
    "linkedin": "https://www.linkedin.com/feed/",
    "medium": "https://medium.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "hacker news": "https://news.ycombinator.com",
}

# Create singleton instance
settings = Settings()

# App URL mappings (can be customized via environment)
import json  # noqa: E402

_custom_mappings = os.getenv("APP_URL_MAPPINGS")
if _custom_mappings:
    try:
        APP_URL_MAPPINGS = {**DEFAULT_APP_URL_MAPPINGS, **json.loads(_custom_mappings)}
    except json.JSONDecodeError:
        APP_URL_MAPPINGS = DEFAULT_APP_URL_MAPPINGS
else:
    APP_URL_MAPPINGS = DEFAULT_APP_URL_MAPPINGS

# Create necessary directories
settings.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
settings.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
