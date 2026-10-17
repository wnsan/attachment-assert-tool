# attachment-assert-tool

Visual assertions for **PDFs, images and documents**:

1. **Define**: open a reference file in the browser, drag boxes over the parts that matter, and give each box a name (`header`, `ยอดรวม`, `signature`, ...). Save the boxes as a *template*.
2. **Compare**: give it another file. The tool renders the file, crops the same named regions and compares them **pixel by pixel** against the reference crops. You get PASS/FAIL per region, diff images and an HTML/JSON report. The CLI exits with code 1 when something differs, so you can use it in CI or tests.

| Input | How it is rendered |
|---|---|
| PDF | every page rasterised with [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) at the template DPI (default 150) |
| PNG / JPG / BMP / GIF / TIFF / WebP | native pixels (multi-frame TIFF/GIF = multiple pages; transparency is flattened onto white) |
| DOCX / XLSX / PPTX / ODT / RTF / TXT / HTML ... | converted to PDF with LibreOffice (`soffice`) when it is installed, then rendered like a PDF |

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
