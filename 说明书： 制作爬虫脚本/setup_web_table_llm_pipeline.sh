#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# WorldQuant Brain FULL SCRAPER (16 datasets 自动抓取版)
# 只需填写 Cookie 即可运行
# ============================================================

PROJECT="wqbrain_full_scraper"
mkdir -p "$PROJECT"/{data,logs,scripts}
cd "$PROJECT"

# =====================
# 1. Python 环境
# =====================
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install requests pandas python-dotenv

# =====================
# 2. 环境变量
# =====================
cat > .env <<'EOF'
WQB_COOKIE=cookieyes-consent=consentid:czhveGZmcWVFZzZlNFY5UEdYVzE4NXVjRXdjVGM1dlQ,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; _ga=GA1.1.177622511082117d7d5ba2de13; _fbp=fb.1.1776225166252.449640668535646284; _gcl_gs=2.1.k1$i1776903980$u44383394; _gcl_aw=GCL.1776912120.CjwKCAjw46HPBhAMEiwASZpLRCnSmnnr1jsYb4IKA0eIOl5GOi5dC9LmIBD3ShEk9bnzJV-iU7YjgxoCC0sQAvD_BwE; _ga_FXKNEPLB1N=GS2.1.s1776911885$o8$g1$t1776913828$j55$l0$h0; _gcl_au=1.1.1140661563.1776225166.2046007118.1777231237.1777231236; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJySjZaZllaemRMNXJ6a0g5SmVYelhYQkF4cW1TdERaZSIsImV4cCI6MTc3NzI2MTcwMn0.QAK6hHMVSVFK8N-R1kXBw-etdG3BBMToniuiniKNIPw; _ga_9RN6WVT1K1=GS2.1.s1777258231$o24$g1$t1777258769$j7$l0$h0; _rdt_uuid=1776225166030.3a9efe4c-2807-4ecc-a891-7b7de450fff6
EOF

# =====================
# 3. Python 主程序
# =====================
cat > scripts/run.py <<'PY'
import os
import time
import pandas as pd
import requests
from http.cookies import SimpleCookie
from dotenv import load_dotenv

load_dotenv()

COOKIE_STRING = os.getenv("WQB_COOKIE", "").strip()

if not COOKIE_STRING or COOKIE_STRING == "PASTE_YOUR_COOKIE_HERE":
    raise RuntimeError("请在 .env 填写 WQB_COOKIE")

BASE = "https://api.worldquantbrain.com"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://platform.worldquantbrain.com",
    "Referer": "https://platform.worldquantbrain.com/",
    "Accept": "application/json;version=2.0",
}

cookie = SimpleCookie()
cookie.load(COOKIE_STRING)
cookies = {k: v.value for k, v in cookie.items()}

session = requests.Session()
session.headers.update(headers)
session.cookies.update(cookies)


class AdaptiveThrottle:
    """
    自适应限速器：
    - 每次请求前先 sleep；
    - 遇到 429 自动加倍等待；
    - 读取 Retry-After header；
    - 连续成功后才缓慢加速。
    """

    def __init__(self, base_delay=3.0, min_delay=2.0, max_delay=180.0):
        self.delay = base_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.success_streak = 0

    def wait_before_request(self):
        print(f"[throttle] sleep {self.delay:.1f}s before request")
        time.sleep(self.delay)

    def on_success(self):
        self.success_streak += 1
        if self.success_streak >= 5:
            self.delay = max(self.min_delay, self.delay * 0.9)
            self.success_streak = 0
        print(f"[throttle] success, next delay={self.delay:.1f}s")

    def on_rate_limit(self, retry_after=None):
        self.success_streak = 0
        if retry_after is not None:
            wait = max(float(retry_after), self.delay * 2)
        else:
            wait = self.delay * 2
        self.delay = min(self.max_delay, wait)
        print(f"[throttle] 429 detected, increase delay to {self.delay:.1f}s")
        return self.delay


throttle = AdaptiveThrottle(base_delay=3.0, min_delay=2.0, max_delay=180.0)


