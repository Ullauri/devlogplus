"""Architecture tests for DevLog+ backend using pytestarch.

These tests enforce the layered architecture boundaries between packages,
ensuring dependency flow is always downward and no forbidden cross-layer
imports exist.

Dependency layers (allowed direction →):

    pipelines  → services.llm, services, prompts, models, config
    routers    → services, schemas, database, models.base (enums)
    services   → models, schemas
    schemas    → models.base (enums only)
    models     → (self only — models.base)
    prompts    → (nothing — pure string templates)
    config     → (nothing — pure leaf)
    database   → config only
"""

import uuid
from pathlib import Path

import pytest
from pytestarch import Rule, get_evaluable_architecture
from sqlalchemy import text
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Path resolution ─────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # …/devlogplus
_ROOT_PATH = _PROJECT_ROOT / "backend"  # pytestarch root — gives "backend.app.*" names
_MODULE_PATH = _PROJECT_ROOT / "backend" / "app"

# ─── Fully-qualified module name constants ───────────────────────────────────
MODELS = "backend.app.models"
SCHEMAS = "backend.app.schemas"
SERVICES = "backend.app.services"
SERVICES_LLM = "backend.app.services.llm"
ROUTERS = "backend.app.routers"
PIPELINES = "backend.app.pipelines"
PROMPTS = "backend.app.prompts"
CONFIG = "backend.app.config"
DATABASE = "backend.app.database"
MAIN = "backend.app.main"


# ─── Shared fixture ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def evaluable():
    """Build the evaluable architecture graph once per test session."""
    return get_evaluable_architecture(
        str(_ROOT_PATH),
        str(_MODULE_PATH),
    )


# ─── Helper ──────────────────────────────────────────────────────────────────
def _assert_no_import(evaluable, *, source: str, target: str) -> None:
    """Assert that *source* (and its submodules) does not import *target*."""
    rule = (
        Rule().modules_that().are_named(source).should_not().import_modules_that().are_named(target)
    )
    rule.assert_applies(evaluable)


