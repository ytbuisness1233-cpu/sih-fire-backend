from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Enforce exact type safety across configuration bounds
    DATABASE_HOSTNAME: str
    DATABASE_PORT: int  # Fixed: Defined as integer for strict database engine compatibility
    DATABASE_PASSWORD: str
    DATABASE_NAME: str
    DATABASE_USERNAME: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FIRMS_API_KEY: str

    # Configuration mapping settings for Pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True  # Guarantees explicit alignment with environment architecture standards
    )

# Instantiate settings schema container globally
settings = Settings()
