import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

from attachment_assert import assert_matches, compare_file, create_template
from attachment_assert.cli import main as cli_main
from attachment_assert.render import render_file


def make_doc(path: Path, text="INVOICE 001", total="TOTAL 100.00", pages=2, fmt=None):
    imgs = []
    for p in range(pages):
        im = Image.new("RGB", (600, 800), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([40, 40, 560, 120], outline="black", width=3)
        d.text((60, 70), f"{text} p{p + 1}", fill="black")
        d.rectangle([380, 680, 560, 740], fill=(230, 240, 255))
        d.text((390, 700), total, fill="navy")
        imgs.append(im)
    if path.suffix.lower() == ".pdf":
        imgs[0].save(path, save_all=True, append_images=imgs[1:], resolution=72)
    else:
        imgs[0].save(path, format=fmt)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aat_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class RenderTests(Base):
    def test_pdf_pages_and_dpi(self):
        pdf = make_doc(self.tmp / "a.pdf")
        pages = render_file(pdf, dpi=72)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].size, (600, 800))
        self.assertEqual(render_file(pdf, dpi=144)[0].size, (1200, 1600))

    def test_png_and_extensionless_sniffing(self):
        png = make_doc(self.tmp / "a.png", pages=1)
        noext = self.tmp / "blob"
        shutil.copyfile(png, noext)
        self.assertEqual(render_file(noext)[0].size, (600, 800))


