"""chain-scout — pricing (CoinGecko, keyless) and PnL estimation.

CoinGecko's public free tier is used without a key; failures degrade
gracefully (None prices), never crash the report. PnL is an *estimate*:
real cost bases are usually unknown, so entries only get a number when an
``avg_entry_price`` is available (fixtures mark demo entries explicitly).
"""

from __future__ import annotations

import time

import requests

from .models import PnlEntry, PnlSummary, WalletSnapshot

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """Tiny keyless client. One price batch per call, 30s cache."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self._cache: dict[str, float | None] = {}
        self._cache_ts = 0.0
        self._cache_ttl = 30.0

    def eth_price(self) -> float | None:
        cached = self._cached("eth")
        if cached is not None:
            return cached
        try:
            r = requests.get(
                f"{COINGECKO_BASE}/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            price = float(r.json()["ethereum"]["usd"])
        except Exception:
            return None
        self._remember("eth", price)
        return price

    def token_prices(self, addresses: list[str]) -> dict[str, float | None]:
        """Single batch call for ERC-20 prices by contract address (mainnet)."""
        out: dict[str, float | None] = {}
        need = [a for a in addresses if self._cached(a) is None]
        for a in addresses:
            out[a] = self._cached(a)
        if not need:
            return out
        try:
            r = requests.get(
                f"{COINGECKO_BASE}/simple/token_price/ethereum",
                params={
                    "contract_addresses": ",".join(need),
                    "vs_currencies": "usd",
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            for a in need:
                price = float(data.get(a.lower(), {}).get("usd")) if data.get(a.lower()) else None
                if price is None and a in data:
                    price = float(data[a]["usd"])
                out[a] = price
                self._remember(a, price)
        except Exception:
            for a in need:
                out[a] = None
        return out

    def _cached(self, key: str) -> float | None:
        if key not in self._cache:
            return None
        if time.monotonic() - self._cache_ts > self._cache_ttl:
            return None
        return self._cache[key]

    def _remember(self, key: str, price: float | None) -> None:
        self._cache[key] = price
        self._cache_ts = time.monotonic()


def estimate_pnl(snapshot: WalletSnapshot) -> PnlSummary:
    """Unrealized PnL per token where an entry price exists.

    ``pnl = (price - entry) * balance``. Tokens without a cost basis are
    listed with value only and ``pnl_usd = None`` (the report says why:
    cost basis is rarely public — this is an estimate, not tax advice).
    """
    entries: list[PnlEntry] = []
    for tok in snapshot.tokens:
        if tok.price_usd is None:
            continue
        pnl_usd = None
        pnl_pct = None
        if tok.avg_entry_price is not None and tok.avg_entry_price > 0:
            pnl_usd = (tok.price_usd - tok.avg_entry_price) * tok.balance_decimal
            pnl_pct = (tok.price_usd / tok.avg_entry_price - 1.0) * 100.0
        entries.append(
            PnlEntry(
                symbol=tok.symbol,
                balance=tok.balance_decimal,
                price_usd=tok.price_usd,
                entry_price=tok.avg_entry_price,
                value_usd=tok.value_usd or 0.0,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                is_demo=tok.entry_is_demo,
            )
        )
    return PnlSummary(entries=entries)