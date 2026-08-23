"""Shared builders for tests — crafted wallets with known risk profiles."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone

from chain_scout.models import Approval, TokenHolding, TransferEvent, WalletSnapshot

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def fake_address(seed: str) -> str:
    """Deterministic, valid-looking 0x + 40 hex chars for a seed string."""
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()[:40]


def token(
    symbol: str = "SAFE",
    balance: float = 1_000.0,
    price: float | None = 100.0,
    holders: int | None = 500_000,
    top10: float | None = 0.05,
    liquidity: float | None = 500_000_000.0,
    supply: float | None = 10_000_000.0,
    last_ts: str | None | object = "__UNSET__",
    entry: float | None = None,
    entry_demo: bool = False,
    demo: bool = False,
    address: str | None = None,
) -> TokenHolding:
    if last_ts is None:
        last_ts_value: str | None = None  # explicitly unknown
    elif last_ts == "__UNSET__":
        last_ts_value = (NOW - timedelta(hours=1)).isoformat()  # fresh by default
    else:
        last_ts_value = str(last_ts)
    return TokenHolding(
        address=address or fake_address(f"token:{symbol}"),
        symbol=symbol,
        name=f"{symbol} Token",
        decimals=18,
        balance_decimal=balance,
        price_usd=price,
        holders_count=holders,
        total_supply=supply,
        top10_holder_share=top10,
        liquidity_usd=liquidity,
        avg_entry_price=entry,
        entry_is_demo=entry_demo,
        last_transfer_ts=last_ts_value,
        is_demo=demo,
    )


def approval(
    symbol: str,
    spender: str = "0x1DEA0000000000000000000000000000000000E0",
    unlimited: bool = True,
    eoa: bool = True,
    known_bad: bool = False,
    address: str | None = None,
    demo: bool = True,
) -> Approval:
    return Approval(
        token_address=address or fake_address(f"token:{symbol}"),
        token_symbol=symbol,
        spender=spender,
        allowance=str(2**256 - 1) if unlimited else "1500000000000000000000",
        is_unlimited=unlimited,
        spender_is_eoa=eoa,
        known_bad=known_bad,
        is_demo=demo,
    )


def transfer(symbol: str, direction: str, sender: str, ts: str | None = None) -> TransferEvent:
    return TransferEvent(
        token_address=fake_address(f"token:{symbol}"),
        token_symbol=symbol,
        timestamp=ts or (NOW - timedelta(days=2)).isoformat(),
        direction=direction,
        value_decimal=1.0,
        sender=sender,
        receiver="0x" + "11" * 20,
    )


def snapshot(
    tokens: list[TokenHolding] | None = None,
    approvals: list[Approval] | None = None,
    transfers: list[TransferEvent] | None = None,
    trust: set[str] | None = None,
) -> WalletSnapshot:
    return WalletSnapshot(
        address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        chain="test",
        data_source="fixture",
        eth_balance=0.0,
        eth_price=None,
        tokens=tokens or [],
        approvals=approvals or [],
        transfers=transfers or [],
        trust_senders=trust or set(),
    )


def clean_wallet() -> WalletSnapshot:
    """Everything calm: priced token, safe/absent approvals, no dust."""
    return snapshot(
        tokens=[token(), token("SAFE2", balance=500.0, price=50.0)],
        approvals=[],
        transfers=[],
    )


def rug_heavy_wallet() -> WalletSnapshot:
    """All value in one sketchy token; unlimited approval to an EOA."""
    sketchy = token(
        symbol="RUGX",
        balance=1_000.0,
        price=10.0,
        holders=100,
        top10=0.95,
        liquidity=300.0,  # mcap $100M / liq $300 => ratio massive
        last_ts=(NOW - timedelta(days=60)).isoformat(),
    )
    return snapshot(
        tokens=[sketchy],
        approvals=[approval("RUGX", eoa=True, unlimited=True)],
        transfers=[],
    )


def approval_heavy_wallet() -> WalletSnapshot:
    """60% of value sits under dangerous approvals; tokens are safe."""
    big = token("BIGA", balance=1_500.0, price=100.0)   # $150k
    mid = token("BIGB", balance=1_000.0, price=100.0)   # $100k
    return snapshot(
        tokens=[big, mid],
        approvals=[approval("BIGA", eoa=True, unlimited=True)],
        transfers=[],
    )


def dust_heavy_wallet() -> WalletSnapshot:
    """Three big tokens + ten $30 dust tokens."""
    tokens = [
        token("BIGA", balance=1_000.0, price=100.0),
        token("BIGB", balance=500.0, price=100.0),
        token("BIGC", balance=250.0, price=100.0),
    ]
    tokens += [token(f"DUST{i}", balance=1.0, price=30.0) for i in range(10)]
    return snapshot(tokens=tokens, approvals=[], transfers=[])


def inbound_heavy_wallet() -> WalletSnapshot:
    """Daily airdrops from unknown senders; otherwise calm."""
    transfers = [
        transfer("BIGA", "in", f"0x{str(i).zfill(40)}") for i in range(5)
    ]
    return snapshot(
        tokens=[token("BIGA", balance=1_000.0, price=100.0)],
        approvals=[],
        transfers=transfers,
    )