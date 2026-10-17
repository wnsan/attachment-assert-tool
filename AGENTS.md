# AGENTS.md — attachment-assert for AI coding agents

This guide is for an LLM or coding agent that needs to **research this repo** or **add attachment checks to a Playwright test suite**.
Read this file first. Every API listed here exists in the code, and the file paths point to the source.

## What it does (one paragraph)

A *template* is a folder holding a reference file and a list of **named rectangles** (regions) on its pages.
At test time a *candidate* file is rendered at the template's DPI. Each named region is cropped and compared **pixel by pixel** with the reference crop.
The result is pass, fail or error per region, plus a diff PNG and an HTML/JSON report.
By default the match must be exact. Tolerance is opt-in through `threshold`, `maxDiffPercent` / `max_diff_percent` and `shift`.
Supported candidates: PDF (pypdfium2), PNG/JPG/BMP/GIF/TIFF/WebP, and Office/ODT/RTF/HTML when LibreOffice (`soffice`) is installed.

## Pick the right entry point

| You are writing… | Use | Import |
|---|---|---|
| Python `pytest-playwright` tests | the `attachment_assert` fixture (auto-registered pytest plugin) | nothing to import |
| Python, not pytest / async Playwright | `assert_matches`, `compare_file`, `assert_matches_async`, `compare_file_async` | `from attachment_assert import ...` |
| TypeScript/JS `@playwright/test` | `expect(x).toMatchAttachment(template, opts)` | `import { expect } from 'attachment-assert/playwright'` |
| JS without the matcher | `compareAttachment`, `assertAttachment` | `require('attachment-assert')` |
| Shell / CI step | `python -m attachment_assert compare <template> <file> --out dir` | — |

The Node package **does not reimplement the comparison**. It spawns `python -m attachment_assert compare ... --json`, so Python must be installed in every case.

## Install into the target project

```bash
# Python side (needed by both stacks)
pip install "attachment-assert-tool[playwright] @ git+https://github.com/wnsan/attachment-assert-tool"
# Node side (only for @playwright/test projects)
npm i -D github:wnsan/attachment-assert-tool
# If Node picks the wrong interpreter:
export ATTACHMENT_ASSERT_PYTHON=/path/to/python   # must have pillow, numpy, pypdfium2
```

Node looks for Python in this order: `options.python`, then `$ATTACHMENT_ASSERT_PYTHON`, then `py -3` (Windows only), then `python3`, then `python`. Each one is checked for the required modules before it is used (`js/index.js` → `findPython`).

## Step 1: get a template

A test needs a template folder. Commit it to the target repo, e.g. `tests/templates/<name>/`:

```
tests/templates/invoice/
  template.json            # format "attachment-assert/1": dpi, reference page_sizes, defaults, regions
  reference.pdf            # copy of the reference file
  regions/01_header.png    # reference pixels per region
```

Three ways to create one:

1. **UI (best when a human picks the boxes):** run `python -m attachment_assert ui`, open the reference file, drag and name boxes, then save. Copy the folder from `attachment_assert_workspace/templates/<name>/`.
2. **CLI (no UI, agent-friendly):**
   ```bash
   # See the page pixel sizes at the chosen DPI. Optionally look at the PNGs to measure boxes.
   python -m attachment_assert render reference.pdf --out /tmp/pages --dpi 150
   # NAME:PAGE:X,Y,W,H. PAGE is 1-based here. Coordinates are pixels at --dpi, origin top-left.
   python -m attachment_assert create reference.pdf --out tests/templates/invoice --dpi 150 \
       --region "header:1:80,80,1040,160" --region "total:1:760,1360,360,120"
   python -m attachment_assert show tests/templates/invoice      # check the result
   ```
