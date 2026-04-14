"""Application configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://devlogplus:devlogplus@db:5432/devlogplus",
        description="Async PostgreSQL connection string",
    )

    # --- OpenRouter ---
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )

    # --- Langfuse ---
    langfuse_public_key: str = Field(default="", description="Langfuse public key")
    langfuse_secret_key: str = Field(default="", description="Langfuse secret key")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL",
    )

    # --- LLM Model Selection (per pipeline) ---
    llm_model_topic_extraction: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_profile_update: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_quiz_generation: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_quiz_evaluation: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_reading_generation: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_project_generation: str = Field(default="anthropic/claude-sonnet-4")
    llm_model_project_evaluation: str = Field(default="anthropic/claude-sonnet-4")

    # --- Application ---
    quiz_question_count: int = Field(default=10, ge=1, le=50)
    reading_recommendation_count: int = Field(default=5, ge=1, le=20)
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Paths ---
    workspace_projects_dir: str = Field(
        default="workspace/projects",
        description="Directory for generated weekly Go projects",
    )
    frontend_dist_dir: str = Field(
        default="frontend/dist",
        description="Directory containing built frontend assets",
    )

    def model_for_pipeline(self, pipeline: str) -> str:
        """Return the configured model name for a given pipeline."""
        model_map = {
            "topic_extraction": self.llm_model_topic_extraction,
            "profile_update": self.llm_model_profile_update,
            "quiz_generation": self.llm_model_quiz_generation,
            "quiz_evaluation": self.llm_model_quiz_evaluation,
            "reading_generation": self.llm_model_reading_generation,
            "project_generation": self.llm_model_project_generation,
            "project_evaluation": self.llm_model_project_evaluation,
        }
        model = model_map.get(pipeline)
        if model is None:
            raise ValueError(f"Unknown pipeline: {pipeline}")
        return model


settings = Settings()
