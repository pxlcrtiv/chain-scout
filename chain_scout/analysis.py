"""chain-scout — high-level API used by the Streamlit app.

``analyze()`` is the one-liner the README promises:

    snapshot, report = analyze(address)          # fixture demo, zero keys
    snapshot, report = analyze(address, "live")  # Sepolia RPC scan
"""

from __future__ import annotations

from datetime import datetime

from . import provider as _provider
from .models import RiskReport, WalletSnapshot
from .scoring import build_report


def validate_address(address: str) -> str:
    addr = (address or "").strip()
    if not _provider.is_address(addr):
        raise ValueError(
            "That does not look like an Ethereum address (expects 0x + 40 hex chars)."
        )
    return addr


def analyze(
    address: str,
    data_source: str = "auto",
    now: datetime | None = None,
) -> tuple[WalletSnapshot, RiskReport]:
    """Fetch a wallet snapshot, score it, and build the risk report."""
    addr = validate_address(address)
    prov = _provider.make_provider(data_source, addr)
    snapshot = prov.fetch(addr)
    report = build_report(snapshot, now)
    return snapshot, report