from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jira_base_url: str
    jira_username: str
    jira_api_token: str
    jira_project_key: str | None = None

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "nomic-embed-text"
    ollama_chat_model: str = "llama3.2"

    similarity_threshold: float = 70
    top_results: int = 3

    generate_reason: bool = False
    generate_reason_for_top: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()