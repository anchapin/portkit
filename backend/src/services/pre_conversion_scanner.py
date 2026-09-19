"""
Pre-Conversion Feature Scanner

.. deprecated::
    Use :mod:`services.pre_conversion` instead.
    This module is a backwards-compatibility shim.

    - ``services.pre_conversion.models`` — RiskSeverity, RiskCategory, RiskItem, ScanMetadata, PreConversionScanResult
    - ``services.pre_conversion.analyzer`` — PreConversionScanner
    - ``services.pre_conversion`` — scan_mod_file convenience function

Issue: #1769 - Split pre_conversion_scanner.py into focused modules
"""

# Re-export all public symbols from the new module structure
from services.pre_conversion import (
    RiskSeverity,
    RiskCategory,
    RiskItem,
    ScanMetadata,
    PreConversionScanResult,
    PreConversionScanner,
    scan_mod_file,
)

__all__ = [
    "RiskSeverity",
    "RiskCategory",
    "RiskItem",
    "ScanMetadata",
    "PreConversionScanResult",
    "PreConversionScanner",
    "scan_mod_file",
]
