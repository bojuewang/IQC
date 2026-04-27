import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://platform.worldquantbrain.com/learn/operators"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto(URL)

        print("👉 请登录，然后回到 Operators 页面")
        input("登录完成后按 Enter...")

        page.goto(URL, wait_until="networkidle")

        # 等待页面主体加载（避免依赖 <table>）
        page.wait_for_timeout(5000)
        page.wait_for_selector("text=Arithmetic", timeout=60000)

        # ============================================================
        # 关闭/忽略 cookie 弹窗（若存在）
        # ============================================================
        try:
            # 常见同意按钮（可能不存在）
            consent_btn = page.locator("button:has-text('Accept')")
            if consent_btn.count() > 0:
                consent_btn.first.click()
                page.wait_for_timeout(500)
        except:
            pass

        # ============================================================
        # 稳定展开所有 Show more（排除 cookie 的 Show more）
        # 关键：限定在 main 区域，避免点到 .cky-show-desc-btn
        # ============================================================
        max_clicks = 200

        for k in range(max_clicks):
            buttons = page.locator("button:has-text('Show more'):not(.cky-show-desc-btn)")
            count = buttons.count()

            if count == 0:
                print("没有更多 Show more")
                break

            print(f"click {k + 1}, remaining buttons = {count}")

            try:
                btn = buttons.first
                btn.scroll_into_view_if_needed()
                btn.click(timeout=5000)
                page.wait_for_timeout(300)
            except Exception as e:
                print("点击失败，停止展开:", e)
                break

        page.wait_for_timeout(1000)

        # ============================================================
        # 抓取整页文本（稳定基线），后续再解析为 CSV
        # ============================================================
        text = page.locator("body").inner_text()

        with open("operators_page_text.txt", "w", encoding="utf-8") as f:
            f.write(text)

        print("✅ 已保存页面文本到 operators_page_text.txt")
        print(text[:1000])

        browser.close()


if __name__ == "__main__":
    main()
