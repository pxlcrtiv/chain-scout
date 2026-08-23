"""Composite formula: renormalization over known signals."""

from __future__ import annotations

from chain_scout.models import SignalResult
from chain_scout.scoring import band_for, composite_score


def _sig(key: str, weight: float, severity: float, known: bool = True) -> SignalResult:
    return SignalResult(
        key=key, label=key, weight=weight, severity=severity, known=known,
        contribution=weight * severity,
    )


def test_all_known_denominator_is_one():
    signals = [_sig("a", 0.35, 1.0), _sig("b", 0.35, 0.5), _sig("c", 0.15, 0.0), _sig("d", 0.15, 0.25)]
    score, band = composite_score(signals)
    # 100*(0.35 + 0.175 + 0 + 0.0375)/1.0 = 56.25 -> 56
    assert score == 56
    assert band == "Elevated"


def test_unknown_signals_renormalize():
    signals = [
        _sig("a", 0.35, 1.0, known=False),   # excluded
        _sig("b", 0.35, 1.0),
        _sig("c", 0.15, 0.0),
        _sig("d", 0.15, 0.0, known=False),   # excluded
    ]
    score, _ = composite_score(signals)
    # denom = 0.35 + 0.15 = 0.5 -> 100*0.35/0.5 = 70
    assert score == 70


def test_unknown_does_not_punish():
    """An unknown signal must not lower the score of known signals."""
    only_bad_known = [_sig("a", 0.35, 1.0), _sig("b", 0.35, 0.0, known=False)]
    score, _ = composite_score(only_bad_known)
    assert score == 100  # the known signal alone is max risk


def test_composite_rounding():
    # Python round() is banker's: 24.5 -> 24, 25.5 -> 26
    assert composite_score([_sig("x", 1.0, 0.245)])[0] == 24
    assert composite_score([_sig("x", 1.0, 0.255)])[0] == 26


def test_band_boundaries_via_composite():
    assert band_for(0) == "Low"
    assert band_for(100) == "High"