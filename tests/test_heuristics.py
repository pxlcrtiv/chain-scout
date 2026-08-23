"""Unit tests for the deterministic heuristic functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from chain_scout.heuristics import (
    classify_approval,
    concentration_signal,
    dead_signal,
    dust_severity,
    dust_tokens,
    inbound_phishing_share,
    liquidity_signal,
    token_rug_score,
)
from chain_scout.models import Approval

from .helpers import NOW, snapshot, token, transfer

# ---------------------------------------------------------------------------
# concentration
# ---------------------------------------------------------------------------


def test_concentration_exact_share_bands():
    assert concentration_signal(0.95, None) == (1.0, True, "top-10 holders own >=90% of supply")
    assert concentration_signal(0.70, None) == (0.65, True, "top-10 holders own >=60% of supply")
    assert concentration_signal(0.45, None) == (0.30, True, "top-10 holders own >=40% of supply")
    assert concentration_signal(0.10, None) == (0.0, True, "holder base looks distributed")


def test_concentration_holders_proxy():
    assert concentration_signal(None, 300) == (0.70, True, "proxy: fewer than 500 holders")
    assert concentration_signal(None, 1_000) == (0.40, True, "proxy: fewer than 2,500 holders")
    assert concentration_signal(None, 50_000) == (0.0, True, "holder base looks healthy (proxy: holders count)")


def test_concentration_unknown():
    assert concentration_signal(None, None) == (0.0, False, "holder data unavailable")


# ---------------------------------------------------------------------------
# liquidity
# ---------------------------------------------------------------------------


def test_liquidity_bands():
    assert liquidity_signal(100_000, 1_000) == (1.0, True, "market cap >20x liquidity")
    assert liquidity_signal(100_000, 8_000) == (0.60, True, "market cap >10x liquidity")
    assert liquidity_signal(100_000, 15_000) == (0.25, True, "market cap >5x liquidity")
    assert liquidity_signal(100_000, 90_000) == (0.0, True, "liquidity is reasonable")


def test_liquidity_unknown_when_data_missing():
    assert liquidity_signal(None, 100) == (0.0, False, "liquidity data unavailable")
    assert liquidity_signal(100, None) == (0.0, False, "liquidity data unavailable")


# ---------------------------------------------------------------------------
# dead token
# ---------------------------------------------------------------------------


def test_dead_signal_window():
    old = (NOW - timedelta(days=60)).isoformat()
    fresh = (NOW - timedelta(days=2)).isoformat()
    assert dead_signal(old, now=NOW) == (0.50, True, "no transfers in the last 30 days")
    assert dead_signal(fresh, now=NOW) == (0.0, True, "token is actively traded")


def test_dead_signal_unknown():
    assert dead_signal(None, now=NOW) == (0.0, False, "transfer activity unknown")


# ---------------------------------------------------------------------------
# token rug score
# ---------------------------------------------------------------------------


def test_rug_score_all_signals_known():
    t = token(
        top10=0.95, liquidity=1_000.0, supply=1_000_000.0,
        last_ts=(NOW - timedelta(days=60)).isoformat(),
    )
    score, known, reasons = token_rug_score(t, now=NOW)
    # concentration 1.0 (w.45) + liquidity 1.0 (w.35) + dead 0.5 (w.20) = 0.90
    assert known
    assert round(score, 4) == 0.90
    assert len(reasons) == 3


def test_rug_score_partial_signals_renormalize():
    t = token(top10=0.95, liquidity=None, last_ts=None)
    score, known, reasons = token_rug_score(t, now=NOW)
    assert known
    assert score == 1.0  # only concentration known -> it alone drives the score
    assert len(reasons) == 1


def test_rug_score_unknown_when_nothing_known():
    t = token(top10=None, holders=None, liquidity=None, last_ts=None)
    score, known, reasons = token_rug_score(t, now=NOW)
    assert not known
    assert score == 0.0
    assert reasons == []


# ---------------------------------------------------------------------------
# approvals
# ---------------------------------------------------------------------------


def test_approval_unlimited_eoa_dangerous():
    sev, reasons = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T", spender="0x" + "1" * 40,
                 allowance=str(2**256 - 1), is_unlimited=True, spender_is_eoa=True)
    )
    assert sev == "dangerous"
    assert any("unlimited allowance to an EOA" in r for r in reasons)


def test_approval_known_bad_dangerous():
    verdict, _ = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T",
                 spender="0xBAD0000000000000000000000000000000000BAD",
                 allowance="1000", is_unlimited=False, known_bad=True),
        known_bad={"0xbad0000000000000000000000000000000000bad"},
    )
    assert verdict == "dangerous"


def test_approval_unlimited_router_watch():
    sev, reasons = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T",
                 spender="0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Uniswap V3 Router02
                 allowance=str(2**256 - 1), is_unlimited=True, spender_is_eoa=False)
    )
    assert sev == "watch"
    assert any("Uniswap V3 SwapRouter02" in r for r in reasons)


def test_approval_exact_router_safe():
    sev, _ = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T",
                 spender="0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
                 allowance="5000000000000000000", is_unlimited=False, spender_is_eoa=False)
    )
    assert sev == "safe"


def test_approval_unknown_contract_watch():
    sev, _ = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T",
                 spender="0x" + "9" * 40, allowance="1000", is_unlimited=False, spender_is_eoa=False)
    )
    assert sev == "watch"


def test_approval_unlimited_unknown_contract_dangerous():
    sev, _ = classify_approval(
        Approval(token_address="0x" + "a" * 40, token_symbol="T",
                 spender="0x" + "9" * 40, allowance=str(2**256 - 1),
                 is_unlimited=True, spender_is_eoa=False)
    )
    assert sev == "dangerous"


# ---------------------------------------------------------------------------
# dust
# ---------------------------------------------------------------------------


def test_dust_tokens_excludes_top_holdings():
    tokens = [
        token("BIGA", balance=1_000, price=100),   # $100k
        token("BIGB", balance=500, price=100),     # $50k
        token("BIGC", balance=250, price=100),     # $25k
        token("DUST1", balance=1, price=30),       # $30
        token("DUST2", balance=1, price=30),
    ]
    dusty = dust_tokens(tokens)
    assert [t.symbol for t in dusty] == ["DUST1", "DUST2"]


def test_dust_severity_saturates():
    # 3 dust + 1 big: the top-3 by value are excluded (big + 2 dust)
    # -> 1 dusty token remains -> 1/15
    tokens = [token(f"DUST{i}", balance=1, price=30) for i in range(3)] + [
        token("BIGA", balance=1_000, price=100)
    ]
    assert dust_severity(tokens) == 1 / 15
    # 20 dust + 1 big: 18 dusty hits the 15 cap -> 1.0
    many = [token(f"D{i}", balance=1, price=30) for i in range(20)] + [
        token("BIGA", balance=1_000, price=100)
    ]
    assert dust_severity(many) == 1.0


# ---------------------------------------------------------------------------
# inbound phishing
# ---------------------------------------------------------------------------


def test_inbound_share_trusted_vs_unknown():
    trust = {"0x28c6c06298d514db089934071355e5743bf21d60"}
    txs = [
        transfer("T", "in", "0x28c6c06298d514db089934071355e5743bf21d60", ts=(NOW - timedelta(days=1)).isoformat()),
        transfer("T", "in", "0x" + "22" * 20, ts=(NOW - timedelta(days=1)).isoformat()),
        transfer("T", "in", "0x" + "33" * 20, ts=(NOW - timedelta(days=1)).isoformat()),
        transfer("T", "out", "0x" + "44" * 20, ts=(NOW - timedelta(days=1)).isoformat()),
    ]
    sev, known, detail = inbound_phishing_share(txs, trust_senders=trust, now=NOW)
    assert known
    assert sev == round(2 / 3, 4)
    assert "unknown senders" in detail


def test_inbound_share_empty_window_unknown():
    sev, known, _ = inbound_phishing_share([], trust_senders=set(), now=NOW)
    assert sev == 0.0
    assert not known


def test_inbound_share_ignores_old_transfers():
    old = transfer("T", "in", "0x" + "99" * 20, ts=(NOW - timedelta(days=90)).isoformat())
    _sev, known, _ = inbound_phishing_share([old], trust_senders=set(), now=NOW)
    assert not known  # nothing inside the 30d window