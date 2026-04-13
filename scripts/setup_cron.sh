#!/usr/bin/env bash
# =============================================================================
# DevLog+ — Cron Job Setup Script
#
# Installs crontab entries for:
#   - Nightly profile update (2:00 AM)
#   - Weekly quiz generation (Monday 3:00 AM)
#   - Weekly reading generation (Monday 3:30 AM)
#   - Weekly project generation (Monday 4:00 AM)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "DevLog+ Cron Setup"
echo "=================="
echo ""

# Check for cron availability
if ! command -v crontab &>/dev/null; then
    echo "⚠️  WARNING: crontab command not found."
    echo "   Cron is required for scheduled tasks (nightly updates, weekly quizzes/readings/projects)."
    echo "   Install cron for your system:"
    echo "     - Debian/Ubuntu: sudo apt install cron"
    echo "     - RHEL/Fedora:   sudo dnf install cronie"
    echo "     - macOS:         cron is available by default"
    echo ""
    exit 1
fi

echo "✅ crontab available"
echo ""

# Define cron entries
DOCKER_CMD="cd ${PROJECT_DIR} && docker compose exec -T app"
CRON_ENTRIES=(
    "0 2 * * * ${DOCKER_CMD} python -m backend.app.pipelines.profile_update  # DevLog+ nightly profile update"
    "0 3 * * 1 ${DOCKER_CMD} python -m backend.app.pipelines.quiz_pipeline   # DevLog+ weekly quiz generation"
    "30 3 * * 1 ${DOCKER_CMD} python -m backend.app.pipelines.reading_pipeline # DevLog+ weekly reading generation"
    "0 4 * * 1 ${DOCKER_CMD} python -m backend.app.pipelines.project_pipeline  # DevLog+ weekly project generation"
)

echo "The following cron entries will be added:"
echo ""
for entry in "${CRON_ENTRIES[@]}"; do
    echo "  $entry"
done
echo ""

read -p "Install these crontab entries? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Preserve existing crontab, remove old DevLog+ entries, add new ones
    (crontab -l 2>/dev/null | grep -v "DevLog+" || true; printf "%s\n" "${CRON_ENTRIES[@]}") | crontab -
    echo "✅ Cron entries installed successfully."
    echo ""
    echo "Current crontab:"
    crontab -l | grep "DevLog+"
else
    echo "Skipped. You can run this script again later or add entries manually."
fi