def get_json_with_retry(url, params, max_retries=12):
    """Handle WorldQuant Brain rate limit with adaptive throttle."""
    for attempt in range(max_retries):
        throttle.wait_before_request()
        r = session.get(url, params=params, timeout=90)
        print("GET", r.url, "status", r.status_code)

        if r.status_code == 200:
            throttle.on_success()
            return r.json()

        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            wait = throttle.on_rate_limit(retry_after)
            print(f"Rate limited: 429. attempt={attempt + 1}/{max_retries}. Sleep {wait:.1f}s then retry...")
            time.sleep(wait)
            continue

        if r.status_code in {401, 403}:
            print("ERROR: cookie 可能过期或权限不足。请重新复制 Cookie 到 .env。")
            print(r.text[:500])
            r.raise_for_status()

        print("ERROR:", r.text[:500])
        r.raise_for_status()

    raise RuntimeError("Too many 429 retries. Please wait 10-20 minutes, refresh cookie, and run again.")


# =====================
# 1. 获取 datasets，页面显示一共 16 个
# =====================
print("
=== STEP 1: 获取 datasets ===")

datasets = []
offset = 0
limit = 20

while True:
    data = get_json_with_retry(f"{BASE}/data-sets", params={
        "delay": 1,
        "instrumentType": "EQUITY",
        "limit": limit,
        "offset": offset,
        "region": "USA",
        "universe": "TOP3000",
    })

    rows = data.get("results", []) if isinstance(data, dict) else data
    total = data.get("count") if isinstance(data, dict) else None

    if not rows:
        print("No dataset rows returned. Stop.")
        break

    datasets.extend(rows)
    print(f"datasets offset={offset}, rows={len(rows)}, collected={len(datasets)}, total={total}")

    if total is not None and len(datasets) >= int(total):
        break

    if len(rows) < limit:
        break

    offset += limit


df_datasets = pd.DataFrame(datasets)
df_datasets.to_csv("data/datasets.csv", index=False, encoding="utf-8-sig")

print("Total datasets:", len(df_datasets))

if df_datasets.empty:
    raise RuntimeError("datasets.csv is empty. Usually caused by 429 rate limit or invalid/expired cookie.")

print("Dataset columns:", list(df_datasets.columns))

name_col = "name" if "name" in df_datasets.columns else None
id_col = "id" if "id" in df_datasets.columns else None

if id_col is None:
    candidates = [c for c in df_datasets.columns if c.lower() in {"dataset.id", "dataset_id"} or c.lower().endswith("id")]
    if not candidates:
        raise RuntimeError(f"Cannot find dataset id column. Columns={list(df_datasets.columns)}")
    id_col = candidates[0]

if name_col:
    print(df_datasets[[id_col, name_col]].to_string(index=False))
else:
    print(df_datasets[[id_col]].to_string(index=False))

# =====================
# 2. 抓所有 fields
# =====================
print("
=== STEP 2: 抓所有 fields ===")

all_fields = []

for dataset_id in df_datasets[id_col].dropna().astype(str).unique():
    print("
>>> dataset:", dataset_id)

    offset = 0

    while True:
        data = get_json_with_retry(f"{BASE}/data-fields", params={
            "dataset.id": dataset_id,
            "delay": 1,
            "instrumentType": "EQUITY",
            "limit": limit,
            "offset": offset,
            "region": "USA",
            "universe": "TOP3000",
        })

        rows = data.get("results", []) if isinstance(data, dict) else data
        total = data.get("count") if isinstance(data, dict) else None

        if not rows:
            print("  no more rows")
            break

        for row in rows:
            if isinstance(row, dict):
                row["dataset_id"] = dataset_id

        all_fields.extend(rows)
        print(f"  fields offset={offset}, rows={len(rows)}, collected={len(all_fields)}, dataset_total={total}")

        if total is not None and offset + limit >= int(total):
            break

        if len(rows) < limit:
            break

        offset += limit


df_fields = pd.DataFrame(all_fields)
df_fields.to_csv("data/fields_all.csv", index=False, encoding="utf-8-sig")

print("
=== DONE ===")
print("datasets:", len(df_datasets))
print("fields:", len(df_fields))
print("saved: data/datasets.csv")
print("saved: data/fields_all.csv")
PY

# =====================
# 4. 运行脚本
# =====================
cat > run.sh <<'EOF'
#!/usr/bin/env bash
set -e
source .venv/bin/activate
python scripts/run.py
EOF

chmod +x run.sh

echo ""
echo "✅ 安装完成"
echo "下一步："
echo "1. 打开 .env 填写 Cookie"
echo "2. 运行 ./run.sh"
