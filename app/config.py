"""Config: loads .env once, exposes typed settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    client_id: str = os.getenv("PAYPAL_CLIENT_ID", "")
    client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    base_url: str = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    currency: str = os.getenv("PAYPAL_CURRENCY", "USD")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    # Optional second provider. Tried when the first one is rate limited or down, so a 20
    # requests/day free tier cannot take the demo offline mid-recording.
    llm2_base_url: str = os.getenv("LLM2_BASE_URL", "")
    llm2_api_key: str = os.getenv("LLM2_API_KEY", "")
    llm2_model: str = os.getenv("LLM2_MODEL", "")
    db_path: Path = ROOT / os.getenv("RESTOCK_DB", "data/restock.db")
    # The merchant's standing spend limit. It lives here, on the server, not in the request:
    # a caller cannot raise it by asking the API nicely.
    autopay_limit: float = float(os.getenv("AUTOPAY_LIMIT_USD", "0") or 0)
    # Signs the approval token that binds a human review to one exact draft state.
    approval_secret: str = os.getenv("APPROVAL_SECRET", "")
    # Forces mock PayPal and the deterministic planner even when real credentials are present.
    # A demo handed to someone else must never be able to charge the sandbox account or spend
    # model quota, and "nothing is charged" has to stay true regardless of what .env contains.
    offline: bool = os.getenv("RESTOCK_OFFLINE", "").strip().lower() not in ("", "0", "false", "no")

    @property
    def has_paypal_creds(self) -> bool:
        return bool(self.client_id and self.client_secret) and not self.offline

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url) and not self.offline

    @property
    def has_llm2(self) -> bool:
        return bool(self.llm2_api_key and self.llm2_base_url and self.llm2_model) and not self.offline


settings = Settings()
