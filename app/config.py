from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Unified Cloud Environment Variables
    DATABASE_URL: str  
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FIRMS_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True  
    )

settings = Settings()
