# attachment-assert-tool

Visual assertions for **PDFs, images and documents**:

1. **Define**: open a reference file in the browser, drag boxes over the parts that matter, and give each box a name (`header`, `ยอดรวม`, `signature`, ...). Save the boxes as a *template*.
2. **Compare**: give it another file. The tool renders the file, crops the same named regions and compares them **pixel by pixel** against the reference crops. You get PASS/FAIL per region, diff images and an HTML/JSON report. The CLI exits with code 1 when something differs, so you can use it in CI or tests.

| Input | How it is rendered |
|---|---|
| PDF | every page rasterised with [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) at the template DPI (default 150) |
| PNG / JPG / BMP / GIF / TIFF / WebP | native pixels (multi-frame TIFF/GIF = multiple pages; transparency is flattened onto white) |
| DOCX / XLSX / PPTX / ODT / RTF / TXT / HTML ... | converted to PDF with LibreOffice (`soffice`) when it is installed, then rendered like a PDF |

> Using an AI coding agent? Point it at [AGENTS.md](AGENTS.md) (also indexed in [llms.txt](llms.txt)).

## Install

Requires Python 3.9+.

```bash
pip install -r requirements.txt        # pillow, numpy, pypdfium2
# or: pip install .   -> gives you the `attachment-assert` command
```

On Windows you can double-click `setup.bat` and then `run_ui.bat`.

## 1. Define regions (browser UI)

```bash
python -m attachment_assert ui            # opens http://localhost:8765
```

- **Open reference file…** (or drag and drop a file). Choose the DPI first for PDFs.
- **Drag** on the page to add a region. Rename it in the side panel. Move it by dragging, resize it with the corner handles, nudge it with the arrow keys (Shift = 10 px), and delete it with `Del`.
- Each region can override the default tolerance. Leave the fields blank to use the template default.
- **Save template**. The template is written to `attachment_assert_workspace/templates/<name>/`. **.zip** downloads the folder (use it in CI). **Load template…** opens a saved template for editing.

Template folder layout:

```
<template>/
  template.json          # dpi, page sizes, defaults, regions (name, page, x, y, w, h, tolerance)
  reference.pdf          # copy of the reference file
  regions/01_header.png  # reference pixels of each region
```

## 2. Compare

**In the UI**: open the **Compare** tab, pick a template, choose one or more files, and press **Compare**. Each region shows the *reference / candidate / diff* crops. In the diff image, red means a pixel differs beyond the threshold and yellow means it differs but is within the threshold. The page overview draws green and red boxes on the candidate page.

**CLI** (exit code `0` = all match, `1` = mismatch, `2` = error):

```bash
python -m attachment_assert compare path/to/template new_invoice.pdf --out report/
python -m attachment_assert compare path/to/template a.pdf b.pdf c.png --out reports/   # one sub-folder per file
python -m attachment_assert compare path/to/template new.pdf --only header --only total
python -m attachment_assert compare path/to/template new.pdf --threshold 8 --max-diff-percent 0.5 --shift 2
python -m attachment_assert compare path/to/template new.pdf --json
```

`report/` contains `report.html`, `report.json`, `page_N.png` overviews, and `regions/*_{reference,candidate,diff}.png`.

**Python / unit tests**:

```python
from attachment_assert import assert_matches, compare_file

assert_matches("templates/invoice", "out/invoice.pdf")           # raises AssertionError listing failed regions
report = compare_file("templates/invoice", "out/invoice.pdf", out_dir="report", shift=2)
print(report.passed, [(r.name, r.status, r.diff_percent) for r in report.results])
```

**Templates without the UI**:

```bash
python -m attachment_assert render reference.pdf --out pages/ --dpi 150    # look up pixel coordinates
python -m attachment_assert create reference.pdf --out templates/invoice --dpi 150 \
    --region "header:1:80,80,1040,160" --region "total:1:760,1360,360,120"   # name:page(1-based):x,y,w,h
python -m attachment_assert show templates/invoice
```

## Use it in Playwright e2e tests

The same template folder (made in the UI or with `create`) works from Python and Node.
Both use the bundled Python engine, so the pixels match what you saw in the UI.

