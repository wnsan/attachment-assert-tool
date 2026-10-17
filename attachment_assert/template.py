"""Template = reference file + named regions (+ cropped reference pixels)."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from .render import DEFAULT_DPI, render_file

FORMAT = "attachment-assert/1"
TEMPLATE_FILE = "template.json"

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "item") -> str:
    """Filesystem-safe name that keeps Unicode (e.g. Thai) intact."""
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(". ")
    return cleaned or fallback


@dataclass
class Tolerance:
    threshold: int = 0             # per-channel difference (0-255) still counted as "same"
    max_diff_percent: float = 0.0  # % of region pixels allowed to exceed threshold
    shift: int = 0                 # search +/- N px for the best alignment

    @classmethod
    def from_dict(cls, d: dict | None, base: "Tolerance | None" = None) -> "Tolerance":
        base = base or cls()
        d = d or {}

        def pick(key, typ):
            v = d.get(key)
            return getattr(base, key) if v is None or v == "" else typ(v)

        return cls(
            threshold=pick("threshold", int),
            max_diff_percent=pick("max_diff_percent", float),
            shift=pick("shift", int),
        )


@dataclass
class Region:
    name: str
    page: int  # 0-based
    x: int
    y: int
    w: int
    h: int
    threshold: int | None = None
    max_diff_percent: float | None = None
    shift: int | None = None
    image: str | None = None  # path relative to the template dir

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def tolerance(self, defaults: Tolerance) -> Tolerance:
        return Tolerance.from_dict(
            {"threshold": self.threshold, "max_diff_percent": self.max_diff_percent, "shift": self.shift},
            defaults,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        def opt(key, typ):
            v = d.get(key)
            return None if v is None or v == "" else typ(v)

        return cls(
            name=str(d["name"]).strip(),
            page=int(d.get("page", 0)),
            x=int(round(float(d["x"]))),
            y=int(round(float(d["y"]))),
            w=int(round(float(d["w"]))),
            h=int(round(float(d["h"]))),
            threshold=opt("threshold", int),
            max_diff_percent=opt("max_diff_percent", float),
            shift=opt("shift", int),
            image=d.get("image"),
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Template:
    path: Path
    name: str
    dpi: int
    regions: list[Region]
    defaults: Tolerance = field(default_factory=Tolerance)
    reference: dict = field(default_factory=dict)
    created: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "Template":
        path = Path(path)
        if path.is_file():
            path = path.parent
        with open(path / TEMPLATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(
            path=path,
            name=data.get("name", path.name),
            dpi=int(data.get("dpi", DEFAULT_DPI)),
            regions=[Region.from_dict(r) for r in data.get("regions", [])],
            defaults=Tolerance.from_dict(data.get("defaults")),
            reference=data.get("reference", {}),
            created=data.get("created", ""),
        )

    @property
    def reference_path(self) -> Path | None:
        f = self.reference.get("file")
        return self.path / f if f else None

    def region_image(self, region: Region) -> Image.Image:
        if not region.image:
            raise FileNotFoundError(f"Region {region.name!r} has no stored reference image")
        with Image.open(self.path / region.image) as img:
            return img.convert("RGB")

    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "name": self.name,
            "created": self.created,
            "dpi": self.dpi,
            "reference": self.reference,
            "defaults": asdict(self.defaults),
            "regions": [r.to_dict() for r in self.regions],
        }

    def save_json(self) -> None:
        with open(self.path / TEMPLATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)


def validate_regions(regions: list[Region], page_sizes: list[tuple[int, int]]) -> None:
    seen: set[str] = set()
    for r in regions:
        if not r.name:
            raise ValueError("Every region needs a name")
        key = r.name.casefold()
        if key in seen:
            raise ValueError(f"Duplicate region name: {r.name!r}")
        seen.add(key)
        if not 0 <= r.page < len(page_sizes):
            raise ValueError(f"Region {r.name!r}: page {r.page + 1} does not exist")
        pw, ph = page_sizes[r.page]
        if r.w <= 0 or r.h <= 0:
            raise ValueError(f"Region {r.name!r}: width/height must be positive")
        if r.x < 0 or r.y < 0 or r.x + r.w > pw or r.y + r.h > ph:
            raise ValueError(
                f"Region {r.name!r}: box {r.box} is outside page {r.page + 1} ({pw}x{ph})"
            )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def create_template(
    reference: str | Path,
    regions: list[Region | dict],
    out_dir: str | Path,
    dpi: int = DEFAULT_DPI,
    name: str | None = None,
    defaults: Tolerance | dict | None = None,
    pages: list[Image.Image] | None = None,
    original_name: str | None = None,
) -> Template:
    """Create (or overwrite) a template folder from a reference file and region boxes."""
    reference = Path(reference)
    out_dir = Path(out_dir)
    regions = [r if isinstance(r, Region) else Region.from_dict(r) for r in regions]
    if not isinstance(defaults, Tolerance):
        defaults = Tolerance.from_dict(defaults)
    if pages is None:
        pages = render_file(reference, dpi)
    page_sizes = [p.size for p in pages]
    validate_regions(regions, page_sizes)

    out_dir.mkdir(parents=True, exist_ok=True)
    region_dir = out_dir / "regions"
    if region_dir.exists():
        shutil.rmtree(region_dir)
    region_dir.mkdir()

    ref_name = "reference" + reference.suffix.lower()
    ref_dest = out_dir / ref_name
    for old in out_dir.glob("reference.*"):
        if old.resolve() != reference.resolve():
            old.unlink()
    if reference.resolve() != ref_dest.resolve():
        shutil.copyfile(reference, ref_dest)

    for i, r in enumerate(regions, 1):
        rel = f"regions/{i:02d}_{safe_filename(r.name, f'region{i}')}.png"
        pages[r.page].crop(r.box).save(out_dir / rel)
        r.image = rel

    tpl = Template(
        path=out_dir,
        name=name or out_dir.name,
        dpi=dpi,
        regions=regions,
        defaults=defaults,
        reference={
            "file": ref_name,
            "original_name": original_name or reference.name,
            "sha256": _sha256(ref_dest),
            "pages": len(pages),
            "page_sizes": [list(s) for s in page_sizes],
        },
        created=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    )
    tpl.save_json()
    return tpl
