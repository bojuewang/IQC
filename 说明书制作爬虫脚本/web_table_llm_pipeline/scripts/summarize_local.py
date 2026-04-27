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
