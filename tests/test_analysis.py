"""High-level analyze() entrypoint + address validation."""

from __future__ import annotations

import pytest

from chain_scout import config
from chain_scout.analysis import analyze, validate_address


def test_validate_address_accepts_checksummed_hex():
    assert validate_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045").startswith("0x")


def test_validate_address_rejects_garbage():
    for bad in ("", "vitalik.eth", "0x1234", "0x" + "z" * 40, "0x" + "1" * 39):
        with pytest.raises(ValueError):
            validate_address(bad)


def test_analyze_fixture_end_to_end():
    snap, report = analyze(config.DEMO_WALLET_ADDRESS, "fixture")
    assert snap.data_source == "fixture"
    assert 0 <= report.score <= 100
    assert report.band in ("Low", "Moderate", "Elevated", "High")
    assert report.total_value_usd is not None
    # the demo wallet carries warnings by design (it exercises every branch)
    assert len(report.warnings) >= 1
    assert report.pnl is not None


def test_analyze_invalid_address_rejected():
    with pytest.raises(ValueError):
        analyze("nope", "fixture")


def test_analyze_unknown_source_rejected():
    with pytest.raises(ValueError):
        analyze(config.DEMO_WALLET_ADDRESS, "telepathy")