3. **Python:**
   ```python
   from attachment_assert import create_template
   create_template("reference.pdf", [
       {"name": "header", "page": 0, "x": 80, "y": 80, "w": 1040, "h": 160},   # page is 0-based here
       {"name": "total",  "page": 0, "x": 760, "y": 1360, "w": 360, "h": 120, "threshold": 8},
   ], "tests/templates/invoice", dpi=150, name="invoice",
      defaults={"threshold": 0, "max_diff_percent": 0.0, "shift": 0})
   ```

Coordinate rules:
- Boxes are in pixels of the page **rendered at the template DPI**. For PDFs, 1 pt = dpi/72 px. Images use native pixels and ignore DPI.
- To turn a PDF-point box into pixels, multiply by `dpi / 72`.
- `page` is **0-based** in `template.json` and in Python. In the CLI `--region` flag it is **1-based**.
- Region names must be unique, compared case-insensitively. `create_template` raises `ValueError` on duplicates and on boxes outside the page. `only` matches names case-insensitively, and Unicode names work (e.g. `ยอดรวม`).

**Bootstrapping from the app itself.** When there is no reference file yet, do one known-good run first. Save the download (`download.save_as("reference.pdf")` / `await download.saveAs(...)`), then build the template from that file with option 2 or 3.

## Step 2a: Python (pytest-playwright)

`pip install` registers the plugin. If the package isn't installed, add `pytest_plugins = ["attachment_assert.pytest_plugin"]` to `conftest.py`.

```python
# tests/test_invoice.py
import pytest

def test_invoice_pdf(page, attachment_assert):
    page.goto("https://my.app/invoices/42")
    with page.expect_download() as info:
        page.get_by_role("button", name="Download PDF").click()
    attachment_assert(info.value, "invoice")             # == .check(); AssertionError lists failing regions + report path

def test_only_some_regions_with_tolerance(page, attachment_assert):
    ...
    attachment_assert(info.value, "invoice", only=["total"], threshold=8, max_diff_percent=0.5, shift=2)

def test_expected_difference(page, attachment_assert):
    ...
    report = attachment_assert.compare(info.value, "invoice")   # never raises on mismatch
    assert {r.name: r.status for r in report.results}["total"] == "fail"
```

```ini
# pytest.ini / pyproject [tool.pytest.ini_options]
attachment_assert_templates = tests/templates      # base for relative template names (else: rootdir)
attachment_assert_output = test-results/attachment-assert
```

You can also pass these on the command line: `--attachment-assert-templates`, `--attachment-assert-output`.
Each comparison writes to `<output>/<sanitised test id>/<NN>_<template>/report.html`.

Without the fixture, or with async Playwright:

```python
from attachment_assert import assert_matches, compare_file, assert_matches_async, compare_file_async
assert_matches("tests/templates/invoice", download, out_dir="out/invoice")         # sync Download
report = await compare_file_async("tests/templates/invoice", async_download)       # async Download
```

Accepted `candidate` values: a path (`str`/`PathLike`), `bytes`/`bytearray`/`memoryview`, a binary file object, or a sync/async Playwright `Download`. The adapter is `attachment_assert/inputs.py`.
Keyword arguments: `out_dir`, `resize`, `candidate_name`, `only`, `threshold`, `max_diff_percent`, `shift`. Results are `CompareReport` / `RegionResult` from `attachment_assert/compare.py`.

## Step 2b: TypeScript (@playwright/test)

```ts
// tests/invoice.spec.ts
import { test } from '@playwright/test';
import { expect, compareAttachment, assertAttachment } from 'attachment-assert/playwright';

const TEMPLATE = 'tests/templates/invoice';   // relative to process.cwd() (where `npx playwright test` runs) or options.templatesDir

test('invoice PDF matches', async ({ page }) => {
  await page.goto('/invoices/42');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download PDF' }).click(),
  ]);
  await expect(download).toMatchAttachment(TEMPLATE);
  await expect(download).toMatchAttachment(TEMPLATE, { only: ['total'], threshold: 8, maxDiffPercent: 0.5, shift: 2 });
});

test('changed total is detected', async ({ page }) => {
  // ...download as above...
  await expect(download).not.toMatchAttachment(TEMPLATE);
  const report = await compareAttachment(download, TEMPLATE);          // never throws on mismatch
  expect(report.results.filter(r => r.status !== 'pass').map(r => r.name)).toEqual(['total']);
  await expect(assertAttachment(download, TEMPLATE)).rejects.toThrow(/total/);
});
```

