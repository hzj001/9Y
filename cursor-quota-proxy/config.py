from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    cursor_api_key: str
    admin_secret: str
    database_url: str = "sqlite:///./quota.db"
    cursor_api_base: str = "https://api.cursor.com"
    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
