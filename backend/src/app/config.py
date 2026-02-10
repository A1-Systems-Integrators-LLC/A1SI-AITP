from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "sqlite+aiosqlite:///data/crypto_investor.db"

    exchange_id: str = "binance"
    exchange_api_key: str = ""
    exchange_api_secret: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def db_path(self) -> Path:
        # Extract file path from sqlite URL
        path = self.database_url.split("///")[-1]
        return Path(path)


settings = Settings()
