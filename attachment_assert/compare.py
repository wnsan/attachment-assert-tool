"""Compare a candidate file against a template, region by region."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .inputs import amaterialize, materialize
from .render import render_file
from .template import Region, Template, Tolerance, safe_filename


@dataclass
class RegionResult:
    name: str
    page: int
    box: list[int]
    status: str  # "pass" | "fail" | "error"
    message: str = ""
    total_pixels: int = 0
    diff_pixels: int = 0
    diff_percent: float = 0.0
    max_channel_diff: int = 0
    mean_abs_diff: float = 0.0
    offset: list[int] = field(default_factory=lambda: [0, 0])
    tolerance: dict = field(default_factory=dict)
    images: dict = field(default_factory=dict)  # reference/candidate/diff, relative to out_dir

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass
class CompareReport:
    template: str
    candidate: str
    dpi: int
    results: list[RegionResult]
    page_sizes: dict = field(default_factory=dict)
    pages: list[str] = field(default_factory=list)  # overview images relative to out_dir
    out_dir: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    @property
    def counts(self) -> dict:
        c = {"pass": 0, "fail": 0, "error": 0}
        for r in self.results:
            c[r.status] += 1
        return c

    def summary(self) -> str:
        c = self.counts
        head = "PASS" if self.passed else "FAIL"
        lines = [f"{head}: {c['pass']}/{len(self.results)} regions match "
                 f"({c['fail']} failed, {c['error']} errors) - {self.candidate}"]
        for r in self.results:
            if not r.passed:
                lines.append(f"  [{r.status.upper()}] {r.name} (page {r.page + 1}): {r.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "counts": self.counts,
            "template": self.template,
            "candidate": self.candidate,
            "dpi": self.dpi,
            "page_sizes": self.page_sizes,
            "pages": self.pages,
            "results": [asdict(r) for r in self.results],
        }


def _bad_mask(ref: np.ndarray, cand: np.ndarray, threshold: int) -> tuple[np.ndarray, np.ndarray]:
    diff = np.abs(ref.astype(np.int16) - cand.astype(np.int16)).max(axis=2)
    return diff, diff > threshold


def _best_alignment(page: np.ndarray, ref: np.ndarray, region: Region, tol: Tolerance):
    """Return (dx, dy, cand_crop) minimising differing pixels within +/- shift."""
    ph, pw = page.shape[:2]
    h, w = ref.shape[:2]
    best = None
    s = max(0, tol.shift)
    offsets = sorted(
        ((dx, dy) for dx in range(-s, s + 1) for dy in range(-s, s + 1)),
        key=lambda o: abs(o[0]) + abs(o[1]),
    )
    for dx, dy in offsets:
        x, y = region.x + dx, region.y + dy
        if x < 0 or y < 0 or x + w > pw or y + h > ph:
            continue
        crop = page[y:y + h, x:x + w]
        _, bad = _bad_mask(ref, crop, tol.threshold)
        n = int(bad.sum())
        if best is None or n < best[0]:
            best = (n, dx, dy, crop)
            if n == 0:
                break
    if best is None:
        return None
    return best[1], best[2], best[3]


def make_diff_image(ref: np.ndarray, cand: np.ndarray, threshold: int) -> Image.Image:
    """Faded reference with red = differs beyond threshold, yellow = within threshold."""
    diff, bad = _bad_mask(ref, cand, threshold)
    gray = ref.mean(axis=2, keepdims=True)
    out = np.repeat(255 - (255 - gray) * 0.25, 3, axis=2)
    soft = (diff > 0) & ~bad
    out[soft] = [255, 210, 0]
    out[bad] = [230, 0, 0]
    return Image.fromarray(out.astype(np.uint8), "RGB")


def compare_pages(
    template: Template,
    cand_pages: list[Image.Image],
    candidate_name: str = "candidate",
    out_dir: str | Path | None = None,
    resize: bool = False,
    overrides: dict | None = None,
) -> CompareReport:
    out = Path(out_dir) if out_dir else None
    if out:
        (out / "regions").mkdir(parents=True, exist_ok=True)
    ref_sizes = [tuple(s) for s in template.reference.get("page_sizes", [])]
    defaults = Tolerance.from_dict(overrides, template.defaults) if overrides else template.defaults

    arrays: dict[int, np.ndarray] = {}
    size_note: dict[int, str] = {}

    def page_array(i: int) -> np.ndarray:
        if i not in arrays:
            img = cand_pages[i]
            if i < len(ref_sizes) and img.size != ref_sizes[i]:
                size_note[i] = f"{img.size[0]}x{img.size[1]} vs reference {ref_sizes[i][0]}x{ref_sizes[i][1]}"
                if resize:
                    img = img.resize(ref_sizes[i], Image.LANCZOS)
            arrays[i] = np.asarray(img.convert("RGB"))
        return arrays[i]

    results: list[RegionResult] = []
    for idx, region in enumerate(template.regions, 1):
        tol = region.tolerance(defaults)
        if overrides:
            tol = Tolerance.from_dict(overrides, tol)
        res = RegionResult(
            name=region.name, page=region.page, box=list(region.box), status="error",
            tolerance=asdict(tol),
        )
        results.append(res)
        try:
            ref = np.asarray(template.region_image(region))
        except Exception as exc:  # missing/corrupt reference crop
            res.message = f"cannot load reference crop: {exc}"
            continue
        res.total_pixels = int(ref.shape[0] * ref.shape[1])
        if region.page >= len(cand_pages):
            res.message = f"candidate has only {len(cand_pages)} page(s)"
            continue
        page = page_array(region.page)
        if region.page in size_note and not resize:
            res.status = "fail"
            res.message = f"page size differs ({size_note[region.page]}); use --resize to scale"
            continue
        aligned = _best_alignment(page, ref, region, tol)
        if aligned is None:
            res.message = "region falls outside the candidate page"
            continue
        dx, dy, cand = aligned
        diff, bad = _bad_mask(ref, cand, tol.threshold)
        res.offset = [dx, dy]
        res.diff_pixels = int(bad.sum())
        res.diff_percent = round(100.0 * res.diff_pixels / max(1, res.total_pixels), 4)
        res.max_channel_diff = int(diff.max()) if diff.size else 0
        res.mean_abs_diff = round(float(np.abs(ref.astype(np.int16) - cand.astype(np.int16)).mean()), 4)
        ok = res.diff_percent <= tol.max_diff_percent if tol.max_diff_percent > 0 else res.diff_pixels == 0
        res.status = "pass" if ok else "fail"
        if ok:
            res.message = "identical" if res.max_channel_diff == 0 else "within tolerance"
        else:
            res.message = (f"{res.diff_pixels} of {res.total_pixels} pixels differ "
                           f"({res.diff_percent}% > {tol.max_diff_percent}% allowed, threshold {tol.threshold})")
        if (dx, dy) != (0, 0):
            res.message += f"; best match shifted by ({dx}, {dy}) px"
        if region.page in size_note:
            res.message += f"; candidate page resized from {size_note[region.page]}"
        if out:
            stem = f"regions/{idx:02d}_{safe_filename(region.name, f'region{idx}')}"
            Image.fromarray(ref).save(out / f"{stem}_reference.png")
            Image.fromarray(np.ascontiguousarray(cand)).save(out / f"{stem}_candidate.png")
            make_diff_image(ref, cand, tol.threshold).save(out / f"{stem}_diff.png")
            res.images = {k: f"{stem}_{k}.png" for k in ("reference", "candidate", "diff")}

    report = CompareReport(
        template=template.name,
        candidate=candidate_name,
        dpi=template.dpi,
        results=results,
        page_sizes={str(i + 1): list(p.size) for i, p in enumerate(cand_pages)},
        out_dir=str(out) if out else None,
    )
    if out:
        report.pages = _write_overviews(out, cand_pages, arrays, results)
        from .report import write_html

        with open(out / "report.json", "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)
        write_html(report, out / "report.html")
    return report


def _write_overviews(out: Path, cand_pages, arrays, results) -> list[str]:
    colors = {"pass": (0, 170, 60), "fail": (230, 0, 0), "error": (255, 140, 0)}
    paths = []
    pages_used = sorted({r.page for r in results if r.page < len(cand_pages)})
    for p in pages_used:
        img = Image.fromarray(arrays[p]) if p in arrays else cand_pages[p].convert("RGB")
        img = img.copy()
        draw = ImageDraw.Draw(img)
        lw = max(2, img.width // 400)
        for r in results:
            if r.page != p:
                continue
            x0, y0, x1, y1 = r.box
            dx, dy = r.offset
            draw.rectangle([x0 + dx, y0 + dy, x1 + dx - 1, y1 + dy - 1], outline=colors[r.status], width=lw)
            draw.text((x0 + dx + 3, max(0, y0 + dy - 12)), r.name, fill=colors[r.status])
        rel = f"page_{p + 1}.png"
        img.save(out / rel)
        paths.append(rel)
    return paths


def compare_file(
    template: str | os.PathLike | Template,
    candidate,
    out_dir: str | os.PathLike | None = None,
    resize: bool = False,
    candidate_name: str | None = None,
    only: list[str] | None = None,
    **overrides,
) -> CompareReport:
    """Compare *candidate* to *template*.

    *candidate* may be a path, bytes, a binary file object or a Playwright (sync) ``Download``.
    *only* limits the check to the named regions. Overrides: threshold, max_diff_percent, shift.
    """
    tpl = template if isinstance(template, Template) else Template.load(template)
    if only:
        tpl = filter_regions(tpl, only)
    path, name = materialize(candidate, candidate_name)
    pages = render_file(path, tpl.dpi)
    overrides = {k: v for k, v in overrides.items() if v is not None}
    return compare_pages(tpl, pages, name, out_dir, resize, overrides or None)


def filter_regions(tpl: Template, names) -> Template:
    import copy

    if isinstance(names, str):
        names = [names]
    wanted = {n.casefold() for n in names}
    out = copy.copy(tpl)
    out.regions = [r for r in tpl.regions if r.name.casefold() in wanted]
    missing = wanted - {r.name.casefold() for r in out.regions}
    if missing:
        raise ValueError(f"template {tpl.name!r} has no region(s) named {sorted(missing)}")
    return out


def _raise_if_failed(report: CompareReport) -> CompareReport:
    if not report.passed:
        msg = report.summary()
        if report.out_dir:
            msg += f"\n  report: {Path(report.out_dir) / 'report.html'}"
        raise AssertionError(msg)
    return report


def assert_matches(template, candidate, out_dir=None, **kwargs) -> CompareReport:
    """Raise AssertionError (with a per-region summary) unless every region matches."""
    return _raise_if_failed(compare_file(template, candidate, out_dir=out_dir, **kwargs))


async def compare_file_async(template, candidate, out_dir=None, **kwargs) -> CompareReport:
    """Like compare_file, but also accepts Playwright *async* ``Download`` objects."""
    import asyncio

    path, name = await amaterialize(candidate, kwargs.pop("candidate_name", None))
    return await asyncio.to_thread(
        compare_file, template, path, out_dir=out_dir, candidate_name=name, **kwargs
    )


async def assert_matches_async(template, candidate, out_dir=None, **kwargs) -> CompareReport:
    return _raise_if_failed(await compare_file_async(template, candidate, out_dir=out_dir, **kwargs))
