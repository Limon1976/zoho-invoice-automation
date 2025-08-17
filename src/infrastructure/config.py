"""
Configuration Management
========================

Type-safe configuration using Pydantic Settings with environment variable support.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
import os

class OurCompanyConfig(BaseModel):
    """Configuration for our companies"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )
    
    name: str = Field(..., description="Company name")
    vat: str = Field(..., description="VAT number")
    country: str = Field(..., description="Country")

class ZohoConfig(BaseSettings):
    """Zoho Books API configuration"""
    model_config = ConfigDict(
        env_prefix="ZOHO_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    client_id: str = Field(..., description="Zoho client ID")
    client_secret: str = Field(..., description="Zoho client secret")
    refresh_token: Optional[str] = Field(None, description="Zoho refresh token")
    organization_id: Optional[str] = Field(None, description="Zoho organization ID")
    base_url: str = Field("https://books.zoho.eu/api/v3", description="Zoho API base URL")

class OpenAIConfig(BaseSettings):
    """OpenAI API configuration"""
    model_config = ConfigDict(
        env_prefix="OPENAI_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    api_key: str = Field(..., description="OpenAI API key")
    assistant_id: str = Field(..., description="OpenAI Assistant ID")
    model: str = Field("gpt-4", description="OpenAI model to use")
    max_tokens: int = Field(4000, description="Maximum tokens per request")

class TelegramConfig(BaseSettings):
    """Telegram Bot configuration"""
    model_config = ConfigDict(
        env_prefix="TELEGRAM_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    bot_token: str = Field(..., description="Telegram bot token")
    chat_id: Optional[str] = Field(None, description="Default chat ID")
    enabled: bool = Field(True, description="Enable Telegram notifications")

class GoogleVisionConfig(BaseSettings):
    """Google Vision API configuration"""
    model_config = ConfigDict(
        env_prefix="GOOGLE_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    credentials_path: Optional[str] = Field(None, description="Path to Google credentials JSON file")
    
    @field_validator('credentials_path')
    @classmethod
    def validate_credentials_file(cls, v: Optional[str]) -> Optional[str]:
        """Validate that credentials file exists if provided"""
        if v and not os.path.exists(v):
            raise ValueError(f"Google credentials file not found: {v}")
        return v

class ProcessingConfig(BaseSettings):
    """Document processing configuration"""
    model_config = ConfigDict(
        env_prefix="PROCESSING_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    our_companies: List[Dict[str, str]] = Field(
        default=[
            {"name": "TaVie Europe OÜ", "vat": "EE102288270", "country": "Estonia"},
            {"name": "Parkentertainment Sp. z o.o.", "vat": "PL5272956146", "country": "Poland"},
        ],
        description="List of our companies for document ownership detection"
    )
    
    supported_currencies: List[str] = Field(
        default=["EUR", "USD", "PLN", "SEK", "GBP"],
        description="Supported currencies"
    )
    
    inbox_folder: str = Field("inbox", description="Folder for incoming documents")
    invoices_folder: str = Field("invoices", description="Folder for processed documents")
    
    # VAT validation patterns by country
    vat_patterns: Dict[str, str] = Field(
        default={
            "PL": r"^PL\d{10}$",
            "EE": r"^EE\d{9}$",
            "DE": r"^DE\d{9}$",
            "FR": r"^FR[A-Z0-9]{2}\d{9}$",
            "ES": r"^ES[A-Z0-9]\d{7}[A-Z0-9]$",
            "IT": r"^IT\d{11}$",
            "NL": r"^NL\d{9}B\d{2}$",
            "BE": r"^BE0\d{9}$",
            "AT": r"^ATU\d{8}$",
            "SE": r"^SE\d{12}$",
            "DK": r"^DK\d{8}$",
            "FI": r"^FI\d{8}$",
            "GB": r"^GB\d{9}$|^GB\d{12}$|^GBGD\d{3}$|^GBHA\d{3}$",
            "US": r"^\d{2}-\d{7}$"
        },
        description="VAT number validation patterns by country"
    )

class DatabaseConfig(BaseSettings):
    """Database configuration"""
    model_config = ConfigDict(
        env_prefix="DATABASE_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    url: str = Field("sqlite:///./invoices.db", description="Database URL")
    echo: bool = Field(False, description="Enable SQL query logging")

class LoggingConfig(BaseSettings):
    """Logging configuration"""
    model_config = ConfigDict(
        env_prefix="LOG_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    level: str = Field("INFO", description="Logging level")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )

class APIConfig(BaseSettings):
    """API server configuration"""
    model_config = ConfigDict(
        env_prefix="API_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    host: str = Field("0.0.0.0", description="API host")
    port: int = Field(8000, description="API port")
    reload: bool = Field(False, description="Enable auto-reload")
    workers: int = Field(1, description="Number of worker processes")

class Settings(BaseSettings):
    """Main application settings"""
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True
    )
    
    # Environment
    environment: str = Field("development", description="Environment name")
    debug: bool = Field(False, description="Enable debug mode")
    
    # Component configurations (использование default_factory для ленивого создания)
    zoho: ZohoConfig = Field(default_factory=ZohoConfig, description="Zoho configuration")
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig, description="OpenAI configuration")
    telegram: TelegramConfig = Field(default_factory=TelegramConfig, description="Telegram configuration")
    google_vision: GoogleVisionConfig = Field(default_factory=GoogleVisionConfig, description="Google Vision configuration")
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig, description="Processing configuration")
    database: DatabaseConfig = Field(default_factory=DatabaseConfig, description="Database configuration")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration")
    api: APIConfig = Field(default_factory=APIConfig, description="API configuration")

def get_config() -> Settings:
    """Get application configuration"""
    return Settings()

# Global configuration instance
config = get_config() 