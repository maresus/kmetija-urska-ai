from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Nastavitve branja iz .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignoriraj dodatne env spremenljivke
    )
    
    # Ime projekta (ni nujno v .env, ima default)
    project_name: str = Field(default="Urška AI")
    
    # OpenAI ključ
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    
    # Database URL za PostgreSQL
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
