from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVONEXT_", env_file=".env", extra="ignore")
    demo: bool = False
    api_key: SecretStr | None = None
    mongo_uri: SecretStr = SecretStr("mongodb://127.0.0.1:27017")
    mongo_database: str = "evonext"
    mongo_collection: str = "evonext_snapshots"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: SecretStr | None = None
    minio_secret_key: SecretStr | None = None
    minio_bucket: str = "evonext"
    minio_secure: bool = False
    postgres_dsn: SecretStr | None = None
    broker_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    legacy_env_file: str = ""
    legacy_base_url: str = ""
    legacy_api_key: SecretStr | None = None
    legacy_writes: bool = False
    langfuse_enabled: bool = False
    langfuse_base_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr | None = None
    trace_content: bool = False
    model_base_url: str = ""
    model_api_key: SecretStr | None = None
    model_name: str = ""
    model_calls_enabled: bool = False
    model_image_quality: Literal[98, 90] = 98
    model_max_request_bytes: int = Field(default=1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    model_max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    review_operator_id: str = Field(default="", max_length=128)
    workshop_root: str = ""
    workshop_owner: str = Field(default="", max_length=128)
    model_budget_scope: str = Field(default="default", min_length=1, max_length=64)
    model_calls_per_minute: int = Field(default=10, ge=0, le=10000)
    model_calls_per_hour: int = Field(default=100, ge=0, le=100000)
    model_calls_per_day: int = Field(default=500, ge=0, le=1000000)
    max_upload_bytes: int = 64 * 1024 * 1024
    max_file_bytes: int = 8 * 1024 * 1024
    max_steps: int = 10000

    @field_validator("model_image_quality", mode="before")
    @classmethod
    def parse_image_quality(cls, value):
        # Environment values are strings; preserve Literal validation for every other input.
        return int(value) if isinstance(value, str) and value in {"90", "98"} else value

    @model_validator(mode="after")
    def safe_defaults(self):
        if not self.demo and (not self.api_key or not self.api_key.get_secret_value()):
            raise ValueError("Set EVONEXT_API_KEY, or explicitly enable local-only demo mode")
        if not self.mongo_collection.startswith("evonext_"):
            raise ValueError("New snapshots require an evonext_ collection; no legacy direct writes")
        if self.max_file_bytes <= 0 or self.max_upload_bytes < self.max_file_bytes:
            raise ValueError("Invalid upload limits")
        if self.demo and self.legacy_writes:
            raise ValueError("Demo mode cannot publish to a legacy platform")
        return self


def secret(value: SecretStr | None) -> str:
    return value.get_secret_value() if value else ""
