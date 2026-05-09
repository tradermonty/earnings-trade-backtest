#!/bin/bash
# ============================================================
# Paper Trading Dry-Run — Cron Wrapper
#
# Runs the full paper trading pipeline in dry-run mode.
# No real orders are placed. Candidates and decisions are logged.
#
# Timezone: All times are PDT (UTC-7). ET = PDT + 3h.
#
# Cron Schedule (PDT — add to crontab):
#   # BMO screen: 6:00 AM PDT = 9:00 AM ET
#   0 6 * * 1-5 /path/to/scripts/cron_paper_dryrun.sh bmo
#
#   # Execute dry-run: 6:30 AM PDT = 9:30 AM ET
#   30 6 * * 1-5 /path/to/scripts/cron_paper_dryrun.sh execute
#
#   # AMC screen: 1:00 PM PDT = 4:00 PM ET
#   0 13 * * 1-5 /path/to/scripts/cron_paper_dryrun.sh amc
#
#   # Exit monitor dry-run: 1:05 PM PDT = 4:05 PM ET
#   5 13 * * 1-5 /path/to/scripts/cron_paper_dryrun.sh exit
#
# Quick install:
#   ./scripts/cron_paper_dryrun.sh install
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="${PROJECT_DIR}/venv311"
PYTHON="${VENV_DIR}/bin/python"
LOG_DIR="${PROJECT_DIR}/logs/paper_dryrun"
DRYRUN_STATE_DIR="${PROJECT_DIR}/data/dryrun"
DATE=$(date '+%Y-%m-%d')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')

# Ensure log and dry-run state directories exist before any python invocation.
# Phase 3b: dry-run uses a separate state dir so the screen→execute→exit
# handoff works without touching live state at data/.
mkdir -p "$LOG_DIR"
mkdir -p "$DRYRUN_STATE_DIR"

MODE="${1:-help}"

log() {
    echo "[$TIMESTAMP] $1" | tee -a "${LOG_DIR}/${DATE}.log"
}

case "$MODE" in
    bmo)
        log "=== BMO Screen ==="
        "$PYTHON" "${SCRIPT_DIR}/paper_auto_entry.py" --screen-bmo --dry-run \
            >> "${LOG_DIR}/${DATE}.log" 2>&1
        log "BMO screen complete"
        ;;

    execute)
        log "=== Execute Dry-Run ==="
        "$PYTHON" "${SCRIPT_DIR}/paper_auto_entry.py" --execute --dry-run \
            >> "${LOG_DIR}/${DATE}.log" 2>&1
        log "Execute dry-run complete"
        ;;

    amc)
        log "=== AMC Screen ==="
        "$PYTHON" "${SCRIPT_DIR}/paper_auto_entry.py" --screen-amc --dry-run \
            >> "${LOG_DIR}/${DATE}.log" 2>&1
        log "AMC screen complete"
        ;;

    reconcile)
        # Phase 3b/Phase 3d: post-09:30-fill reconciliation. Discovers orders
        # that returned `accepted` at 09:30 but filled later. Runs at 16:03 ET
        # (between AMC screen at 16:00 and exit monitor at 16:05) to ensure
        # the exit monitor sees the latest filled positions. In dry-run mode
        # this is a no-op (DryRunAccount fills are immediate).
        log "=== Reconcile Pending Orders Dry-Run ==="
        "$PYTHON" "${SCRIPT_DIR}/reconcile_pending_orders.py" --dry-run \
            >> "${LOG_DIR}/${DATE}.log" 2>&1
        log "Reconcile dry-run complete"
        ;;

    exit)
        log "=== Exit Monitor Dry-Run ==="
        "$PYTHON" "${SCRIPT_DIR}/paper_exit_monitor.py" --dry-run \
            >> "${LOG_DIR}/${DATE}.log" 2>&1
        log "Exit monitor dry-run complete"
        ;;

    install)
        echo "Installing cron jobs for paper trading dry-run..."
        # Remove any existing paper dryrun cron entries
        crontab -l 2>/dev/null | grep -v "cron_paper_dryrun" > /tmp/crontab_clean || true

        cat >> /tmp/crontab_clean << CRON
# Paper Trading Dry-Run (PDT times, ET = PDT + 3h)
0 6 * * 1-5 ${SCRIPT_DIR}/cron_paper_dryrun.sh bmo
30 6 * * 1-5 ${SCRIPT_DIR}/cron_paper_dryrun.sh execute
0 13 * * 1-5 ${SCRIPT_DIR}/cron_paper_dryrun.sh amc
3 13 * * 1-5 ${SCRIPT_DIR}/cron_paper_dryrun.sh reconcile
5 13 * * 1-5 ${SCRIPT_DIR}/cron_paper_dryrun.sh exit
CRON

        crontab /tmp/crontab_clean
        rm /tmp/crontab_clean
        echo "Cron jobs installed. Verify with: crontab -l"
        crontab -l | grep "paper_dryrun"
        ;;

    status)
        echo "=== Paper Dry-Run Logs ==="
        ls -lt "${LOG_DIR}"/*.log 2>/dev/null | head -10
        echo ""
        if [ -f "${LOG_DIR}/${DATE}.log" ]; then
            echo "=== Today's Log (${DATE}) ==="
            cat "${LOG_DIR}/${DATE}.log"
        else
            echo "No log for today yet."
        fi
        ;;

    help|*)
        echo "Usage: $0 {bmo|execute|amc|reconcile|exit|install|status}"
        echo ""
        echo "  bmo        - Screen BMO candidates (9:00 AM ET / 6:00 AM PDT)"
        echo "  execute    - Dry-run execute pending (9:30 AM ET / 6:30 AM PDT)"
        echo "  amc        - Screen AMC candidates (4:00 PM ET / 1:00 PM PDT)"
        echo "  reconcile  - Reconcile pending orders (4:03 PM ET / 1:03 PM PDT)"
        echo "  exit       - Dry-run exit monitor (4:05 PM ET / 1:05 PM PDT)"
        echo "  install    - Install cron jobs"
        echo "  status     - Show recent logs"
        ;;
esac
