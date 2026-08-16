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
    llm_model_topic_extraction: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_profile_update: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_quiz_generation: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_quiz_evaluation: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_reading_generation: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_project_generation: str = Field(default="anthropic/claude-sonnet-5")
    llm_model_project_evaluation: str = Field(default="anthropic/claude-sonnet-5")

    # Reasoning budget passed to OpenRouter. Newer models (Claude Sonnet 5
    # among them) reason by default, and OpenRouter bills reasoning as output
    # tokens — so reasoning draws down the same `max_tokens` the answer needs.
    # Left unbounded, a pipeline can spend its whole budget thinking and return
    # `content: null`.
    #
    # "none" disables reasoning, matching the behaviour this app's prompts and
    # per-pipeline max_tokens were sized for. Raise it deliberately, and raise
    # the affected pipeline's max_tokens at the same time.
    # Valid: none | minimal | low | medium | high | xhigh | max
    llm_reasoning_effort: str = Field(default="none")

    # --- Application ---
    quiz_question_count: int = Field(default=10, ge=1, le=50)
    reading_recommendation_count: int = Field(default=5, ge=1, le=20)
    reading_validate_urls: bool = Field(
        default=True,
        description=(
            "If true, the reading pipeline fetches every LLM-proposed URL and drops "
            "recommendations that don't resolve, that point at a site index or listing "
            "page, or whose page title doesn't match the claimed title. "
            "Disable for offline dev or to skip the network round-trip."
        ),
    )
    # Keep in step with reading_svc.DEFAULT_MIN_TITLE_OVERLAP — the service
    # layer cannot import config, so the value is stated in both places and a
    # test asserts they match.
    reading_min_title_overlap: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum agreement (0..1) between a recommendation's claimed title and the "
            "fetched page's own title before the link is accepted. Raise to be stricter "
            "about mismatched links; set to 0 to accept any reachable non-index page."
        ),
    )
    reading_url_validation_timeout: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Per-URL timeout (seconds) for reading URL reachability checks.",
    )
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Paths ---
    workspace_projects_dir: str = Field(
        default="workspace/projects",
        description="Directory for generated weekly Go projects",
    )
    go_executable: str = Field(
        default="/usr/local/go/bin/go",
        description="Path to the Go binary used for post-generation compile checks",
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
