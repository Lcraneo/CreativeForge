"""CreativeForge AI 封面渲染：cover.html → 多尺寸 PNG + A4 矢量 PDF
用法：python render.py [--draft]   （--draft 仅出 16:9 低倍率小样用于自查）
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = (HERE / "cover.html").as_uri()
OUT = HERE / "exports"
OUT.mkdir(exist_ok=True)

BOARDS = [  # (id, 输出名, device_scale_factor)
    ("board-a", "creativeforge-cover-16x9.png", 2),            # 1920×1080
    ("board-b", "creativeforge-cover-a4-print.png", 2480/794), # 2480×3508 ≈ A4@300dpi
    ("board-c", "creativeforge-cover-square.png", 2),          # 1080×1080
    ("board-d", "creativeforge-cover-banner.png", 2),          # 1500×500
]

def fonts_ready(page):
    page.evaluate("document.fonts.ready.then(() => true)")
    ok = page.evaluate("""(() => {
        const zh = document.fonts.check('900 20px "Noto Serif SC"', '锻塑律铸一句自然语言');
        const en = document.fonts.check('900 20px "Noto Serif SC"', 'CreativeForge');
        const sans = document.fonts.check('600 14px "Outfit"', 'Studio');
        return { zh, en, sans };
    })()""")
    return ok

with sync_playwright() as p:
    browser = p.chromium.launch()
    draft = "--draft" in sys.argv

    if draft:
        ctx = browser.new_context(device_scale_factor=1, viewport={"width": 1100, "height": 4000})
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_timeout(400)
        print("fonts:", fonts_ready(page))
        page.locator("#board-a").screenshot(path=OUT / "_draft-a.png")
        page.locator("#board-b").screenshot(path=OUT / "_draft-b.png")
        print("draft done")
    else:
        done = set()
        for dsf in sorted({round(b[2], 5) for b in BOARDS}, reverse=True):
            ctx = browser.new_context(device_scale_factor=dsf, viewport={"width": 1100, "height": 4000})
            page = ctx.new_page()
            page.goto(URL)
            page.wait_for_timeout(400)
            fr = fonts_ready(page)
            for bid, name, scale in BOARDS:
                if abs(scale - dsf) < 1e-4:
                    page.locator(f"#{bid}").screenshot(path=OUT / name)
                    done.add(bid)
                    print(f"{name}  <- {bid} @{dsf:.3f}x  fonts:{fr['zh'] and fr['en'] and fr['sans']}")
            ctx.close()

        # A4 矢量 PDF（印刷母版）
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_timeout(400)
        page.emulate_media(media="print")
        page.pdf(path=str(OUT / "creativeforge-cover-a4-print.pdf"),
                 prefer_css_page_size=True, print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        print("creativeforge-cover-a4-print.pdf done")
        ctx.close()

    browser.close()
