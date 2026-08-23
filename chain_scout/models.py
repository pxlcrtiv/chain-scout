"""chain-scout — normalized data models.

Every data source (bundled fixture, public RPC, indexers) is normalized into
these dataclasses before any heuristic or scoring runs, so the scoring
engine is pure data-in/data-out and stays deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_ts(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp from fixture/indexer data."""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


@dataclass
class TokenHolding:
    address: str
    symbol: str
    name: str
    decimals: int
    balance_decimal: float
    price_usd: float | None = None
    holders_count: int | None = None
    total_supply: float | None = None
    top10_holder_share: float | None = None
    liquidity_usd: float | None = None
    avg_entry_price: float | None = None
    entry_is_demo: bool = False
    last_transfer_ts: str | None = None
    is_demo: bool = False

    @property
    def value_usd(self) -> float | None:
        if self.price_usd is None:
            return None
        return self.balance_decimal * self.price_usd

    @property
    def mcap_usd(self) -> float | None:
        if self.price_usd is None or self.total_supply is None:
            return None
        return self.price_usd * self.total_supply

    def as_dict(self) -> dict:
        return {
            "address": self.address,
            "symbol": self.symbol,
            "name": self.name,
            "decimals": self.decimals,
            "balance_decimal": self.balance_decimal,
            "price_usd": self.price_usd,
            "value_usd": self.value_usd,
            "holders_count": self.holders_count,
            "total_supply": self.total_supply,
            "top10_holder_share": self.top10_holder_share,
            "liquidity_usd": self.liquidity_usd,
            "avg_entry_price": self.avg_entry_price,
            "entry_is_demo": self.entry_is_demo,
            "last_transfer_ts": self.last_transfer_ts,
            "is_demo": self.is_demo,
        }


@dataclass
class Approval:
    token_address: str
    token_symbol: str
    spender: str
    allowance: str  # raw decimal string as found on chain
    is_unlimited: bool = False
    spender_is_eoa: bool | None = None
    known_bad: bool = False
    timestamp: str | None = None
    is_demo: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "spender": self.spender,
            "allowance": self.allowance,
            "is_unlimited": self.is_unlimited,
            "spender_is_eoa": self.spender_is_eoa,
            "known_bad": self.known_bad,
            "timestamp": self.timestamp,
            "is_demo": self.is_demo,
            "note": self.note,
        }


@dataclass
class TransferEvent:
    token_address: str
    token_symbol: str
    timestamp: str | None
    direction: str  # "in" | "out"
    value_decimal: float
    sender: str = ""
    receiver: str = ""


@dataclass
class WalletSnapshot:
    address: str
    chain: str
    data_source: str
    ens_name: str | None = None
    eth_balance: float = 0.0
    eth_price: float | None = None
    tokens: list[TokenHolding] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    transfers: list[TransferEvent] = field(default_factory=list)
    trust_senders: set[str] = field(default_factory=set)
    snapshot_ts: str | None = None
    notes: list[str] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)

    @property
    def eth_value_usd(self) -> float | None:
        if self.eth_price is None:
            return None
        return self.eth_balance * self.eth_price

    def total_value_usd(self) -> float | None:
        known = [t.value_usd for t in self.tokens if t.value_usd is not None]
        if not known and self.eth_value_usd is None:
            return None
        return sum(known) + (self.eth_value_usd or 0.0)


@dataclass
class SignalResult:
    key: str
    label: str
    weight: float
    severity: float  # 0..1, 1 = maximum risk
    known: bool
    contribution: float  # weight * severity (used by the formula)
    detail: str = ""


@dataclass
class PnlEntry:
    symbol: str
    balance: float
    price_usd: float
    entry_price: float | None
    value_usd: float
    pnl_usd: float | None
    pnl_pct: float | None
    is_demo: bool = False


@dataclass
class PnlSummary:
    entries: list[PnlEntry] = field(default_factory=list)

    @property
    def value_usd(self) -> float:
        return sum(e.value_usd for e in self.entries)

    @property
    def pnl_usd(self) -> float | None:
        known = [e.pnl_usd for e in self.entries if e.pnl_usd is not None]
        if not known:
            return None
        return sum(known)

    @property
    def covered_value_usd(self) -> float:
        return sum(e.value_usd for e in self.entries if e.pnl_usd is not None)

    def as_dict(self) -> dict:
        return {
            "value_usd": round(self.value_usd, 2),
            "pnl_usd": round(self.pnl_usd, 2) if self.pnl_usd is not None else None,
            "covered_value_usd": round(self.covered_value_usd, 2),
            "entries": [e.__dict__ for e in self.entries],
        }


@dataclass
class RiskReport:
    address: str
    chain: str
    data_source: str
    ens_name: str | None
    score: int
    band: str
    signals: list[SignalResult] = field(default_factory=list)
    token_rug: dict[str, dict] = field(default_factory=dict)  # symbol -> {score, reasons, known}
    warnings: list[str] = field(default_factory=list)
    research_notes: list[str] = field(default_factory=list)
    pnl: PnlSummary | None = None
    total_value_usd: float | None = None

    def as_dict(self) -> dict:
        return {
            "address": self.address,
            "chain": self.chain,
            "data_source": self.data_source,
            "ens_name": self.ens_name,
            "score": self.score,
            "band": self.band,
            "signals": [s.__dict__ for s in self.signals],
            "token_rug": self.token_rug,
            "warnings": self.warnings,
            "research_notes": self.research_notes,
            "pnl": self.pnl.as_dict() if self.pnl else None,
            "total_value_usd": self.total_value_usd,
        }