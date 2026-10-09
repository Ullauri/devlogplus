"""Jev through OpenRouter's Decisions API — a cheap closed classifier.

Jev (TypeSafe's ``typesafe/jev-1.13``) generates no text. A request carries a
``state`` (plain text) and typed ``questions``; the answer is a calibrated
probability per question. This client asks only ``noul`` (yes/no) questions,
which come back as P(yes), and the pipelines use that to decide whether an
expensive chat-completion call is worth making at all.

Wire facts, carried in from homechan's ``brain/jev.py`` (verified there
2026-09-20): POST ``https://openrouter.ai/api/alpha/decisions``, bearer
OpenRouter key, $0.042 per million input tokens, output free, 0.2-0.9 s a
call. The API is marked alpha, so every call fails soft: no key, a timeout,
an HTTP error or a body this module cannot read all mean "no opinion"
(``None``), and the caller falls back to what it did before the gate existed.

Request building and response parsing are pure functions, tested offline.
``DecisionsClient._post`` is the one place that touches the network — the
test suite's autouse ``_no_real_decisions_calls`` fixture replaces it.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.config import settings
from backend.app.services.llm.tracing import trace_llm_call

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

# Pinned rather than configurable: the threshold the pipelines compare
# against is only meaningful for the model whose probabilities it was set
# from, and the API is alpha — a new version is a recalibration, not a swap.
JEV_MODEL = "typesafe/jev-1.13"

# Total wall-clock budget for one call, connection included. The gate sits in
# front of a call that takes seconds; it must never cost more than it saves.
DECISIONS_TIMEOUT_SECONDS = 3.0


class DecisionsError(Exception):
    """The API answered with an error body or a shape this module cannot read."""


@dataclass(frozen=True)
class NoulDecision:
    """One answered yes/no question, with what it cost."""

    p_yes: float
    input_tokens: int
    output_tokens: int
    cost: float
    model: str


def noul(instructions: str) -> dict[str, str]:
    """A yes/no question; the answer is P(yes)."""
    return {"type": "noul", "instructions": instructions}


def build_request(state: str, questions: dict[str, dict[str, str]], model: str = JEV_MODEL) -> dict:
    """The Decisions request body: the text to judge and the questions about it."""
    if not questions:
        raise ValueError("a decisions request needs at least one question")
    return {"model": model, "state": state, "questions": questions}


def parse_noul_response(body: Any, key: str) -> NoulDecision:
    """Read the answer to the ``noul`` question *key* out of a response body.

    Raises ``DecisionsError`` on an error body, a missing answer, an answer
    of another type, or a probability outside 0..1.
    """
    if not isinstance(body, dict):
        raise DecisionsError("response is not an object")
    if "error" in body:
        err = body["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        raise DecisionsError(f"api error: {msg}")
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise DecisionsError("response has no answers")
    answer = answers.get(key)
    if not isinstance(answer, dict):
        raise DecisionsError(f"response has no answer for {key!r}")
    if answer.get("type") != "noul":
        raise DecisionsError(f"answer {key!r} has type {answer.get('type')!r}, expected 'noul'")
    try:
        p_yes = float(answer["noul"])
    except (KeyError, TypeError, ValueError) as e:
        raise DecisionsError(f"answer {key!r} carries no readable probability") from e
    if not 0.0 <= p_yes <= 1.0:
        raise DecisionsError(f"answer {key!r} probability {p_yes} is outside 0..1")

    usage = body.get("usage") or {}
    try:
        return NoulDecision(
            p_yes=p_yes,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cost=float(usage.get("cost") or 0.0),
            model=str(body.get("model") or ""),
        )
    except (AttributeError, TypeError, ValueError) as e:
        raise DecisionsError("response usage is unreadable") from e


class DecisionsClient:
    """Asks Jev one yes/no question at a time; ``None`` whenever it cannot."""

    _QUESTION_KEY = "q"

    def __init__(
        self,
        *,
        url: str = DECISIONS_URL,
        model: str = JEV_MODEL,
        timeout: float = DECISIONS_TIMEOUT_SECONDS,
    ) -> None:
        self.url = url
        self.model = model
        self.timeout = timeout

    async def _post(self, payload: dict) -> tuple[int, Any]:
        """Send *payload*; return the status and the decoded body.

        The only network touch in this module. Raises on transport errors
        and on a body that is not JSON; ``ask_noul`` turns both into ``None``.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            response = await http.post(
                self.url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
        return response.status_code, response.json()

    async def ask_noul(self, *, pipeline: str, state: str, question: str) -> NoulDecision | None:
        """P(yes) for *question* about *state*, or ``None`` for no opinion.

        Never raises into a pipeline. Logs one INFO line per answered call —
        probability, tokens, cost and milliseconds, never *state*.
        """
        if not settings.openrouter_api_key:
            return None

        payload = build_request(state, {self._QUESTION_KEY: noul(question)}, self.model)
        start = time.monotonic()
        try:
            # Langfuse gets the question and the size of the text, not the
            # text: the gate's whole output is one number, and the entry
            # itself is already traced by the extraction call it guards.
            with trace_llm_call(
                pipeline=pipeline,
                model=self.model,
                input_data={"question": question, "state_chars": len(state)},
            ) as trace:
                async with asyncio.timeout(self.timeout):
                    status, body = await self._post(payload)
                if status >= 400:
                    detail = ""
                    if isinstance(body, dict) and "error" in body:
                        detail = f": {body['error']}"
                    raise DecisionsError(f"http {status}{detail}")
                decision = parse_noul_response(body, self._QUESTION_KEY)
                # Reshaped into the chat-completion fields LLMTrace reads, so
                # the trace carries real usage instead of "?".
                trace.record_output(
                    {
                        "usage": {
                            "prompt_tokens": decision.input_tokens,
                            "completion_tokens": decision.output_tokens,
                            "total_tokens": decision.input_tokens + decision.output_tokens,
                        },
                        "choices": [{"message": {"p_yes": decision.p_yes}}],
                    }
                )
        except TimeoutError:
            logger.warning(
                "Decisions [%s]: timeout after %.1fs — no opinion", pipeline, self.timeout
            )
            return None
        except Exception as e:  # noqa: BLE001 — a classifier must never break a pipeline
            logger.warning("Decisions [%s]: %s — no opinion", pipeline, e)
            return None

        ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Decisions [%s] model=%s p_yes=%.3f in=%d out=%d cost=$%.6f %dms",
            pipeline,
            decision.model or self.model,
            decision.p_yes,
            decision.input_tokens,
            decision.output_tokens,
            decision.cost,
            ms,
        )
        return decision


decisions_client = DecisionsClient()