### Python: pytest-playwright

```bash
pip install "attachment-assert-tool[playwright] @ git+https://github.com/wnsan/attachment-assert-tool"
```

Installing the package registers a pytest plugin with an `attachment_assert` fixture. It accepts a Playwright `Download`, a file path, bytes or a file object:

```python
def test_invoice_download(page, attachment_assert):
    page.goto("https://my.app/invoices/42")
    with page.expect_download() as info:
        page.click("text=Download PDF")
    attachment_assert(info.value, "invoice")                  # raises AssertionError listing failed regions
    attachment_assert(info.value, "invoice", only=["total"], shift=2, threshold=8)
    report = attachment_assert.compare(info.value, "invoice")  # no raise, inspect report.results
```

```bash
pytest --attachment-assert-templates tests/templates     # or ini: attachment_assert_templates = tests/templates
```

Reports go to `test-results/attachment-assert/<test id>/` (change it with `--attachment-assert-output`).
Without pytest, `assert_matches(template, download)` / `compare_file(...)` take the same inputs.
For the async API, use `await assert_matches_async(template, download)`.

### Node / TypeScript: @playwright/test

```bash
npm i -D github:wnsan/attachment-assert-tool      # needs Python 3.9+ and: pip install pillow numpy pypdfium2
```

```ts
import { test } from '@playwright/test';
import { expect, compareAttachment } from 'attachment-assert/playwright';

test('invoice PDF', async ({ page }) => {
  await page.goto('/invoices/42');
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('text=Download PDF')]);

  await expect(download).toMatchAttachment('tests/templates/invoice');
  await expect(download).toMatchAttachment('tests/templates/invoice', { only: ['total'], shift: 2, threshold: 8 });

  const report = await compareAttachment(download, 'tests/templates/invoice');   // no throw
  console.log(report.results.map(r => `${r.name}: ${r.status}`));
});
```

If you already have your own `expect`, extend it with `base.extend(attachmentMatchers)`.
`toMatchAttachment` accepts a `Download`, a file path, a `Buffer`, or a `Page`/`Locator` (as a screenshot).
On failure, the HTML report and the reference/candidate/diff crops of the failing regions are attached to the Playwright HTML report.
Options: `threshold`, `maxDiffPercent`, `shift`, `resize`, `only`, `outDir`, `templatesDir`, `python`, `attachAll`.

The interpreter is found from `ATTACHMENT_ASSERT_PYTHON`, then `py -3` (Windows), `python3`, `python`.

Working examples (both run in CI): [`e2e/python`](e2e/python) and [`e2e/node`](e2e/node), using the demo app in `e2e/server.js` and the template in `examples/templates/invoice`.

```bash
pytest e2e/python --attachment-assert-templates examples/templates
npm ci && npx playwright install chromium && npx playwright test -c e2e/node
```

## Tolerance

| setting | meaning | default |
|---|---|---|
| `threshold` | per-channel colour difference (0-255) that still counts as *equal* | `0` |
| `max_diff_percent` | % of region pixels allowed to exceed the threshold | `0` |
| `shift` | search ±N px around the box for the best alignment (absorbs small layout shifts) | `0` |

All zeros means an exact pixel-by-pixel match. You can set tolerance as a template default, per region, or as a per-run override (CLI flags or the UI "override tolerance" fields).

If a candidate page has a different pixel size than the reference page, the region **fails** by default. Use `--resize` (or the *resize pages* checkbox) to scale the candidate page to the reference size first. Combine it with a non-zero threshold, because resampling changes pixels.

## Try it

`examples/` has a reference invoice, an identical copy and a copy with a changed total:

```bash
python -m attachment_assert create examples/invoice_reference.pdf --out /tmp/tpl --dpi 72 \
    --region "header:1:40,40,521,81" --region "total:1:380,680,181,61"
python -m attachment_assert compare /tmp/tpl examples/invoice_same.pdf            # PASS
python -m attachment_assert compare /tmp/tpl examples/invoice_changed_total.pdf   # FAIL: total
```

## Tests

```bash
python -m unittest discover -s tests -v
```
