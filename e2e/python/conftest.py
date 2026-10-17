import functools
import http.server
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "e2e" / "site"
FILES = ROOT / "examples"


class DemoHandler(http.server.SimpleHTTPRequestHandler):
    """/ -> e2e/site/index.html, /files/<name> -> examples/<name> as an attachment."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/files/"):
            f = FILES / Path(self.path).name
            if not f.is_file():
                return self.send_error(404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.path = "/index.html"
            super().do_GET()


@pytest.fixture(scope="session")
def demo_url():
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(DemoHandler, directory=str(SITE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def app(page, demo_url):
    page.goto(demo_url)
    return page
