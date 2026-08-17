"""MCP server for DevLog+ — exposes journal, profile, triage, and project data.

Run as a standalone process (stdio transport) for Claude Code integration:
    poetry run python -m backend.app.mcp_server
"""

import json
import logging
import sys
import uuid

from mcp.server.fastmcp import FastMCP

from backend.app.database import session_scope
from backend.app.models.base import TriageStatus
from backend.app.schemas.journal import JournalEntryCreate
from backend.app.schemas.triage import TriageResolveRequest
from backend.app.services import journal as journal_svc
from backend.app.services import profile as profile_svc
from backend.app.services import project as project_svc
from backend.app.services import triage as triage_svc

logger = logging.getLogger(__name__)

mcp = FastMCP("DevLog+")


def reroute_stdout_logging() -> None:
    """Move any stdout log handler to stderr.

    Under the stdio transport, stdout *is* the JSON-RPC channel — it carries
    one message per line and shares it with nothing. Anything else printed
    there lands mid-stream and the client fails to parse the response.

    SQLAlchemy is the live offender: ``database.py`` passes
    ``echo=(app_env == "development")``, and echo installs a
    ``StreamHandler(sys.stdout)`` (``sqlalchemy.log._add_default_handler``).
    With APP_ENV=development every statement the server runs is interleaved
    into its own replies.

    Handlers are redirected rather than removed, so the logging is still there
    on stderr when you run the server by hand to debug it. Written as a sweep
    over every handler rather than a SQLAlchemy special case, because the next
    library to log to stdout would break the protocol the same way.
    """
    loggers = [logging.getLogger()]
    loggers += [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    for log in loggers:
        for handler in list(getattr(log, "handlers", ())):
            if getattr(handler, "stream", None) is sys.stdout:
                handler.setStream(sys.stderr)


# ---------------------------------------------------------------------------
# Resources (read-only)
# ---------------------------------------------------------------------------


@mcp.resource("devlog://profile")
async def get_profile() -> str:
    """Current Knowledge Profile — topics grouped by category."""
    async with session_scope() as session:
        profile = await profile_svc.get_knowledge_profile(session)
        return profile.model_dump_json(indent=2)


@mcp.resource("devlog://journal")
async def get_journal() -> str:
    """Recent journal entries (last 10, most recent first)."""
    async with session_scope() as session:
        entries = await journal_svc.list_entries(session, limit=10)
        responses = [journal_svc.entry_to_response(e) for e in entries]
        data = [r.model_dump(mode="json") for r in responses]
        return json.dumps(data, indent=2, default=str)


@mcp.resource("devlog://triage")
async def get_triage() -> str:
    """Pending triage items awaiting user review (critical/high first)."""
    async with session_scope() as session:
        items = await triage_svc.list_triage_items(session, status=TriageStatus.PENDING, limit=50)
        data = [
            {
                "id": str(item.id),
                "source": item.source,
                "title": item.title,
                "description": item.description,
                "severity": item.severity,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ]
        return json.dumps(data, indent=2)


@mcp.resource("devlog://projects/current")
async def get_current_project() -> str:
    """Current active weekly Go project with its tasks."""
    async with session_scope() as session:
        project = await project_svc.get_current_project(session)
        if project is None:
            return json.dumps({"message": "No active project found."})
        data = {
            "id": str(project.id),
            "title": project.title,
            "description": project.description,
            "difficulty_level": project.difficulty_level,
            "status": project.status,
            "issued_at": project.issued_at.isoformat() if project.issued_at else None,
            "tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "description": t.description,
                    "type": t.task_type,
                    "order_index": t.order_index,
                }
                for t in (project.tasks or [])
            ],
        }
        return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tools (actions with side effects)
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_journal_entry(content: str, title: str | None = None) -> str:
    """Create a new DevLog+ journal entry.

    Args:
        content: Entry text — plain text only, no HTML. At least one character.
        title: Optional short title (e.g. "Learning Go channels").
    """
    data = JournalEntryCreate(title=title, content=content)
    async with session_scope() as session:
        entry = await journal_svc.create_entry(session, data)
        await session.commit()
        response = journal_svc.entry_to_response(entry)
        label = response.title or "(untitled)"
        return f"Created journal entry {response.id}: {label}"


@mcp.tool()
async def trigger_profile_update() -> str:
    """Run the profile-update pipeline.

    Processes unprocessed journal entries, extracts topics via LLM, and
    updates the Knowledge Profile. Skips if blocking triage items exist.
    Returns a JSON summary of what was processed.
    """
    from backend.app.pipelines.profile_update import run_profile_update

    async with session_scope() as session:
        result = await run_profile_update(session)
        await session.commit()
        return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def resolve_triage(item_id: str, action: str, resolution_text: str | None = None) -> str:
    """Resolve a pending triage item.

    Args:
        item_id: UUID of the triage item (copy from devlog://triage).
        action: One of: accepted, rejected, edited, deferred.
        resolution_text: Required when action is 'edited' (corrected value);
                         optional for other actions.
    """
    try:
        uid = uuid.UUID(item_id)
    except ValueError:
        return f"Invalid item_id {item_id!r} — must be a valid UUID."

    valid_actions = [s.value for s in TriageStatus if s != TriageStatus.PENDING]
    try:
        status = TriageStatus(action)
    except ValueError:
        return f"Invalid action {action!r}. Choose from: {', '.join(valid_actions)}"

    if status == TriageStatus.PENDING:
        return f"Invalid action {action!r}. Choose from: {', '.join(valid_actions)}"

    data = TriageResolveRequest(action=status, resolution_text=resolution_text)
    async with session_scope() as session:
        item = await triage_svc.resolve_triage_item(session, uid, data)
        await session.commit()
        if item is None:
            return f"Triage item {item_id} not found."
        return f"Resolved: [{item.severity}] {item.title} → {item.status}"


if __name__ == "__main__":
    # Must run before the first response is written, and after the imports
    # above have created the engine that installs the offending handler.
    reroute_stdout_logging()
    mcp.run()
