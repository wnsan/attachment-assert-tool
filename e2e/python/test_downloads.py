"""pytest-playwright example: assert downloaded PDFs against a region template.

Run:  pytest e2e/python --attachment-assert-templates examples/templates
"""
import pytest

from attachment_assert import assert_matches


def test_download_matches_template(app, attachment_assert):
    with app.expect_download() as info:
        app.click("#dl-same")
    report = attachment_assert(info.value, "invoice")  # fixture: raises on mismatch
    assert [r.status for r in report.results] == ["pass", "pass", "pass"]


def test_changed_total_is_detected(app, attachment_assert):
    with app.expect_download() as info:
        app.click("#dl-changed")
    report = attachment_assert.compare(info.value, "invoice")  # no raise, inspect the report
    assert not report.passed
    assert {r.name: r.status for r in report.results} == {
        "header": "pass", "total": "fail", "header p2": "pass"}
    with pytest.raises(AssertionError, match="total"):
        attachment_assert.check(info.value, "invoice")


def test_only_selected_regions(app, attachment_assert):
    with app.expect_download() as info:
        app.click("#dl-changed")
    attachment_assert(info.value, "invoice", only=["header", "header p2"])


def test_plain_api_with_download(app, pytestconfig):
    with app.expect_download() as info:
        app.click("#dl-same")
    assert_matches(pytestconfig.rootpath / "examples/templates/invoice", info.value)
