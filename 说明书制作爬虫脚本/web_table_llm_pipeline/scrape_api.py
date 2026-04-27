# scripts/scrape_api.py

import requests
import pandas as pd

BASE_URL = "https://api.worldquantbrain.com/data-fields"

params = {
    "datasetId": "analyst4",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "limit": 50,
    "offset": 0
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

all_rows = []

while True:
    r = requests.get(BASE_URL, params=params, headers=headers)
    data = r.json()

    rows = data.get("results", [])
    if not rows:
        break

    all_rows.extend(rows)

    print(f"[fetch] offset={params['offset']} got={len(rows)}")

    params["offset"] += params["limit"]

    if params["offset"] >= data.get("count", 0):
        break

df = pd.DataFrame(all_rows)

df.to_csv("data/raw_table.csv", index=False)

print("[done] rows =", len(df))
print(df.head())
