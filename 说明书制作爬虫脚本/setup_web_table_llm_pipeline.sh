#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Web Table Scraper + Local Cache + Summary + LLM Note Pipeline
# 功能：
# 1. 爬虫读取分页表格页面信息
# 2. 本地中转保存为 CSV / backup
# 3. pandas 汇总所有字段信息
# 4. 调用 OpenAI API 生成结构化中文笔记，并自动加入 toy example
# ============================================================

PROJECT="web_table_llm_pipeline"
mkdir -p "$PROJECT"/{data,notes,logs,scripts}
cd "$PROJECT"

# -----------------------------
# 0. Python virtual environment
# -----------------------------
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install playwright pandas openai python-dotenv tabulate
playwright install chromium

# -----------------------------
# 1. Environment template
# -----------------------------
cat > .env.example <<'EOF'
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5.5
EOF

# -----------------------------
# 2. Scraper
# -----------------------------
cat > scripts/scrape.py <<'PY'
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pandas as pd
import argparse
import time
from pathlib import Path


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Try to normalize the table columns into a data dictionary schema."""
    if df.shape[1] >= 6:
        df = df.iloc[:, :6]
        df.columns = [
            "field_name",
            "description",
            "data_type",
            "coverage_1",
            "coverage_2",
            "count",
        ]
    else:
        df.columns = [f"col_{i+1}" for i in range(df.shape[1])]
    return df


def scrape_table(url: str, max_pages: int, out_csv: str, headless: bool = False):
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=120_000)

        for page_id in range(max_pages):
            try:
                page.wait_for_selector("table", timeout=60_000)
            except PlaywrightTimeoutError:
                print("No table detected. Stop.")
                break

            rows = page.locator("table tbody tr")
            n = rows.count()

            for i in range(n):
                cells = rows.nth(i).locator("td")
                row = [cells.nth(j).inner_text().strip() for j in range(cells.count())]
                if row:
                    all_rows.append(row)

            print(f"[scrape] page={page_id + 1}, rows={n}, total={len(all_rows)}")

            next_btn = page.locator("text=Next").first
            if next_btn.count() == 0:
                print("[scrape] No Next button found. Stop.")
                break

            try:
                if next_btn.is_disabled():
                    print("[scrape] Next button disabled. Stop.")
                    break
            except Exception:
                pass

            try:
                next_btn.click(timeout=30_000)
            except Exception as e:
                print(f"[scrape] Failed to click Next: {e}")
                break

            time.sleep(1.0)

        browser.close()

    df = pd.DataFrame(all_rows)
    df = normalize_columns(df)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"[scrape] saved: {out_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--max-pages", type=int, default=653)
    parser.add_argument("--out", default="data/raw_table.csv")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    scrape_table(
        url=args.url,
        max_pages=args.max_pages,
        out_csv=args.out,
        headless=args.headless,
    )
PY

# -----------------------------
# 3. Local summary
# -----------------------------
cat > scripts/summarize_local.py <<'PY'
import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/raw_table.csv")
OUT_PATH = Path("notes/local_summary.md")

if not DATA_PATH.exists():
    raise FileNotFoundError("data/raw_table.csv not found. Run scraper first.")

df = pd.read_csv(DATA_PATH)
summary = []

summary.append("# Local Summary")
summary.append("")
summary.append(f"Total rows: {len(df)}")
summary.append(f"Total columns: {df.shape[1]}")
summary.append(f"Columns: `{list(df.columns)}`")

if "data_type" in df.columns:
    summary.append("\n## Data Type Counts\n")
    summary.append(df["data_type"].value_counts(dropna=False).to_markdown())

if "coverage_2" in df.columns:
    missing_cov2 = (df["coverage_2"].astype(str).str.strip() == "—").sum()
    summary.append("\n## Coverage Diagnostics\n")
    summary.append(f"Rows with missing coverage_2 marked as `—`: {missing_cov2}")

keywords = [
    "sales", "revenue", "currency", "estimation", "estimate", "broker",
    "income", "netincome", "forecast", "revision", "value", "price", "volume"
]

summary.append("\n## Keyword Groups\n")
for kw in keywords:
    mask = df.astype(str).apply(
        lambda col: col.str.contains(kw, case=False, na=False)
    ).any(axis=1)
    sub = df[mask]
    summary.append(f"\n### `{kw}`")
    summary.append(f"Count: {len(sub)}")
    if len(sub) > 0:
        summary.append(sub.head(20).to_markdown(index=False))

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text("\n".join(summary), encoding="utf-8")
print(f"[summary] saved: {OUT_PATH}")
PY

# -----------------------------
# 4. LLM note generator
# -----------------------------
cat > scripts/llm_note.py <<'PY'
import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "your_api_key_here":
    raise RuntimeError("Please set OPENAI_API_KEY in .env")

model = os.getenv("OPENAI_MODEL", "gpt-5.5")
client = OpenAI(api_key=api_key)

df = pd.read_csv("data/raw_table.csv")
local_summary = Path("notes/local_summary.md").read_text(encoding="utf-8")

# Keep prompt compact enough for API use.
sample_rows = df.head(100).to_markdown(index=False)

prompt = f"""
你是一个量化研究助理和数据字典分析专家。

