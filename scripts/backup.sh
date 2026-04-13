#!/usr/bin/env bash
# =============================================================================
# DevLog+ — Data Backup Script
#
# Backs up all user data:
#   1. PostgreSQL database (via pg_dump)
#   2. workspace/projects/ directory (generated Go micro-projects)
#
# Usage:
#   ./scripts/backup.sh                  # uses DATABASE_URL from .env
#   DATABASE_URL=... ./scripts/backup.sh # explicit override
#
# Output: backups/<timestamp>/ containing:
#   - devlogplus.sql    (full database dump)
#   - projects.tar.gz   (workspace/projects/ archive, if non-empty)
#   - backup.meta       (metadata: timestamp, db url hint, sizes)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_ROOT="$PROJECT_ROOT/backups"
WORKSPACE_DIR="$PROJECT_ROOT/workspace/projects"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

# ── Load .env if present ─────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]] && [[ -f "$PROJECT_ROOT/.env" ]]; then
    # shellcheck disable=SC2046
    export $(grep -v '^\s*#' "$PROJECT_ROOT/.env" | grep 'DATABASE_URL' | xargs)
fi

DATABASE_URL="${DATABASE_URL:-}"

if [[ -z "$DATABASE_URL" ]]; then
    echo "❌ DATABASE_URL is not set. Set it in .env or pass it as an env var."
    exit 1
fi

# ── Parse DATABASE_URL ───────────────────────────────────────────────
# Format: postgresql+asyncpg://user:pass@host:port/dbname
# Strip the +asyncpg dialect so we get a plain postgres:// URL for pg_dump
PG_URL="$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')"

# Extract components for display (mask password)
DB_HOST="$(echo "$PG_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')"
DB_NAME="$(echo "$PG_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')"

# ── Create backup directory ──────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "═══════════════════════════════════════════════════"
echo "  DevLog+ — Backup"
echo "  Timestamp : $TIMESTAMP"
echo "  Target    : backups/$TIMESTAMP/"
echo "  Database  : $DB_NAME @ $DB_HOST"
echo "═══════════════════════════════════════════════════"
echo ""

# ── 1. Database dump ─────────────────────────────────────────────────
echo "▶ Dumping database…"
if ! command -v pg_dump &>/dev/null; then
    echo "  ❌ pg_dump not found. Install it with: sudo apt install postgresql-client"
    rm -rf "$BACKUP_DIR"
    exit 1
fi

if ! pg_dump "$PG_URL" --format=plain --no-owner --no-acl > "$BACKUP_DIR/devlogplus.sql" 2>&1; then
    echo "  ❌ pg_dump failed — is PostgreSQL running and reachable at $DB_HOST?"
    echo "     Backup aborted. Your data has NOT been modified."
    rm -rf "$BACKUP_DIR"
    exit 1
fi

DB_SIZE="$(du -h "$BACKUP_DIR/devlogplus.sql" | cut -f1)"
echo "  ✅ Database dump: $DB_SIZE (devlogplus.sql)"

# ── 2. Workspace projects archive ────────────────────────────────────
echo "▶ Archiving workspace/projects…"
if [[ -d "$WORKSPACE_DIR" ]] && [[ -n "$(ls -A "$WORKSPACE_DIR" 2>/dev/null)" ]]; then
    tar -czf "$BACKUP_DIR/projects.tar.gz" -C "$PROJECT_ROOT" workspace/projects/
    PROJ_SIZE="$(du -h "$BACKUP_DIR/projects.tar.gz" | cut -f1)"
    echo "  ✅ Projects archive: $PROJ_SIZE (projects.tar.gz)"
else
    PROJ_SIZE="EMPTY"
    echo "  ℹ️  workspace/projects/ is empty — nothing to archive."
fi

# ── 3. Metadata file ────────────────────────────────────────────────
cat > "$BACKUP_DIR/backup.meta" <<EOF
timestamp=$TIMESTAMP
database_host=$DB_HOST
database_name=$DB_NAME
database_dump_size=$DB_SIZE
projects_archive_size=$PROJ_SIZE
EOF

echo ""
echo "✅ Backup complete → backups/$TIMESTAMP/"
echo ""

# ── Prune old backups (keep last 10) ────────────────────────────────
BACKUP_COUNT="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)"
if [[ "$BACKUP_COUNT" -gt 10 ]]; then
    PRUNE_COUNT=$((BACKUP_COUNT - 10))
    echo "♻️  Pruning $PRUNE_COUNT old backup(s) (keeping last 10)…"
    find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | head -n "$PRUNE_COUNT" | while read -r dir; do
        rm -rf "$dir"
        echo "   removed $(basename "$dir")"
    done
    echo ""
fi
