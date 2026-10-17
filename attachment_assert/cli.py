"""Command line interface: ui / compare / create / show / render."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .render import DEFAULT_DPI, RenderError, render_file


def _parse_region(spec: str) -> dict:
    # name:page:x,y,w,h   (page is 1-based)
    try:
        name, page, box = spec.rsplit(":", 2)
        x, y, w, h = (int(v) for v in box.split(","))
        return {"name": name, "page": int(page) - 1, "x": x, "y": y, "w": w, "h": h}
    except Exception:
        raise argparse.ArgumentTypeError(f"bad region {spec!r}; expected name:page:x,y,w,h")


def _add_tolerance(p: argparse.ArgumentParser, default_none: bool) -> None:
    d = None if default_none else 0
    p.add_argument("--threshold", type=int, default=d,
                   help="per-channel difference 0-255 still treated as equal")
    p.add_argument("--max-diff-percent", type=float, default=None if default_none else 0.0,
                   help="percent of region pixels allowed to differ")
    p.add_argument("--shift", type=int, default=d,
                   help="search +/-N pixels for the best alignment")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="attachment-assert", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ui", help="open the browser UI to define templates and compare files")
    p.add_argument("--workspace", default="attachment_assert_workspace",
                   help="folder holding templates/ and runs/ (default: %(default)s)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")

    p = sub.add_parser("compare", help="compare a file against a template (exit 1 on mismatch)")
    p.add_argument("template", help="template folder (or its template.json)")
    p.add_argument("candidate", nargs="+", help="file(s) to check")
    p.add_argument("--out", help="write report.html/report.json + crops here "
                                 "(sub-folder per candidate when several)")
    p.add_argument("--resize", action="store_true",
                   help="scale candidate pages to the reference page size when they differ")
    p.add_argument("--json", action="store_true", help="print JSON instead of a text summary")
    p.add_argument("--only", action="append", help="only check these region names (repeatable)")
    _add_tolerance(p, default_none=True)

    p = sub.add_parser("create", help="create a template from the command line")
    p.add_argument("reference")
    p.add_argument("--out", required=True, help="template folder to create")
    p.add_argument("--region", action="append", type=_parse_region, required=True,
                   metavar="NAME:PAGE:X,Y,W,H", help="pixel box at --dpi, page is 1-based")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    p.add_argument("--name")
    _add_tolerance(p, default_none=False)

    p = sub.add_parser("show", help="list the regions of a template")
    p.add_argument("template")

    p = sub.add_parser("render", help="render a file to PNG pages (to measure boxes)")
    p.add_argument("file")
    p.add_argument("--out", required=True)
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)

    args = ap.parse_args(argv)
    try:
        return _run(args)
    except (RenderError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args) -> int:
    if args.cmd == "ui":
        from .server import serve

        serve(Path(args.workspace), args.host, args.port, open_browser=not args.no_browser)
        return 0

    if args.cmd == "compare":
        from .compare import compare_pages
        from .template import Template

        tpl = Template.load(args.template)
        if args.only:
            wanted = {n.casefold() for n in args.only}
            tpl.regions = [r for r in tpl.regions if r.name.casefold() in wanted]
            if not tpl.regions:
                raise ValueError(f"no regions named {args.only}")
        overrides = {k: v for k, v in (("threshold", args.threshold),
                                       ("max_diff_percent", args.max_diff_percent),
                                       ("shift", args.shift)) if v is not None}
        all_ok, out_json = True, []
        for cand in args.candidate:
            out = None
            if args.out:
                out = Path(args.out) / Path(cand).stem if len(args.candidate) > 1 else Path(args.out)
            rep = compare_pages(tpl, render_file(cand, tpl.dpi), Path(cand).name, out,
                                args.resize, overrides or None)
            all_ok &= rep.passed
            if args.json:
                out_json.append(rep.to_dict())
            else:
                print(rep.summary())
                if out:
                    print(f"  report: {out / 'report.html'}")
        if args.json:
            print(json.dumps(out_json[0] if len(out_json) == 1 else out_json, ensure_ascii=False, indent=2))
        return 0 if all_ok else 1

    if args.cmd == "create":
        from .template import create_template

        tpl = create_template(
            args.reference, args.region, args.out, dpi=args.dpi, name=args.name,
            defaults={"threshold": args.threshold, "max_diff_percent": args.max_diff_percent or 0.0,
                      "shift": args.shift},
        )
        print(f"created template {tpl.path} with {len(tpl.regions)} region(s)")
        return 0

    if args.cmd == "show":
        from .template import Template

        tpl = Template.load(args.template)
        print(f"{tpl.name}: reference {tpl.reference.get('original_name')} @ {tpl.dpi} dpi, "
              f"defaults {tpl.defaults}")
        for r in tpl.regions:
            print(f"  {r.name:<30} page {r.page + 1}  x={r.x} y={r.y} w={r.w} h={r.h}  "
                  f"{r.tolerance(tpl.defaults)}")
        return 0

    if args.cmd == "render":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for i, page in enumerate(render_file(args.file, args.dpi), 1):
            page.save(out / f"page_{i}.png")
            print(f"page_{i}.png  {page.size[0]}x{page.size[1]}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