下面是一批金融数据字段字典的本地汇总和样例行。
请生成一份结构化中文笔记，要求使用 Markdown。

笔记结构：

# 金融字段字典爬取结果笔记

## 1. 页面信息整体结构
解释 field_name, description, data_type, coverage, count 这类字段的意义。

## 2. 字段经济含义分类
至少包括：
- sales / revenue
- currency
- analyst estimate
- broker information
- income statement
- forecast / revision
- price / value / volume

## 3. Vector 与 Matrix 的解释
从数据结构角度解释 Vector 和 Matrix 可能分别代表什么。

## 4. 从字段字典到 alpha factor mining
解释如何把字段字典转化为 feature universe。

## 5. Toy Example
给一个小表格，例如：
- actual_sales_value_quarterly
- an14_adjusted_netincome_ft
- an14_ads1detailafv110_estvalue
- actuals_reporting_currency

然后给出一个简单 alpha 原型，例如：
alpha = normalized(estimate_revision_signal) * liquidity_filter
并解释每个变量如何由字段构造。

## 6. Pipeline 后续改造建议
包括：去重、字段分类器、异常字段检测、LLM 自动标签、进入 backtest。

Local summary:
{local_summary}

Sample rows:
{sample_rows}
"""

response = client.responses.create(
    model=model,
    input=prompt,
)

note = response.output_text
Path("notes/llm_note.md").write_text(note, encoding="utf-8")
print("[llm] saved: notes/llm_note.md")
PY

# -----------------------------
# 5. Pipeline runner
# -----------------------------
cat > run_pipeline.sh <<'RUN'
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
RUN

chmod +x run_pipeline.sh

# -----------------------------
# 6. README
# -----------------------------
cat > README.md <<'EOF'
# Web Table + LLM Note Pipeline 使用说明书

本项目用于把一个「分页表格型网页」自动转化为可分析的数据字典，并进一步调用大语言模型生成结构化中文笔记。

核心流程：

```text
网页 URL
  → Playwright 爬虫读取 table
  → 保存 data/raw_table.csv
  → pandas 本地汇总 notes/local_summary.md
  → OpenAI API 归纳总结 notes/llm_note.md
```

---

## 1. 项目结构

运行 `setup_web_table_llm_pipeline.sh` 后，会生成：

```text
web_table_llm_pipeline/
├── .venv/                         # Python 虚拟环境
├── .env.example                   # API key 模板
├── README.md                      # 使用说明
├── run_pipeline.sh                # 主运行脚本
├── data/
│   ├── raw_table.csv              # 爬虫抓取的原始表格
│   └── raw_table_backup_*.csv     # 每次运行的备份
├── notes/
│   ├── local_summary.md           # pandas 本地统计总结
│   └── llm_note.md                # LLM 生成的中文笔记
├── logs/
│   ├── scrape.log                 # 爬虫日志
│   ├── summary.log                # 汇总日志
│   └── llm.log                    # LLM 调用日志
└── scripts/
    ├── scrape.py                  # 网页表格爬虫
    ├── summarize_local.py         # 本地汇总脚本
    └── llm_note.py                # LLM 笔记生成脚本
```

---

## 2. 安装与初始化

先保存并运行总安装脚本：

```bash
chmod +x setup_web_table_llm_pipeline.sh
./setup_web_table_llm_pipeline.sh
```

进入项目目录：

```bash
cd web_table_llm_pipeline
```

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
nano .env
```

填入：

```bash
OPENAI_API_KEY=你的 OpenAI API Key
OPENAI_MODEL=gpt-5.5
```

---

## 3. 运行 pipeline

普通运行：

```bash
./run_pipeline.sh "网页URL" 653
```

其中：

- `网页URL` 是目标页面地址；
- `653` 是最大分页数，可改成更小数字先测试；
- 第三参数可选 `--headless`，表示不打开浏览器窗口。

例如先测试前 3 页：

```bash
./run_pipeline.sh "https://example.com/table-page" 3
```

无界面运行：

```bash
./run_pipeline.sh "https://example.com/table-page" 653 --headless
```

---

## 4. 输出文件说明

### `data/raw_table.csv`

爬虫抓到的原始表格数据。若页面表格至少有 6 列，脚本会自动命名为：

```text
field_name, description, data_type, coverage_1, coverage_2, count
```

这些字段对应：

- `field_name`：字段名，例如 `actual_sales_value_quarterly`；
- `description`：字段解释；
- `data_type`：字段类型，例如 `Vector` 或 `Matrix`；
- `coverage_1`、`coverage_2`：覆盖率或可用性指标；
- `count`：字段相关数量。

### `notes/local_summary.md`

本地统计摘要，包括：

- 总行数；
- 总列数；
- 数据类型统计；
- coverage 缺失诊断；
- sales / currency / estimate / broker / income 等关键词分组。

### `notes/llm_note.md`

LLM 生成的中文笔记，包括：

- 页面字段结构解释；
- 字段经济含义分类；
- Vector / Matrix 类型解释；
- 如何进入 alpha factor mining；
- toy example；
- 后续 pipeline 改造建议。

---

## 5. 每个脚本的功能

### `scripts/scrape.py`

负责打开网页、读取表格、点击 `Next` 翻页，并把所有行合并保存为 CSV。

核心逻辑：

```text
打开页面
→ 等待 table 出现
→ 读取 tbody tr
→ 读取每个 td
→ 点击 Next
→ 重复直到 max_pages 或没有 Next
```

### `scripts/summarize_local.py`

负责用 pandas 做本地汇总，不依赖 LLM。

它会统计：

- 字段总数；
- Vector / Matrix 等类型数量；
- coverage 缺失；
- 常见金融关键词分组。

### `scripts/llm_note.py`

负责读取 `raw_table.csv` 和 `local_summary.md`，调用 OpenAI API，生成结构化中文研究笔记。

它不会把所有 653 页完整塞进 prompt，而是使用：

```text
local_summary + 前 100 行样例
```

这样更稳定，也更省 token。

### `run_pipeline.sh`

主控制脚本，顺序执行：

```text
[1/4] 爬虫读取页面信息
[2/4] 本地中转保存
[3/4] 汇总所有信息
[4/4] 调用 LLM API 生成笔记
```

---

## 6. 登录页面注意事项

如果网页需要登录，建议第一次不要使用 `--headless`：

```bash
./run_pipeline.sh "网页URL" 3
```

浏览器会弹出。你可以手动登录，然后观察表格是否加载成功。

如果页面登录状态不会自动保存，需要进一步升级为：

```text
persistent browser profile
cookies 保存 / 读取
session storage 保存 / 读取
```

---

## 7. 常见问题

### Q1. 没抓到表格怎么办？

可能原因：

- 页面还没加载完成；
- 表格不是真正的 `<table>`，而是 div grid；
- 需要登录；
- Next 按钮文字不是 `Next`。

需要修改 `scripts/scrape.py` 里的 selector，例如：

```python
page.wait_for_selector("table")
page.locator("table tbody tr")
page.locator("text=Next")
```

### Q2. 页面是 div 表格，不是 table 怎么办？

需要把选择器改成对应的 CSS selector，例如：

```python
rows = page.locator(".data-row")
cells = rows.nth(i).locator(".data-cell")
```

### Q3. API 报错怎么办？

检查 `.env`：

```bash
cat .env
```

确认有：

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.5
```

### Q4. 只想本地总结，不调用 LLM？

可以只运行：

```bash
source .venv/bin/activate
python scripts/scrape.py --url "网页URL" --max-pages 3 --out data/raw_table.csv
python scripts/summarize_local.py
```

---

## 8. 后续升级方向

可以继续升级为：

1. 字段去重模块；
2. 自动字段分类器；
3. 字段质量评分；
4. Vector / Matrix 结构解析；
5. alpha feature universe 自动生成；
6. toy alpha 自动回测；
7. GitHub 自动同步；
8. 定时任务每日更新。
EOF

# -----------------------------
# 7. Final message
# -----------------------------
echo ""
echo "完成搭建：$PROJECT"
echo "下一步："
echo "  cd $PROJECT"
echo "  cp .env.example .env"
echo "  nano .env"
echo "  ./run_pipeline.sh '网页URL' 653"
