"""
Pre-Conversion Scanner

Convenience re-exports for the pre-conversion scanning phase.

Issue: #1769 - Split pre_conversion_scanner.py into focused modules
"""

from .models import (
    RiskSeverity,
    RiskCategory,
    RiskItem,
    ScanMetadata,
    PreConversionScanResult,
)
from .analyzer import PreConversionScanner

__all__ = [
    "RiskSeverity",
    "RiskCategory",
    "RiskItem",
    "ScanMetadata",
    "PreConversionScanResult",
    "PreConversionScanner",
    "scan_mod_file",
]


async def scan_mod_file(file_path: str, filename: str) -> PreConversionScanResult:
    """
    Convenience function to scan a mod file.

    Args:
        file_path: Path to the mod file
        filename: Original filename

    Returns:
        PreConversionScanResult with identified risks
    """
    scanner = PreConversionScanner()
    return await scanner.scan_file(file_path, filename)