# ═════════════════════════════════════════════════════════════════════════════
# 1. PROMPTS — pure leaf: no internal imports at all
# ═════════════════════════════════════════════════════════════════════════════
class TestPromptsAreLeafPackage:
    """Prompt templates are pure string constants with zero internal deps."""

    @pytest.mark.parametrize(
        "target",
        [MODELS, SCHEMAS, SERVICES, ROUTERS, PIPELINES, DATABASE, CONFIG],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_prompts_do_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=PROMPTS, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 2. MODELS — depend only on themselves (models.base)
# ═════════════════════════════════════════════════════════════════════════════
class TestModelsBoundaries:
    """ORM models only import from models.base — never from higher layers."""

    @pytest.mark.parametrize(
        "target",
        [SCHEMAS, SERVICES, ROUTERS, PIPELINES, PROMPTS, DATABASE, CONFIG],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_models_do_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=MODELS, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 3. SCHEMAS — depend on models.base enums only, never higher layers
# ═════════════════════════════════════════════════════════════════════════════
class TestSchemasBoundaries:
    """Pydantic schemas reference models.base enums only."""

    @pytest.mark.parametrize(
        "target",
        [SERVICES, ROUTERS, PIPELINES, PROMPTS, DATABASE, CONFIG],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_schemas_do_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=SCHEMAS, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 4. SERVICES — depend on models + schemas, never routers/pipelines/prompts
# ═════════════════════════════════════════════════════════════════════════════
class TestServicesBoundaries:
    """Business-logic services never reach up into routers or pipelines."""

    @pytest.mark.parametrize(
        "target",
        [ROUTERS, PIPELINES, PROMPTS, DATABASE],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_services_do_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=SERVICES, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 5. ROUTERS — depend on services + schemas + database, never pipelines/prompts
#
# Exception: ``routers.pipelines`` legitimately launches pipelines from a
# user-initiated HTTP endpoint (the manual "Run now" buttons in the
# Settings page). All other router modules must not import pipelines.
# ══════════════════════════════════════════════════════════════════════════
class TestRoutersBoundaries:
    """API routers never reach into prompt templates.

    Routers generally don't reach into pipelines either — the one
    permitted exception is ``routers.pipelines``, which exposes manual
    "Run now" triggers for the user to bypass cron.
    """

    def test_routers_do_not_import_prompts(self, evaluable) -> None:
        _assert_no_import(evaluable, source=ROUTERS, target=PROMPTS)

    def test_only_routers_pipelines_imports_pipelines(self, evaluable) -> None:
        """Every router module except ``routers.pipelines`` must avoid pipelines."""
        routers_dir = _MODULE_PATH / "routers"
        other_router_modules = [
            f"{ROUTERS}.{p.stem}"
            for p in routers_dir.glob("*.py")
            if p.stem not in ("__init__", "pipelines")
        ]
        for mod in other_router_modules:
            _assert_no_import(evaluable, source=mod, target=PIPELINES)

    def test_routers_do_not_import_domain_models_directly(self, evaluable) -> None:
        """Routers access domain data through services, not ORM models.

        Exception: models.base is allowed (enums used in query params).
        """
        domain_model_modules = [
            f"{MODELS}.journal",
            f"{MODELS}.topic",
            f"{MODELS}.quiz",
            f"{MODELS}.reading",
            f"{MODELS}.project",
            f"{MODELS}.feedback",
            f"{MODELS}.settings",
            f"{MODELS}.triage",
        ]
        for mod in domain_model_modules:
            rule = (
                Rule()
                .modules_that()
                .are_named(ROUTERS)
                .should_not()
                .import_modules_that()
                .are_named(mod)
            )
            rule.assert_applies(evaluable)

    def test_routers_do_not_import_llm_client(self, evaluable) -> None:
        """Routers never call the LLM client directly."""
        _assert_no_import(evaluable, source=ROUTERS, target=SERVICES_LLM)


# ═════════════════════════════════════════════════════════════════════════════
# 6. PIPELINES — top-level orchestrators, never import routers or schemas
# ═════════════════════════════════════════════════════════════════════════════
class TestPipelinesBoundaries:
    """Batch pipelines must not depend on HTTP/API layer."""

    @pytest.mark.parametrize(
        "target",
        [ROUTERS, SCHEMAS, DATABASE],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_pipelines_do_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=PIPELINES, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 7. SERVICES.LLM — isolated from domain; only depends on config + self
# ═════════════════════════════════════════════════════════════════════════════
class TestLlmSubpackageIsolation:
    """The LLM client sub-package is isolated from domain logic."""

    @pytest.mark.parametrize(
        "target",
        [MODELS, SCHEMAS, ROUTERS, PIPELINES, PROMPTS, DATABASE],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_llm_does_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=SERVICES_LLM, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 8. CONFIG & DATABASE — infrastructure leaves
# ═════════════════════════════════════════════════════════════════════════════
class TestInfrastructureLeaves:
    """Config and database are low-level modules that never look upward."""

    @pytest.mark.parametrize(
        "target",
        [MODELS, SCHEMAS, SERVICES, ROUTERS, PIPELINES, PROMPTS],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_config_does_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=CONFIG, target=target)

    @pytest.mark.parametrize(
        "target",
        [MODELS, SCHEMAS, SERVICES, ROUTERS, PIPELINES, PROMPTS],
        ids=lambda t: t.rsplit(".", 1)[-1],
    )
    def test_database_does_not_import(self, evaluable, target: str) -> None:
        _assert_no_import(evaluable, source=DATABASE, target=target)


# ═════════════════════════════════════════════════════════════════════════════
# 9. CROSS-CUTTING — no circular dependencies between major layers
# ═════════════════════════════════════════════════════════════════════════════
class TestNoCyclicDependencies:
    """Verify that no reverse-direction imports exist between layers."""

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (MODELS, SCHEMAS),
            (MODELS, SERVICES),
            (MODELS, ROUTERS),
            (MODELS, PIPELINES),
            (SCHEMAS, SERVICES),
            (SCHEMAS, ROUTERS),
            (SCHEMAS, PIPELINES),
            (SERVICES, ROUTERS),
            (SERVICES, PIPELINES),
        ],
        ids=[
            "models→schemas",
            "models→services",
            "models→routers",
            "models→pipelines",
            "schemas→services",
            "schemas→routers",
            "schemas→pipelines",
            "services→routers",
            "services→pipelines",
        ],
    )
    def test_no_reverse_dependency(self, evaluable, source: str, target: str) -> None:
        _assert_no_import(evaluable, source=source, target=target)

    def test_routers_and_pipelines_are_independent(self, evaluable) -> None:
        """Routers and pipelines exist in parallel — pipelines never imports routers.

        Routers generally don't import pipelines either; the one exception
        is ``routers.pipelines`` (manual "Run now" triggers), which is
        covered by ``TestRoutersBoundaries.test_only_routers_pipelines_imports_pipelines``.
        """
        _assert_no_import(evaluable, source=PIPELINES, target=ROUTERS)


# ═════════════════════════════════════════════════════════════════════════════
# 10. ENUM VALIDATION — invalid DB values must be caught at read time
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio(loop_scope="session")
class TestEnumValidation:
    """validate_strings=True on all SAEnum columns raises on bad DB values.

    Bug (Issue #6): validate_strings=False silently created an invalid enum
    member for any unrecognised string coming from the DB. Changing to
    validate_strings=True causes SQLAlchemy to raise a LookupError at the ORM
    read boundary (may be wrapped in StatementError depending on SA version),
    making the failure visible.
    """

    async def test_invalid_enum_string_raises_on_orm_load(self, db_session: AsyncSession) -> None:
        """Insert a row with an unknown quiz_session status, then try to load it via ORM.

        This must raise LookupError (or StatementError wrapping it) rather than
        silently returning a broken enum member.
        """
        bad_id = uuid.uuid4()
        # Write directly via raw SQL to bypass Python-level validation.
        await db_session.execute(
            text(
                "INSERT INTO quiz_sessions "
                "(id, status, question_count, created_at, updated_at) "
                "VALUES (:id, 'totally_invalid_status', 1, now(), now())"
            ),
            {"id": bad_id},
        )
        await db_session.flush()

        # Now try to read the row through SQLAlchemy ORM — this is where
        # validate_strings=True (the fix) should raise.
        from sqlalchemy import select as sa_select

        from backend.app.models.quiz import QuizSession

        stmt = sa_select(QuizSession).where(QuizSession.id == bad_id)
        with pytest.raises((LookupError, StatementError)):
            result = await db_session.execute(stmt)
            result.scalars().all()  # materialise the rows to trigger enum coercion
