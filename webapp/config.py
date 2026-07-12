"""Application configuration via pydantic-settings. All values are overridable through
environment variables (or a local ``.env``). DigiKey credentials are read directly from
the environment by :mod:`capinator.digikey`, so they are not duplicated here."""
from functools import cached_property
from typing import Set

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./capinator.db"

    # Sessions / auth
    secret_key: str = "dev-insecure-change-me"

    # Job limits
    guest_job_limit: int = 2          # jobs per guest per 24h
    max_spec_rows: int = 100          # cap pasted-list size to bound per-job API calls

    # Seed catalog (flat-file durability for Render's ephemeral disk)
    seed_file: str = "seed/component_lists.yaml"
    seed_on_startup: bool = True
    seed_owner_email: str = "curator@capinator.local"

    # Admin gate for the seed export/import UI (comma-separated). Empty => seed owner.
    admin_emails: str = ""

    # Worker back-off: pause dequeuing when remaining quota drops to/below this.
    quota_low_water: int = 5

    # Public API: max requests per API key per minute (read-only; no DigiKey calls).
    api_rate_limit_per_min: int = 60

    @cached_property
    def admin_email_set(self) -> Set[str]:
        emails = {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}
        return emails or {self.seed_owner_email.strip().lower()}


settings = Settings()
