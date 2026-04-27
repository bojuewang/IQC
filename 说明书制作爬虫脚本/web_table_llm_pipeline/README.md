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
