#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate

URL="${1:-}"
MAX_PAGES="${2:-653}"
HEADLESS_FLAG="${3:-}"

if [ -z "$URL" ]; then
  echo "用法："
  echo "  ./run_pipeline.sh '网页URL' 653"
  echo "  ./run_pipeline.sh '网页URL' 653 --headless"
  exit 1
fi

echo "[1/4] 爬虫读取页面信息"
if [ "$HEADLESS_FLAG" = "--headless" ]; then
  python scripts/scrape.py --url "$URL" --max-pages "$MAX_PAGES" --out data/raw_table.csv --headless | tee logs/scrape.log
else
  python scripts/scrape.py --url "$URL" --max-pages "$MAX_PAGES" --out data/raw_table.csv | tee logs/scrape.log
fi

echo "[2/4] 本地中转保存"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp data/raw_table.csv "data/raw_table_backup_${TIMESTAMP}.csv"

echo "[3/4] 汇总所有信息"
python scripts/summarize_local.py | tee logs/summary.log

echo "[4/4] 调用大语言模型 API 生成笔记"
python scripts/llm_note.py | tee logs/llm.log

echo ""
echo "Pipeline finished. 输出文件："
echo "  data/raw_table.csv"
echo "  data/raw_table_backup_${TIMESTAMP}.csv"
echo "  notes/local_summary.md"
echo "  notes/llm_note.md"
