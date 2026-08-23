"""Golden tests — exact scores for crafted wallets with known profiles.

These pin the transparent formula to specific integers: any change to the
weights, thresholds, or rounding that moves a score gets caught here.
"""

from __future__ import annotations

from chain_scout.scoring import build_report, composite_score, compute_signals

from .helpers import (
    NOW,
    approval_heavy_wallet,
    clean_wallet,
    dust_heavy_wallet,
    inbound_heavy_wallet,
    rug_heavy_wallet,
)


def test_golden_clean_wallet_scores_zero_low():
    report = build_report(clean_wallet(), now=NOW)
    assert report.score == 0
    assert report.band == "Low"


def test_golden_rug_heavy_wallet():
    # approval exposure 1.0 (w=0.35), rug severity 0.90 (w=0.35),
    # dust 0 (w=0.15), inbound unknown (excluded).
    # denom = 0.85 -> raw = 100*(0.350 + 0.315)/0.85 = 78.24 -> 78
    report = build_report(rug_heavy_wallet(), now=NOW)
    assert report.score == 78
    assert report.band == "High"
    signals = {s.key: s for s in report.signals}
    assert signals["approvals"].severity == 1.0
    assert round(signals["rug"].severity, 2) == 0.90
    assert signals["inbound"].known is False


def test_golden_approval_heavy_wallet():
    # 60% of value under dangerous approvals -> raw 24.7 -> 25
    report = build_report(approval_heavy_wallet(), now=NOW)
    assert report.score == 25
    assert report.band == "Moderate"


def test_golden_dust_heavy_wallet():
    # 10 dust / 15 cap = 0.6667 (w=0.15); rug known 0 (w=0.35); denom 0.5
    # -> raw 20 -> 20
    report = build_report(dust_heavy_wallet(), now=NOW)
    assert report.score == 20
    assert report.band == "Moderate"


def test_golden_inbound_heavy_wallet():
    # inbound severity 1.0 (w=0.15), others known 0 (rug 0.35, dust 0.15)
    # denom 0.65 -> raw 23.08 -> 23
    report = build_report(inbound_heavy_wallet(), now=NOW)
    assert report.score == 23
    assert report.band == "Moderate"


def test_golden_score_matches_hand_computation():
    """The engine's number must equal the formula computed by hand."""
    wallet = rug_heavy_wallet()
    signals = compute_signals(wallet, now=NOW)
    known = [s for s in signals if s.known]
    denom = sum(s.weight for s in known)
    raw = 100.0 * sum(s.contribution for s in known) / denom
    assert round(raw) == composite_score(signals)[0]


def test_band_edges():
    assert composite_score([]) == (0, "Low")
    check = [
        (0, "Low"),
        (19, "Low"),
        (20, "Moderate"),
        (39, "Moderate"),
        (40, "Elevated"),
        (69, "Elevated"),
        (70, "High"),
        (100, "High"),
    ]
    for score, band in check:
        from chain_scout.scoring import band_for

        assert band_for(score) == band


def test_score_clamped_to_100():
    from chain_scout.models import SignalResult

    signals = [
        SignalResult(key="a", label="A", weight=1.0, severity=1.0, known=True, contribution=1.0),
        SignalResult(key="b", label="B", weight=1.0, severity=1.0, known=True, contribution=1.0),
    ]
    score, band = composite_score(signals)
    assert score == 100
    assert band == "High"