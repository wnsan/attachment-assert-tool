"""Standalone HTML report for a CompareReport (images referenced relative to the report)."""
from __future__ import annotations

import html
from pathlib import Path

_CSS = """
body{font-family:system-ui,Segoe UI,Tahoma,sans-serif;margin:24px;color:#222;background:#f6f7f9}
h1{margin:0 0 4px} .muted{color:#666}
.banner{padding:12px 16px;border-radius:8px;font-weight:600;margin:16px 0;color:#fff}
.pass{background:#1a9b50}.fail{background:#d62828}.error{background:#e67e00}
.card{background:#fff;border-radius:8px;padding:12px 16px;margin:12px 0;box-shadow:0 1px 3px #0002}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;color:#fff;font-size:12px;margin-right:8px}
.imgs{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px}
.imgs figure{margin:0}.imgs img{max-width:420px;max-height:320px;border:1px solid #ccc;image-rendering:pixelated;background:#fff}
figcaption{font-size:12px;color:#666}
table{border-collapse:collapse;font-size:13px}td{padding:2px 10px 2px 0}
.overview img{max-width:100%;border:1px solid #ccc}
"""


def write_html(report, path: str | Path) -> None:
    e = html.escape
    c = report.counts
    status = "pass" if report.passed else "fail"
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{e(report.template)} - {status.upper()}</title><style>{_CSS}</style></head><body>",
        f"<h1>Attachment assert: {e(report.template)}</h1>",
        f"<div class='muted'>Candidate: {e(report.candidate)} &middot; DPI {report.dpi}</div>",
        f"<div class='banner {status}'>{status.upper()} &mdash; {c['pass']}/{len(report.results)} regions match"
        f" ({c['fail']} failed, {c['error']} errors)</div>",
    ]
    for r in report.results:
        parts.append("<div class='card'>")
        parts.append(f"<span class='tag {r.status}'>{r.status.upper()}</span><b>{e(r.name)}</b>"
                     f" <span class='muted'>page {r.page + 1}, box {r.box}</span>")
        parts.append(f"<div>{e(r.message)}</div><table>")
        for k, v in (("differing pixels", f"{r.diff_pixels} / {r.total_pixels} ({r.diff_percent}%)"),
                     ("max channel diff", r.max_channel_diff), ("mean abs diff", r.mean_abs_diff),
                     ("offset", r.offset), ("tolerance", r.tolerance)):
            parts.append(f"<tr><td class='muted'>{k}</td><td>{e(str(v))}</td></tr>")
        parts.append("</table>")
        if r.images:
            parts.append("<div class='imgs'>")
            for k in ("reference", "candidate", "diff"):
                parts.append(f"<figure><img src='{e(r.images[k])}'><figcaption>{k}</figcaption></figure>")
            parts.append("</div>")
        parts.append("</div>")
    if report.pages:
        parts.append("<h2>Candidate pages</h2>")
        for p in report.pages:
            parts.append(f"<div class='card overview'><div class='muted'>{e(p)}</div><img src='{e(p)}'></div>")
    parts.append("</body></html>")
    Path(path).write_text("\n".join(parts), encoding="utf-8")
