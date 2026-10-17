"""Region-based visual assertions for PDFs, images and documents."""
from .compare import (
    CompareReport, RegionResult, assert_matches, assert_matches_async, compare_file,
    compare_file_async,
)
from .template import Region, Template, create_template

__all__ = [
    "compare_file", "assert_matches", "compare_file_async", "assert_matches_async",
    "RegionResult", "CompareReport", "Template", "Region", "create_template",
]
__version__ = "0.2.0"
