"""Application configuration."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://leadgen:leadgen123@db:5432/leadgen"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ALGORITHM: str = "HS256"  # Alias for JWT_ALGORITHM
    JWT_EXPIRATION_HOURS: int = 24
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # External APIs
    CLEARBIT_API_KEY: Optional[str] = None
    ZEROBOUNCE_API_KEY: Optional[str] = None
    INSTANTLY_API_KEY: Optional[str] = None
    SMARTLEAD_API_KEY: Optional[str] = None
    
    # Feature Flags
    ENABLE_ENRICHMENT: bool = False
    ENABLE_VERIFICATION: bool = False
    ENABLE_BATCH_PROCESSING: bool = True
    
    # Batch Processing Configuration
    BATCH_SCHEDULE: str = "0 0,6,12,18 * * *"  # 4x daily: midnight, 6am, noon, 6pm
    BATCH_SIZE: int = 1000
    BATCH_WORKERS: int = 4
    
    # Lead Configuration
    LEAD_RETENTION_DAYS: int = 365  # How long to keep leads before archiving

    
    INSTANTLY_API_KEY: Optional[str] = None

    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
