"""Measure the entry gate against the live Decisions API, by hand.

Two questions the offline suite cannot answer, because both need a real key:

    # Does the API accept a long entry, and what does it bill for it?
    python -m backend.scripts.entry_gate_probe --synthetic-words 4000

    # What P(yes) does the gate give the journal entries already on file?
    python -m backend.scripts.entry_gate_probe --survey

Every call is a real, billed request (fractions of a cent each). Output is
lengths, token counts and probabilities only — never entry text — so it can be
pasted into a task log as it stands. ``--survey`` reads the database named by
``DATABASE_URL`` and writes nothing to it.
"""

import argparse
import asyncio
import sys
import time

from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import session_scope
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.prompts import entry_gate
from backend.app.services.llm.decisions import (
    DecisionsClient,
    DecisionsError,
    build_request,
    noul,
    parse_noul_response,
)

# Generous: a measurement should show the API's own limit, not this one's.
_PROBE_TIMEOUT_SECONDS = 30.0

_SYNTHETIC_SENTENCE = (
    "Today I traced a deadlock in our Go worker pool to an unbuffered channel "
    "that two goroutines both waited on while holding the same mutex. "
)


def _synthetic_entry(words: int) -> str:
    per_sentence = len(_SYNTHETIC_SENTENCE.split())
    return (_SYNTHETIC_SENTENCE * (words // per_sentence + 1)).strip()


async def _ask_raw(client: DecisionsClient, state: str) -> str:
    """One call, reported in full: unlike ``ask_noul`` this shows the failure."""
    start = time.monotonic()
    try:
        payload = build_request(state, {"q": noul(entry_gate.QUESTION)}, client.model)
        status, body = await client._post(payload)
    except Exception as e:  # noqa: BLE001 — a probe reports, it does not recover
        return f"transport error: {type(e).__name__}: {e}"
    ms = int((time.monotonic() - start) * 1000)
    try:
        decision = parse_noul_response(body, "q")
    except DecisionsError as e:
        return f"http={status} {ms}ms unreadable: {e}"
    return (
        f"http={status} {ms}ms p_yes={decision.p_yes:.3f} in={decision.input_tokens} "
        f"out={decision.output_tokens} cost=${decision.cost:.6f} model={decision.model}"
    )


async def _synthetic(client: DecisionsClient, words: int) -> None:
    state = _synthetic_entry(words)
    print(f"synthetic words={len(state.split())} chars={len(state)}")
    print(await _ask_raw(client, state))


async def _survey(client: DecisionsClient) -> None:
    async with session_scope() as db:
        rows = await db.execute(
            select(JournalEntryVersion.content)
            .join(JournalEntry, JournalEntry.id == JournalEntryVersion.entry_id)
            .where(JournalEntryVersion.is_current == True)  # noqa: E712
            .order_by(JournalEntry.created_at)
        )
        contents = list(rows.scalars().all())
    print(f"entries={len(contents)} threshold={settings.llm_entry_gate_threshold}")
    for i, content in enumerate(contents, 1):
        result = await _ask_raw(client, content)
        print(f"#{i} words={len(content.split())} chars={len(content)} {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic-words", type=int, metavar="N")
    mode.add_argument("--survey", action="store_true")
    args = parser.parse_args()

    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set; nothing was sent.", file=sys.stderr)
        return 2
    client = DecisionsClient(timeout=_PROBE_TIMEOUT_SECONDS)
    if args.survey:
        asyncio.run(_survey(client))
    else:
        asyncio.run(_synthetic(client, args.synthetic_words))
    return 0


if __name__ == "__main__":
    sys.exit(main())
