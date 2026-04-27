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
