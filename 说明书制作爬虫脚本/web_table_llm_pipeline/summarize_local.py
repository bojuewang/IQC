from pathlib import Path
import pandas as pd

DATA_PATH = Path("data/raw_table.csv")

if (not DATA_PATH.exists()) or DATA_PATH.stat().st_size == 0:
    print("[summary] raw_table.csv is empty. No table was scraped.")
    print("[hint] The page may require login, or the data is rendered in a non-table structure.")
    raise SystemExit(0)

df = pd.read_csv(DATA_PATH)

if df.empty:
    print("[summary] CSV loaded but contains zero rows.")
    raise SystemExit(0)

print(df.head())
