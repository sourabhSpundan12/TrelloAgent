from pathlib import Path
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Application Info
    APP_NAME: str = "PM Hooks"
    APP_ENV: str = "development"  # development, testing, staging, production
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Backward compatibility aliases for Phase 1/2 references
    @property
    def PROJECT_NAME(self) -> str:
        return self.APP_NAME

    @property
    def ENVIRONMENT(self) -> str:
        return self.APP_ENV

    @property
    def API_V1_STR(self) -> str:
        return self.API_V1_PREFIX

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS & Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return []

    # MongoDB Configuration
    MONGODB_URL: Optional[str] = None
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "agentic_task_manager"
    MONGODB_DB_NAME_ENV: Optional[str] = None
    MONGODB_MIN_POOL_SIZE: int = 5
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_TIMEOUT_MS: int = 10000

    @property
    def EFFECTIVE_MONGODB_URI(self) -> str:
        return self.MONGODB_URL or self.MONGODB_URI

    @property
    def MONGODB_DB_NAME(self) -> str:
        return self.MONGODB_DATABASE

    # JWT Authentication & Security
    JWT_SECRET_KEY: str = "agentic-secret-key-change-in-production-super-secure-token-32b"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Optional Admin Bootstrap Configuration
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "System Administrator"

    # Placeholders for future phases (uninitialized in Phase 3)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    
    # LLM & LangChain Multi-Provider Configuration
    LLM_PROVIDER: str = "google"  # "google" | "openai"
    LLM_MODEL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT: int = 60
    LLM_MAX_TOKENS: Optional[int] = None

    # PII Detection and Masking Configuration (Microsoft Presidio)
    PII_MASKING_ENABLED: bool = True
    PII_MASKING_PROVIDER: str = "presidio"
    PII_MASKING_THRESHOLD: float = 0.5
    PII_MASKING_ENTITIES: List[str] = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "LOCATION",
        "IP_ADDRESS",
        "URL",
        "CREDIT_CARD",
        "IBAN_CODE",
        "US_SSN",
        "IN_PAN",
        "IN_AADHAAR",
        "IN_PASSPORT",
    ]
    PII_TERMINAL_LOGGING: bool = True

    @property
    def EFFECTIVE_LLM_MODEL(self) -> str:
        if self.LLM_MODEL:
            return self.LLM_MODEL
        if self.LLM_PROVIDER.lower() in ("openai",):
            return "gpt-4o-mini"
        return self.GEMINI_MODEL or "gemini-3.5-flash-lite"

    TRELLO_API_KEY: str = ""
    TRELLO_TOKEN: str = ""
    TRELLO_BOARD_ID: str = ""
    N8N_WEBHOOK_URL: str = ""
    N8N_API_KEY: str = ""
    PENDING_ACTION_DEFAULT_TTL_MINUTES: int = 30

    # SMTP / Email Configuration for Password Reset & Notifications
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "PM Hooks"
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15

    # Employee Performance Scoring Configuration (Module 4)
    PERFORMANCE_WEIGHT_ON_TIME: float = 0.40
    PERFORMANCE_WEIGHT_CONSISTENCY: float = 0.30
    PERFORMANCE_WEIGHT_COMPLETION: float = 0.20
    PERFORMANCE_WEIGHT_RELIABILITY: float = 0.10
    PERFORMANCE_HIGH_THRESHOLD: float = 80.0
    PERFORMANCE_MEDIUM_THRESHOLD: float = 60.0
    PERFORMANCE_MIN_COMPLETED_TASKS: int = 3
    PERFORMANCE_EVALUATION_DAYS: int = 90

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        # Synchronize MONGODB_URL and MONGODB_URI
        if self.MONGODB_URL and (not self.MONGODB_URI or self.MONGODB_URI == "mongodb://localhost:27017"):
            self.MONGODB_URI = self.MONGODB_URL
        elif self.MONGODB_URI and not self.MONGODB_URL:
            self.MONGODB_URL = self.MONGODB_URI

        # Synchronize MONGODB_DATABASE if MONGODB_DB_NAME_ENV was passed
        if self.MONGODB_DB_NAME_ENV:
            self.MONGODB_DATABASE = self.MONGODB_DB_NAME_ENV

        # Validate that in production, security-critical values are not defaults
        if self.APP_ENV == "production":
            if "agentic-secret-key-change" in self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("In production, JWT_SECRET_KEY must be a secure random key with at least 32 characters.")
            if self.BOOTSTRAP_ADMIN_PASSWORD == "AdminSecurePassword123!":
                raise ValueError("In production, default development admin password must not be used.")
            if self.DEBUG:
                self.DEBUG = False
            if self.FRONTEND_URL and self.FRONTEND_URL not in self.BACKEND_CORS_ORIGINS:
                self.BACKEND_CORS_ORIGINS.append(self.FRONTEND_URL)
        return self

    model_config = SettingsConfigDict(
        env_file=(
            str(_ROOT_DIR / ".env"),
            str(_BACKEND_DIR / ".env"),
            ".env",
            "../.env",
            "../../.env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
