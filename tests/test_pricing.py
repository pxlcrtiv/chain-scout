"""Pricing (CoinGecko client) and PnL estimation."""

from __future__ import annotations

from chain_scout.models import TokenHolding, WalletSnapshot
from chain_scout.pricing import CoinGeckoClient, estimate_pnl

from .helpers import token


def _wallet_with_entries() -> WalletSnapshot:
    winner = token("WIN", balance=1000.0, price=2.0, entry=1.0, entry_demo=True)   # +$1,000
    loser = token("LOSE", balance=500.0, price=0.5, entry=1.0, entry_demo=True)    # -$250
    no_basis = token("NOBS", balance=100.0, price=5.0, entry=None)
    no_price = token("NOPR", balance=50.0, price=None, entry=1.0)
    return WalletSnapshot(address="x", chain="test", data_source="fixture", tokens=[
        winner, loser, no_basis, no_price,
    ])


def test_pnl_math():
    summary = estimate_pnl(_wallet_with_entries())
    by = {e.symbol: e for e in summary.entries}
    assert by["WIN"].pnl_usd == 1000.0
    assert by["WIN"].pnl_pct == 100.0
    assert by["LOSE"].pnl_usd == -250.0
    assert by["LOSE"].pnl_pct == -50.0


def test_pnl_unknown_basis_reported_not_fabricated():
    summary = estimate_pnl(_wallet_with_entries())
    by = {e.symbol: e for e in summary.entries}
    assert by["NOBS"].pnl_usd is None
    # no price -> token not even listed (nothing to value)
    assert "NOPR" not in by


def test_pnl_totals_only_cover_known_basis():
    summary = estimate_pnl(_wallet_with_entries())
    assert summary.pnl_usd == 750.0
    assert summary.value_usd == 2000.0 + 250.0 + 500.0  # WIN + LOSE + NOBS
    assert summary.covered_value_usd == 2250.0


def test_coin_gecko_fallback_on_network_error(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("no network")

    monkeypatch.setattr("chain_scout.pricing.requests.get", boom)
    client = CoinGeckoClient()
    assert client.eth_price() is None
    assert client.token_prices(["0x" + "a" * 40]) == {"0x" + "a" * 40: None}


def test_coin_gecko_parses_response(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ethereum": {"usd": 2459.5}, "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"usd": 2460.0}}

    monkeypatch.setattr("chain_scout.pricing.requests.get", lambda *a, **k: FakeResp())
    client = CoinGeckoClient()
    assert client.eth_price() == 2459.5
    prices = client.token_prices(["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"])
    assert prices["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"] == 2460.0


def test_pnl_demo_flag_propagates():
    summary = estimate_pnl(_wallet_with_entries())
    by = {e.symbol: e for e in summary.entries}
    assert by["WIN"].is_demo
    assert not by["NOBS"].is_demo