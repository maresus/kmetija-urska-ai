from openai import OpenAI

from app.core.config import Settings

_settings = Settings()


def get_llm_client() -> OpenAI:
    """Return an initialized OpenAI client or raise if API key missing."""
    if not _settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY ni nastavljen. Dodaj ga v okolje ali .env datoteko."
        )
    return OpenAI(api_key=_settings.openai_api_key)
