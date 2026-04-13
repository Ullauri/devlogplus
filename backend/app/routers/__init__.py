"""Re-export all routers for convenient import in main.py."""

from backend.app.routers import (
    feedback,
    journal,
    onboarding,
    profile,
    project,
    quiz,
    reading,
    settings,
    triage,
)

__all__ = [
    "feedback",
    "journal",
    "onboarding",
    "profile",
    "project",
    "quiz",
    "reading",
    "settings",
    "triage",
]
