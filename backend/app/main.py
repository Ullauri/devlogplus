"""DevLog+ FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.routers import (
    feedback,
    journal,
    onboarding,
    pipelines,
    profile,
    project,
    quiz,
    reading,
    transfer,
    triage,
)
from backend.app.routers import (
    settings as settings_router,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Application startup / shutdown lifecycle."""
    logging.basicConfig(level=settings.log_level)
    logger.info("DevLog+ starting up (env=%s)", settings.app_env)

    # Ensure workspace projects directory exists
    await asyncio.to_thread(
        Path(settings.workspace_projects_dir).mkdir, parents=True, exist_ok=True
    )

    yield

    logger.info("DevLog+ shutting down")


app = FastAPI(
    title="DevLog+",
    description=(
        "Single-user developer journal for technical learning and skill maintenance.\n\n"
        "DevLog+ has two engines:\n\n"
        "- **Learning engine** — builds a Knowledge Profile from journal entries, quizzes, "
        "and feedback. Understands what you know, where you're weak, and what to explore "
        "next.\n"
        "- **Practice engine** — generates weekly Go micro-projects calibrated to your "
        "practical level.\n\n"
        "## Core workflow\n\n"
        "1. **Journal** — write technical entries (typed or dictated) about what you learn.\n"
        "2. **Profile** — the system builds and maintains a Knowledge Profile nightly.\n"
        "3. **Quiz** — weekly free-text quizzes probe your understanding.\n"
        "4. **Readings** — curated reading recommendations from your allowlisted domains.\n"
        "5. **Projects** — weekly Go micro-projects with bugs, features, and refactors.\n"
        "6. **Feedback** — thumbs-up/down reactions and feedforward notes steer future "
        "content.\n"
        "7. **Triage** — items the system can't resolve are surfaced for your "
        "clarification.\n"
    ),
    version="0.1.0",
    license_info={
        "name": "Private — single-user local application",
    },
    openapi_tags=[
        {
            "name": "journal",
            "description": (
                "CRUD operations for technical journal entries. Entries are text-only "
                "(typed or dictated via browser Web Speech API). Edits are versioned — "
                "the most recent version is the source of truth. New entries are "
                "processed nightly by the profile-update pipeline."
            ),
        },
        {
            "name": "profile",
            "description": (
                "Read-only view of the AI-derived Knowledge Profile. The profile "
                "organizes topics by evidence strength (strong / developing / limited), "
                "surfaces the current frontier (topics actively being learned) and the "
                "next frontier (recommended adjacent topics). Updated nightly."
            ),
        },
        {
            "name": "quizzes",
            "description": (
                "Weekly free-text quizzes that probe understanding. Each session has "
                "10 questions (configurable). Answers are evaluated by an LLM judge for "
                "correctness (full / partial / incorrect), depth, and confidence. "
                "Results feed back into the Knowledge Profile."
            ),
        },
        {
            "name": "readings",
            "description": (
                "Weekly reading recommendations and domain allowlist management. "
                "Recommendations are generated from the Knowledge Profile and limited "
                "to domains on the user's allowlist. The allowlist ships with sensible "
                "defaults and is fully editable."
            ),
        },
        {
            "name": "projects",
            "description": (
                "Weekly LLM-generated Go micro-projects. Each project is a "
                "self-contained codebase with source, tests, tasks (bugs, features, "
                "refactors, optimizations), and a README. Submit your solution and "
                "receive an AI evaluation before the next project is issued."
            ),
        },
        {
            "name": "triage",
            "description": (
                "Items the system can't confidently resolve on its own. Created by the "
                "profile-update, quiz-evaluation, and project-evaluation pipelines. "
                "Severity levels: low / medium / high / critical. High and critical "
                "items block the next profile-update cycle until resolved."
            ),
        },
        {
            "name": "feedback",
            "description": (
                "Two distinct signal types on every generated item:\n\n"
                "- **Feedback** (thumbs-up / thumbs-down) — corrects the system's "
                "current understanding.\n"
                "- **Feedforward** (free-text note) — shapes what the system should "
                "generate next.\n\n"
                "Attach to individual quiz questions, readings, or the project as a "
                "whole."
            ),
        },
        {
            "name": "settings",
            "description": (
                "User-configurable application settings stored as key-value pairs. "
                "Includes model selection, quiz question count, cron schedules, and "
                "other tunables."
            ),
        },
        {
            "name": "onboarding",
            "description": (
                "First-run experience (~10–15 min). Collects technical background "
                "self-assessment, Go experience level, a short diagnostic quiz, and "
                "optional topic interests. Establishes baseline context before the "
                "normal processing cycle begins."
            ),
        },
        {
            "name": "transfer",
            "description": (
                "Export and import all application data for device-to-device "
                "migration. Export produces a single JSON file containing every "
                "table. Import replaces all existing data with the uploaded "
                "bundle — use when moving DevLog+ from one machine to another."
            ),
        },
        {
            "name": "pipelines",
            "description": (
                "Manual, user-initiated triggers for the pipelines that "
                "normally run on a cron schedule (profile update, quiz, "
                "reading, and project generation). Intended as an opt-in "
                "escape hatch exposed in the Settings page — not part of "
                "the normal daily flow. Each trigger returns 202 Accepted "
                "immediately and runs the pipeline in the background; use "
                "`GET /pipelines/runs` to observe progress."
            ),
        },
    ],
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routers — all under /api/v1
# ---------------------------------------------------------------------------
api_prefix = "/api/v1"
app.include_router(journal.router, prefix=api_prefix)
app.include_router(profile.router, prefix=api_prefix)
app.include_router(quiz.router, prefix=api_prefix)
app.include_router(reading.router, prefix=api_prefix)
app.include_router(project.router, prefix=api_prefix)
app.include_router(triage.router, prefix=api_prefix)
app.include_router(feedback.router, prefix=api_prefix)
app.include_router(settings_router.router, prefix=api_prefix)
app.include_router(onboarding.router, prefix=api_prefix)
app.include_router(transfer.router, prefix=api_prefix)
app.include_router(pipelines.router, prefix=api_prefix)

# ---------------------------------------------------------------------------
# Serve built frontend as static files (production)
# ---------------------------------------------------------------------------
frontend_path = Path(settings.frontend_dist_dir)
if frontend_path.is_dir():
    # Serve hashed build assets (JS/CSS/images) under /assets/*
    assets_dir = frontend_path / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="frontend-assets",
        )

    index_file = frontend_path / "index.html"

    # SPA fallback: any non-API GET that isn't a real file returns index.html
    # so client-side routes (e.g. /onboarding) work on full-page loads/refresh.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Never hijack API or docs routes
        if (
            full_path.startswith("api/")
            or full_path.startswith("docs")
            or full_path.startswith("redoc")
            or full_path.startswith("openapi.json")
        ):
            raise HTTPException(status_code=404)

        # Serve real static files (favicon.ico, robots.txt, etc.) if present
        candidate = (frontend_path / full_path).resolve()
        try:
            candidate.relative_to(frontend_path.resolve())
        except ValueError:
            raise HTTPException(status_code=404) from None
        if candidate.is_file():
            return FileResponse(candidate)

        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404)