If the project already has a custom `expect`, merge the matcher in:

```ts
import { expect as base } from '@playwright/test';
import { attachmentMatchers } from 'attachment-assert/playwright';
export const expect = base.extend(attachmentMatchers);
```

Accepted `received` values: a Playwright `Download`, a file path or `URL`, a `Buffer`/`Uint8Array` (set `name: 'x.pdf'` to help type detection), or a `Page`/`Locator`. A `Page` or `Locator` is compared through its default `.screenshot()`: the viewport for a `Page` (not the full page), or the element's box for a `Locator`. The template must come from a PNG taken the same way, with the same viewport and `deviceScaleFactor`.

Options (`js/index.d.ts` → `AttachmentAssertOptions`): `threshold`, `maxDiffPercent`, `shift`, `resize`, `only` (string or string[]), `outDir`, `templatesDir`, `python`, `name`, `attachAll`.
Inside a test, the matcher writes to `testInfo.outputPath('attachment-assert', ...)`. It attaches `report.html` and the reference, candidate and diff PNGs of **failing** regions to the HTML report. Set `attachAll: true` to attach passing regions too.

## Options: the same knobs under different names

| Meaning | Python kwarg / template.json | JS option | CLI flag | Default |
|---|---|---|---|---|
| per-channel colour difference (0–255) still treated as equal | `threshold` | `threshold` | `--threshold` | 0 |
| % of region pixels allowed to exceed `threshold` | `max_diff_percent` | `maxDiffPercent` | `--max-diff-percent` | 0 |
| search ±N px for the best alignment | `shift` | `shift` | `--shift` | 0 |
| scale candidate pages to the reference size | `resize` | `resize` | `--resize` | false (size mismatch = fail) |
| check only these regions (case-insensitive) | `only=[...]` | `only` | `--only NAME` (repeat) | all |

Precedence, lowest to highest: template `defaults`, then the region's own value in `template.json`, then the per-call override. A per-call override applies to every region in that call.

## Report shape (`report.json`, CLI `--json`, JS return value)

```jsonc
{
  "passed": false,
  "counts": {"pass": 2, "fail": 1, "error": 0},
  "template": "invoice", "candidate": "invoice_changed_total.pdf", "dpi": 72,
  "results": [{
    "name": "total", "page": 0, "box": [380, 680, 561, 741], "status": "fail",   // box = x0, y0, x1, y1 (not w/h)
    "message": "662 of 11041 pixels differ (5.9958% > 0.0% allowed, threshold 0)",
    "total_pixels": 11041, "diff_pixels": 662, "diff_percent": 5.9958,
    "max_channel_diff": 209, "mean_abs_diff": 0.7713, "offset": [0, 0],          // offset = best shift found
    "tolerance": {"threshold": 0, "max_diff_percent": 0.0, "shift": 0},
    "images": {"reference": "regions/02_total_reference.png", "candidate": "...", "diff": "..."}   // relative to the out dir; {} when no out dir
  }]
  // JS adds: outDir, reportHtml, summary
}
```

`status: "fail"` covers pixel differences and also a page-size mismatch without `resize`.
`status: "error"` means the region could not be compared: the candidate has fewer pages, the region falls outside the candidate page, or the reference crop is missing.
`create_template` / `create` reject boxes outside the reference page with a `ValueError`.
CLI exit codes: `0` all regions match, `1` at least one mismatch, `2` usage, render or IO error. The JS wrapper throws for any exit code other than 0 or 1.
Diff PNG colours: red is beyond the threshold, yellow is nonzero but within it.

