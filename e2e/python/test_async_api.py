"""Async Playwright API (no pytest-playwright fixtures needed)."""
import asyncio
from pathlib import Path

from attachment_assert import assert_matches_async, compare_file_async

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "examples/templates/invoice"


async def _download(base_url, link):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(base_url)
        async with page.expect_download() as info:
            await page.click(link)
        download = await info.value
        same = await assert_matches_async(TEMPLATE, download) if link == "#dl-same" else None
        rep = await compare_file_async(TEMPLATE, download)
        await browser.close()
        return same, rep


def test_async_download(demo_url):
    same, rep = asyncio.run(_download(demo_url, "#dl-same"))
    assert same.passed and rep.passed
    _, rep = asyncio.run(_download(demo_url, "#dl-changed"))
    assert [r.name for r in rep.results if not r.passed] == ["total"]
    assert rep.candidate == "invoice_changed_total.pdf"
