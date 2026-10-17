"""Region-based visual assertions for PDFs, images and documents."""
from .compare import compare_file, assert_matches, RegionResult, CompareReport
from .template import Template, Region, create_template

__all__ = [
    "compare_file", "assert_matches", "RegionResult", "CompareReport",
    "Template", "Region", "create_template",
]
__version__ = "0.1.0"