## Pitfalls (read before debugging a "flaky" failure)

- **DPI is fixed by the template.** A candidate is always rendered at `template.dpi`. Choose the DPI when you create the template; you can't change it per call.
- **Cross-OS font rasterisation.** PDF rendering is stable because pypdfium2 bundles its own engine. **Browser screenshots** can differ between OSes and GPUs. For screenshot templates use `threshold` 10–30 and/or a small `maxDiffPercent`, and generate the template on the CI OS.
- **Dynamic content.** Dates, IDs and QR codes change every run. Don't box them, or give those regions their own tolerance.
- **Layout drift of a few pixels.** Use `shift: 1..3` rather than a big `maxDiffPercent`.
- **Different page size.** This fails by default, which is deliberate. Pass `resize` only when the scaling is expected.
- **Template paths.** In pytest they are relative to `attachment_assert_templates` or the rootdir. In Node they are relative to `process.cwd()` or `templatesDir`. Pass absolute paths if in doubt.
- **Downloads in Python e2e.** Serve files from a real HTTP server. A `page.route(...).fulfill(...)` attachment download can come back canceled in Playwright (see `e2e/python/conftest.py`).
- **Office files** need LibreOffice on PATH, otherwise you get `status`/exit-code errors. Exporting to PDF in the app under test is more deterministic.
- **Intended visual change.** Regenerate the template (UI "Load template…" → save, or re-run `create`) and commit the new `regions/*.png`. Don't loosen tolerance to hide the change.

## Repo map (for research / changes)

| Path | What |
|---|---|
| `attachment_assert/render.py` | file type detection, PDF/image/LibreOffice rendering (`render_file`) |
| `attachment_assert/template.py` | `Template`, `Region`, `Tolerance`, `create_template`, template.json I/O |
| `attachment_assert/compare.py` | `compare_pages` (core pixel diff + shift search), `compare_file`, `assert_matches`, async variants, `filter_regions` |
| `attachment_assert/inputs.py` | turns Download/bytes/file objects into a temp file (`materialize`, `amaterialize`) |
| `attachment_assert/pytest_plugin.py` | pytest options and the `attachment_assert` fixture (`AttachmentAssert`) |
| `attachment_assert/report.py` | HTML report |
| `attachment_assert/cli.py` | `ui`, `compare`, `create`, `show`, `render` subcommands |
| `attachment_assert/server.py`, `static/index.html` | browser UI (stdlib HTTP server + single-page app) |
| `js/index.js`, `js/index.d.ts` | Node wrapper: `compareAttachment`, `assertAttachment`, `findPython` |
| `js/playwright.js`, `js/playwright.d.ts` | `toMatchAttachment` matcher, `attachmentMatchers`, extended `expect` |
| `e2e/python/`, `e2e/node/` | working Playwright examples (Python + TS) against `e2e/server.js` / `e2e/site/` |
| `examples/` | sample PDFs and the `examples/templates/invoice` template (regions: `header`, `total`, `header p2`) |
| `tests/` | unit tests (unittest) |

Verify changes made in this repo:

```bash
pip install -e ".[playwright]" && python -m playwright install chromium
python -m unittest discover -s tests
python -m pytest e2e/python --attachment-assert-templates examples/templates
npm ci && npx playwright install chromium && npx playwright test -c e2e/node
```

## Checklist for adding attachment assertions to a Playwright suite

1. Install the Python package (and the npm package for TS) in the target project.
2. Get a known-good reference file and create a template with named regions. Commit `tests/templates/<name>/`.
3. In the test, trigger the download (`expect_download` / `waitForEvent('download')`) and assert with the fixture or matcher.
4. Run it once against a known-good build (it must pass) and once against a deliberately changed file (it must fail on the expected region).
5. Make sure CI installs Python with pillow, numpy and pypdfium2, and upload `test-results/` / `playwright-report/` as artifacts.
