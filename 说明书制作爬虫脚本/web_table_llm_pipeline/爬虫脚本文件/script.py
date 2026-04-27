import requests
import pandas as pd
import time
from http.cookies import SimpleCookie

# ============================================================
# WorldQuant Brain data-fields API 爬虫
# 目标：抓取 Analyst Estimate Data for Equity 的 Fields 表
# ============================================================

BASE = "https://api.worldquantbrain.com/data-fields"

params = {
    "dataset.id": "uni1",
    "delay": 1,
    "instrumentType": "EQUITY",
    "limit": 20,
    "offset": 0,
    "region": "USA",
    "universe": "TOP3000",
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://platform.worldquantbrain.com",
    "Referer": "https://platform.worldquantbrain.com/",
    "Accept": "application/json, text/plain, */*",
}

# ============================================================
# 关键：把浏览器 DevTools 里的 Cookie 整行复制到这里
#
# 操作：
# Network -> data-fields?... -> Headers -> Request Headers -> Cookie
# 复制类似：
# a=xxx; b=yyy; t=zzz
#
# 注意：不要复制 URL，不要复制 Request Cookies 表格中的 Name/Value 分列。
# ============================================================

COOKIE_STRING = """
cookieyes-consent=consentid:czhveGZmcWVFZzZlNFY5UEdYVzE4NXVjRXdjVGM1dlQ,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; _ga=GA1.1.177622511082117d7d5ba2de13; _fbp=fb.1.1776225166252.449640668535646284; _gcl_gs=2.1.k1$i1776903980$u44383394; _gcl_aw=GCL.1776912120.CjwKCAjw46HPBhAMEiwASZpLRCnSmnnr1jsYb4IKA0eIOl5GOi5dC9LmIBD3ShEk9bnzJV-iU7YjgxoCC0sQAvD_BwE; _ga_FXKNEPLB1N=GS2.1.s1777261685$o9$g1$t1777261699$j46$l0$h0; _gcl_au=1.1.1140661563.1776225166.1663074993.1777261705.1777261704; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI5UGhGcVB4Uk83MnNveExqZFJ0VUxFazdoMzlVbmVpcSIsImV4cCI6MTc3NzI3NjEzMH0.5xorvW5oT_zPbZifo1KReMbp_HWoG8zebXn_4aurBbE; _rdt_uuid=1776225166030.3a9efe4c-2807-4ecc-a891-7b7de450fff6; _ga_9RN6WVT1K1=GS2.1.s1777264873$o25$g1$t1777266139$j2$l0$h0
""".strip()


def cookie_string_to_dict(cookie_string: str) -> dict:
    """Convert raw browser Cookie header string into requests cookies dict."""
    if not cookie_string or cookie_string == "PASTE_YOUR_COOKIE_STRING_HERE":
        raise ValueError(
            "请先把浏览器 Request Headers 里的 Cookie 整行复制到 COOKIE_STRING。"
        )

    simple_cookie = SimpleCookie()
    simple_cookie.load(cookie_string)
    return {key: morsel.value for key, morsel in simple_cookie.items()}


def fetch_one_page(session: requests.Session, offset: int) -> tuple[list, int | None]:
    """Fetch one page. Return rows and optional total count."""
    params["offset"] = offset
    response = session.get(BASE, params=params, timeout=60)

    print("offset =", offset, "status =", response.status_code)

    if response.status_code != 200:
        print("ERROR TEXT:", response.text[:500])
        response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        rows = data.get("results", [])
        total = data.get("count") or data.get("total")
    elif isinstance(data, list):
        rows = data
        total = None
    else:
        rows = []
        total = None

    return rows, total


def main():
    cookies = cookie_string_to_dict(COOKIE_STRING)

    session = requests.Session()
    session.headers.update(headers)
    session.cookies.update(cookies)

    all_rows = []
    limit = params["limit"]
    total_count = None

    for offset in range(0, 20000, limit):
        rows, total = fetch_one_page(session, offset)

        if total is not None and total_count is None:
            total_count = int(total)
            print("detected total_count =", total_count)

        if not rows:
            print("No more rows. Stop.")
            break

        all_rows.extend(rows)

        if total_count is not None and len(all_rows) >= total_count:
            print("Reached total_count. Stop.")
            break

        # 你截图里显示 rate limit 是 1 request / second
        time.sleep(1.2)

    df = pd.DataFrame(all_rows)
    df.to_csv("uni1_fields.csv", index=False, encoding="utf-8-sig")

    print("\nDone.")
    print("Total rows:", len(df))
    print("Saved to: uni1_fields.csv")
    print(df.head())


if __name__ == "__main__":
    main()
