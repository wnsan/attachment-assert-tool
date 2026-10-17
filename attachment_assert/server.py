"""Tiny stdlib HTTP server backing the browser UI."""
from __future__ import annotations

import io
import json
import shutil
import threading
import traceback
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .compare import compare_pages
from .render import DEFAULT_DPI, render_file, supported_exts
from .template import TEMPLATE_FILE, Template, create_template, safe_filename

STATIC = Path(__file__).with_name("static")
MAX_UPLOAD = 300 * 1024 * 1024
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".png": "image/png", ".json": "application/json"}


class Doc:
    def __init__(self, doc_id: str, path: Path, name: str, dpi: int):
        self.id, self.path, self.name, self.dpi = doc_id, path, name, dpi
        self.pages = render_file(path, dpi)
        self._png: dict[int, bytes] = {}

    def info(self) -> dict:
        return {"id": self.id, "name": self.name, "dpi": self.dpi,
                "pages": [{"w": p.width, "h": p.height} for p in self.pages]}

    def png(self, i: int) -> bytes:
        if i not in self._png:
            buf = io.BytesIO()
            self.pages[i].save(buf, "PNG")
            self._png[i] = buf.getvalue()
        return self._png[i]


class App:
    def __init__(self, workspace: Path):
        self.ws = workspace
        self.templates = workspace / "templates"
        self.uploads = workspace / "uploads"
        self.runs = workspace / "runs"
        for d in (self.templates, self.uploads, self.runs):
            d.mkdir(parents=True, exist_ok=True)
        self.docs: dict[str, Doc] = {}
        self.lock = threading.Lock()

    def template_dir(self, name: str) -> Path:
        path = (self.templates / safe_filename(name, "template")).resolve()
        if path.parent != self.templates.resolve():
            raise ValueError("bad template name")
        return path

    def list_templates(self) -> list[dict]:
        out = []
        for d in sorted(self.templates.iterdir()):
            if (d / TEMPLATE_FILE).exists():
                try:
                    t = Template.load(d)
                    out.append({"name": t.name, "dir": d.name, "regions": len(t.regions),
                                "reference": t.reference.get("original_name"), "dpi": t.dpi,
                                "created": t.created})
                except Exception as exc:
                    out.append({"name": d.name, "dir": d.name, "error": str(exc)})
        return out

    def add_doc(self, data: bytes, filename: str, dpi: int) -> Doc:
        doc_id = uuid.uuid4().hex[:12]
        folder = self.uploads / doc_id
        folder.mkdir(parents=True)
        path = folder / safe_filename(Path(filename).name, "upload")
        path.write_bytes(data)
        doc = Doc(doc_id, path, Path(filename).name, dpi)
        with self.lock:
            self.docs[doc_id] = doc
        return doc

    def doc(self, doc_id: str) -> Doc:
        doc = self.docs.get(doc_id)
        if not doc:
            raise KeyError("document not loaded (server restarted?) - open the file again")
        return doc


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "attachment-assert/0.1"

    def log_message(self, fmt, *args):
        pass

    # ---- helpers -------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("file too large")
        return self.rfile.read(n)

    def _file(self, path: Path, root: Path):
        path = path.resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return self._json({"error": "not found"}, 404)
        self._send(200, path.read_bytes(), CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def _dispatch(self, method: str):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            self._route(method, parts, q)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            self._json({"error": str(exc).strip("'\"")}, 400)
        except Exception as exc:
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # ---- routes --------------------------------------------------------
    def _route(self, m: str, p: list[str], q: dict):
        app = self.app
        if m == "GET" and (not p or p == ["index.html"]):
            return self._file(STATIC / "index.html", STATIC)
        if m == "GET" and p[0] == "static":
            return self._file(STATIC.joinpath(*p[1:]), STATIC)
        if m == "GET" and p[0] == "runs":
            return self._file(app.runs.joinpath(*p[1:]), app.runs)
        if p[0] != "api":
            return self._json({"error": "not found"}, 404)
        p = p[1:]

        if m == "GET" and p == ["info"]:
            return self._json({"exts": supported_exts(), "workspace": str(app.ws.resolve()),
                               "default_dpi": DEFAULT_DPI})

        if m == "POST" and p == ["upload"]:
            name = unquote(self.headers.get("X-Filename", "upload"))
            doc = app.add_doc(self._body(), name, int(q.get("dpi", DEFAULT_DPI)))
            return self._json(doc.info())

        if m == "GET" and len(p) == 4 and p[0] == "doc" and p[2] == "page":
            doc = app.doc(p[1])
            return self._send(200, doc.png(int(p[3].split(".")[0])), "image/png")

        if p and p[0] == "templates":
            if m == "GET" and len(p) == 1:
                return self._json(app.list_templates())
            if m == "POST" and len(p) == 1:
                return self._save_template(json.loads(self._body() or b"{}"))
            tdir = app.template_dir(p[1])
            if m == "GET" and len(p) == 2:
                tpl = Template.load(tdir)
                ref = tpl.reference_path
                doc = None
                if ref and ref.exists():
                    doc = Doc(uuid.uuid4().hex[:12], ref, tpl.reference.get("original_name", ref.name), tpl.dpi)
                    with app.lock:
                        app.docs[doc.id] = doc
                return self._json({"template": tpl.to_dict(), "doc": doc.info() if doc else None})
            if m == "GET" and len(p) == 3 and p[2] == "zip":
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in tdir.rglob("*"):
                        if f.is_file():
                            zf.write(f, Path(tdir.name) / f.relative_to(tdir))
                fname = tdir.name + ".zip"
                return self._send(200, buf.getvalue(), "application/zip", {
                    "Content-Disposition": f"attachment; filename*=UTF-8''{_quote(fname)}"})
            if m == "DELETE" and len(p) == 2:
                shutil.rmtree(tdir)
                return self._json({"ok": True})

        if m == "POST" and p == ["compare"]:
            return self._compare(q)

        return self._json({"error": "not found"}, 404)

    def _save_template(self, body: dict):
        app = self.app
        name = str(body.get("name") or "").strip()
        if not name:
            raise ValueError("template name is required")
        doc = app.doc(body["doc_id"])
        tdir = app.template_dir(name)
        if tdir.exists() and not body.get("overwrite"):
            return self._json({"error": f"template {name!r} already exists", "exists": True}, 409)
        staging_ref = doc.path
        if tdir.exists() and doc.path.resolve().parent == tdir.resolve():
            staging = app.uploads / uuid.uuid4().hex[:12]
            staging.mkdir()
            staging_ref = staging / doc.path.name
            shutil.copyfile(doc.path, staging_ref)
            doc.path = staging_ref
        tpl = create_template(staging_ref, body.get("regions", []), tdir, dpi=doc.dpi, name=name,
                              defaults=body.get("defaults"), pages=doc.pages, original_name=doc.name)
        return self._json({"ok": True, "template": tpl.to_dict()})

    def _compare(self, q: dict):
        app = self.app
        tpl = Template.load(app.template_dir(q["template"]))
        run_id = uuid.uuid4().hex[:12]
        out = app.runs / run_id
        (out / "input").mkdir(parents=True)
        fname = unquote(self.headers.get("X-Filename", "candidate"))
        cand = out / "input" / safe_filename(Path(fname).name, "candidate")
        cand.write_bytes(self._body())
        overrides = {}
        for key, typ in (("threshold", int), ("max_diff_percent", float), ("shift", int)):
            if q.get(key) not in (None, ""):
                overrides[key] = typ(q[key])
        rep = compare_pages(tpl, render_file(cand, tpl.dpi), Path(fname).name, out,
                            q.get("resize") in ("1", "true"), overrides or None)
        data = rep.to_dict()
        data["run"] = f"/runs/{run_id}/"
        return self._json(data)


def _quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s)


def serve(workspace: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    app = App(workspace)
    handler = type("BoundHandler", (Handler,), {"app": app})
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    print(f"Attachment Assert UI: {url}\nWorkspace: {workspace.resolve()}\nCtrl+C to stop")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
