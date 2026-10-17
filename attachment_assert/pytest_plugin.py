"""pytest plugin: ``attachment_assert`` fixture for e2e tests (pytest-playwright friendly).

Auto-registered via the ``pytest11`` entry point when the package is pip-installed;
otherwise add ``pytest_plugins = ["attachment_assert.pytest_plugin"]`` to conftest.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .compare import (
    CompareReport, _raise_if_failed, compare_file, compare_file_async,
)


def pytest_addoption(parser):
    group = parser.getgroup("attachment-assert")
    group.addoption("--attachment-assert-output", default=None,
                    help="folder for attachment-assert reports (default: test-results/attachment-assert)")
    group.addoption("--attachment-assert-templates", default=None,
                    help="base folder for relative template paths")
    parser.addini("attachment_assert_output", "folder for attachment-assert reports",
                  default="test-results/attachment-assert")
    parser.addini("attachment_assert_templates", "base folder for relative template paths", default="")


class AttachmentAssert:
    """Per-test helper. ``check`` raises AssertionError on mismatch, ``compare`` returns the report."""

    def __init__(self, request):
        cfg = request.config
        root = Path(cfg.rootpath)
        out = cfg.getoption("attachment_assert_output") or cfg.getini("attachment_assert_output")
        tpl = cfg.getoption("attachment_assert_templates") or cfg.getini("attachment_assert_templates")
        self.output_root = (root / out).resolve()
        self.templates_root = (root / tpl).resolve() if tpl else root
        node = re.sub(r'[<>:"/\\|?*\[\]\s]+', "_", request.node.nodeid).strip("_")
        self.test_dir = self.output_root / node[-150:]
        self.reports: list[CompareReport] = []
        self._n = 0

    def template_path(self, template) -> Path:
        p = Path(template)
        return p if p.is_absolute() else self.templates_root / p

    def _out_dir(self, template) -> Path:
        self._n += 1
        return self.test_dir / f"{self._n:02d}_{Path(str(template)).name}"

    def compare(self, candidate, template, **kwargs) -> CompareReport:
        kwargs.setdefault("out_dir", self._out_dir(template))
        rep = compare_file(self.template_path(template), candidate, **kwargs)
        self.reports.append(rep)
        return rep

    def check(self, candidate, template, **kwargs) -> CompareReport:
        return _raise_if_failed(self.compare(candidate, template, **kwargs))

    async def compare_async(self, candidate, template, **kwargs) -> CompareReport:
        kwargs.setdefault("out_dir", self._out_dir(template))
        rep = await compare_file_async(self.template_path(template), candidate, **kwargs)
        self.reports.append(rep)
        return rep

    async def check_async(self, candidate, template, **kwargs) -> CompareReport:
        return _raise_if_failed(await self.compare_async(candidate, template, **kwargs))

    __call__ = check


@pytest.fixture
def attachment_assert(request) -> AttachmentAssert:
    """``attachment_assert(download_or_path_or_bytes, "templates/invoice", shift=2)``"""
    return AttachmentAssert(request)
