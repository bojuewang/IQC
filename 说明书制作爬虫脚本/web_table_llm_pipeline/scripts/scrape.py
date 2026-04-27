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