class CompareTests(Base):
    def _template(self, ref, **kw):
        regions = [
            {"name": "header", "page": 0, "x": 40, "y": 40, "w": 521, "h": 81},
            {"name": "ยอดรวม", "page": 0, "x": 380, "y": 680, "w": 181, "h": 61},
            {"name": "header p2", "page": 1, "x": 40, "y": 40, "w": 521, "h": 81},
        ]
        return create_template(ref, regions, self.tmp / "tpl", dpi=72, **kw)

    def test_identical_pdf_passes(self):
        ref = make_doc(self.tmp / "ref.pdf")
        tpl = self._template(ref)
        self.assertTrue((tpl.path / "reference.pdf").exists())
        rep = assert_matches(tpl.path, make_doc(self.tmp / "same.pdf"), out_dir=self.tmp / "out")
        self.assertTrue(rep.passed)
        self.assertTrue((self.tmp / "out" / "report.html").exists())
        data = json.loads((self.tmp / "out" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(data["counts"]["pass"], 3)

    def test_changed_region_fails_others_pass(self):
        ref = make_doc(self.tmp / "ref.pdf")
        tpl = self._template(ref)
        cand = make_doc(self.tmp / "cand.pdf", total="TOTAL 999.00")
        rep = compare_file(tpl.path, cand, out_dir=self.tmp / "out")
        status = {r.name: r.status for r in rep.results}
        self.assertEqual(status, {"header": "pass", "ยอดรวม": "fail", "header p2": "pass"})
        self.assertFalse(rep.passed)
        failed = next(r for r in rep.results if r.status == "fail")
        self.assertGreater(failed.diff_pixels, 0)
        self.assertTrue((self.tmp / "out" / failed.images["diff"]).exists())
        with self.assertRaises(AssertionError) as ctx:
            assert_matches(tpl.path, cand)
        self.assertIn("ยอดรวม", str(ctx.exception))

    def test_tolerance_threshold_and_percent(self):
        ref = make_doc(self.tmp / "ref.png", pages=1)
        im = Image.open(ref).convert("RGB")
        px = im.load()
        for x in range(40, 200):  # small brightness change inside header
            px[x, 100] = tuple(max(0, c - 5) for c in px[x, 100])
        cand = self.tmp / "cand.png"
        im.save(cand)
        tpl = create_template(ref, [{"name": "header", "page": 0, "x": 40, "y": 40, "w": 521, "h": 81}],
                              self.tmp / "tpl")
        self.assertFalse(compare_file(tpl.path, cand).passed)
        self.assertTrue(compare_file(tpl.path, cand, threshold=5).passed)
        self.assertTrue(compare_file(tpl.path, cand, max_diff_percent=1.0).passed)

    def test_shift_search(self):
        ref = make_doc(self.tmp / "ref.png", pages=1)
        im = Image.open(ref).convert("RGB")
        shifted = Image.new("RGB", im.size, "white")
        shifted.paste(im, (3, 2))
        cand = self.tmp / "shifted.png"
        shifted.save(cand)
        tpl = create_template(ref, [{"name": "total", "page": 0, "x": 370, "y": 670, "w": 200, "h": 80}],
                              self.tmp / "tpl")
        self.assertFalse(compare_file(tpl.path, cand).passed)
        rep = compare_file(tpl.path, cand, shift=4)
        self.assertTrue(rep.passed)
        self.assertEqual(rep.results[0].offset, [3, 2])

    def test_page_size_mismatch_and_missing_page(self):
        ref = make_doc(self.tmp / "ref.pdf")
        tpl = self._template(ref)
        one_page = make_doc(self.tmp / "one.pdf", pages=1)
        rep = compare_file(tpl.path, one_page)
        self.assertEqual(rep.results[2].status, "error")
        big = make_doc(self.tmp / "big.png", pages=1)
        Image.open(big).resize((660, 880)).save(big)
        rep = compare_file(tpl.path, big)
        self.assertIn("page size differs", rep.results[0].message)

    def test_invalid_regions_rejected(self):
        ref = make_doc(self.tmp / "ref.png", pages=1)
        with self.assertRaises(ValueError):
            create_template(ref, [{"name": "a", "page": 0, "x": 500, "y": 0, "w": 200, "h": 10}], self.tmp / "t")
        with self.assertRaises(ValueError):
            create_template(ref, [{"name": "a", "page": 0, "x": 0, "y": 0, "w": 5, "h": 5},
                                  {"name": "A", "page": 0, "x": 0, "y": 0, "w": 5, "h": 5}], self.tmp / "t")


class CliTests(Base):
    def test_create_and_compare_exit_codes(self):
        ref = make_doc(self.tmp / "ref.pdf")
        tpl = self.tmp / "tpl"
        self.assertEqual(cli_main(["create", str(ref), "--out", str(tpl), "--dpi", "72",
                                   "--region", "header:1:40,40,521,81",
                                   "--region", "total:1:380,680,181,61"]), 0)
        self.assertEqual(cli_main(["compare", str(tpl), str(make_doc(self.tmp / "s.pdf"))]), 0)
        bad = make_doc(self.tmp / "bad.pdf", total="TOTAL 1.00")
        self.assertEqual(cli_main(["compare", str(tpl), str(bad), "--out", str(self.tmp / "o")]), 1)
        self.assertEqual(cli_main(["compare", str(tpl), str(bad), "--only", "header"]), 0)
        self.assertEqual(cli_main(["compare", str(tpl), str(self.tmp / "missing.pdf")]), 2)


class ServerTests(Base):
    def test_upload_save_compare_roundtrip(self):
        from http.server import ThreadingHTTPServer

        from attachment_assert.server import App, Handler

        app = App(self.tmp / "ws")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (Handler,), {"app": app}))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def call(method, path, data=None, headers=None):
            req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
            with urllib.request.urlopen(req) as r:
                body = r.read()
                return json.loads(body) if r.headers.get_content_type() == "application/json" else body

        try:
            self.assertIn(b"Attachment Assert", call("GET", "/"))
            ref = make_doc(self.tmp / "ref.pdf").read_bytes()
            doc = call("POST", "/api/upload?dpi=72", ref, {"X-Filename": "ref.pdf"})
            self.assertEqual(len(doc["pages"]), 2)
            png = call("GET", f"/api/doc/{doc['id']}/page/1.png")
            self.assertEqual(Image.open(io.BytesIO(png)).size, (600, 800))
            body = json.dumps({"name": "ใบแจ้งหนี้", "doc_id": doc["id"], "regions": [
                {"name": "total", "page": 0, "x": 380, "y": 680, "w": 181, "h": 61}]}).encode()
            call("POST", "/api/templates", body, {"Content-Type": "application/json"})
            self.assertEqual(call("GET", "/api/templates")[0]["name"], "ใบแจ้งหนี้")
            q = urllib.parse.quote("ใบแจ้งหนี้")
            ok = call("POST", f"/api/compare?template={q}", ref, {"X-Filename": "c.pdf"})
            self.assertTrue(ok["passed"])
            bad = make_doc(self.tmp / "bad.pdf", total="TOTAL 5").read_bytes()
            rep = call("POST", f"/api/compare?template={q}", bad, {"X-Filename": "bad.pdf"})
            self.assertFalse(rep["passed"])
            diff = call("GET", rep["run"] + rep["results"][0]["images"]["diff"])
            self.assertTrue(diff.startswith(b"\x89PNG"))
            loaded = call("GET", f"/api/templates/{q}")
            self.assertEqual(loaded["template"]["regions"][0]["name"], "total")
            # re-save the loaded template in place (reference file lives inside the template dir)
            body = json.dumps({"name": "ใบแจ้งหนี้", "doc_id": loaded["doc"]["id"], "overwrite": True,
                               "regions": loaded["template"]["regions"]}).encode()
            call("POST", "/api/templates", body, {"Content-Type": "application/json"})
            self.assertTrue(call("POST", f"/api/compare?template={q}", ref, {"X-Filename": "c.pdf"})["passed"])
            self.assertTrue(call("GET", f"/api/templates/{q}/zip").startswith(b"PK"))
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
