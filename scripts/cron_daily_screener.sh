#!/bin/bash
# ============================================================
# Daily Earnings Screener - Cron Job Script
# 日次エントリー候補スクリーナー（cron用）
#
# Usage:
#   ./scripts/cron_daily_screener.sh           # 今日の候補
#   ./scripts/cron_daily_screener.sh 2024-10-24  # 指定日付
#
# Cron設定例 (米国西海岸時間 12:00 PM = JST 翌朝5時):
#   寄り付き前だと決算データの取りこぼしがあるため、マーケット引け後に実行
#   US West Coast 12:00 PM = US East Coast 3:00 PM = JST 翌朝5:00 (冬時間) / 4:00 (夏時間)
#
#   JST (日本標準時) でのcron設定:
#   0 5 * * 2-6 /path/to/scripts/cron_daily_screener.sh >> /path/to/logs/screener.log 2>&1
#
#   PST/PDT (米国西海岸時間) でのcron設定:
#   0 12 * * 1-5 /path/to/scripts/cron_daily_screener.sh >> /path/to/logs/screener.log 2>&1
#
# ============================================================

set -e  # エラー時に停止

# ============================================================
# 設定
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="${PROJECT_DIR}/venv311"
LOG_DIR="${PROJECT_DIR}/logs"
PYTHON_SCRIPT="${SCRIPT_DIR}/screen_daily_candidates.py"

# 日付引数（オプション）
TARGET_DATE="${1:-}"

# ============================================================
# 環境準備
# ============================================================
# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# タイムスタンプ
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "============================================================"
echo "Daily Screener Started: $TIMESTAMP"
echo "============================================================"

# 仮想環境確認
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found: $VENV_DIR"
    exit 1
fi

# Python スクリプト確認
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "ERROR: Python script not found: $PYTHON_SCRIPT"
    exit 1
fi

# ============================================================
# 仮想環境をアクティベート
# ============================================================
source "${VENV_DIR}/bin/activate"

# ============================================================
# スクリーナー実行
# ============================================================
cd "$PROJECT_DIR"

if [ -n "$TARGET_DATE" ]; then
    echo "Running screener for date: $TARGET_DATE"
    python "$PYTHON_SCRIPT" --date "$TARGET_DATE" --verbose
else
    echo "Running screener for today (NY timezone)"
    python "$PYTHON_SCRIPT" --verbose
fi

EXIT_CODE=$?

# ============================================================
# 完了
# ============================================================
END_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo ""
echo "============================================================"
echo "Daily Screener Completed: $END_TIMESTAMP"
echo "Exit Code: $EXIT_CODE"
echo "============================================================"

exit $EXIT_CODE
