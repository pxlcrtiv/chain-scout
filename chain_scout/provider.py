"""chain-scout — data providers.

Two providers, both keyless by default:

* ``FixtureProvider`` — loads the bundled demo wallet (``fixtures/demo_wallet.json``).
  This is the zero-key demo: real mainnet snapshot data plus clearly-labeled
  simulated entries that exercise every heuristic branch.
* ``LiveProvider`` — talks to a public RPC over web3.py. **Sepolia by
  default**; mainnet URLs are refused unless ``MAINNET_ALLOWED=1`` (the app
  is testnet-first by design — see README).

Full transaction/approval *history* needs an indexer (Etherscan et al.) and
therefore a key; without one the live provider reports balances and records
a provider note instead of fabricating data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from web3 import Web3

from . import config
from .models import Approval, TokenHolding, TransferEvent, WalletSnapshot, utc_now_iso

_HEX_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_address(value: str) -> bool:
    return bool(_HEX_ADDR.match(value or ""))


class FixtureProvider:
    """Bundled demo wallet. Zero network, zero keys, deterministic."""

    name = "fixture"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.DEMO_WALLET_FIXTURE

    def matches(self, address: str) -> bool:
        return address.strip().lower() == config.DEMO_WALLET_ADDRESS.lower()

    def fetch(self, address: str) -> WalletSnapshot:
        if not self.path.exists():
            raise FileNotFoundError(f"fixture missing: {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        if address.strip().lower() != meta.get("address", "").lower():
            raise ValueError(
                f"fixture wallet is {meta.get('address')}; requested {address}. "
                "Paste the demo address, or switch data source to Live."
            )
        tokens = [self._token_row(t) for t in data.get("tokens", [])]
        approvals = [self._approval_row(a) for a in data.get("approvals", [])]
        transfers = [self._transfer_row(t) for t in data.get("transfers", [])]
        eth = data.get("eth", {})
        return WalletSnapshot(
            address=meta["address"],
            chain=meta.get("chain", "ethereum (fixture snapshot)"),
            data_source="fixture",
            ens_name=meta.get("ens"),
            eth_balance=float(eth.get("balance_decimal", 0.0)),
            eth_price=eth.get("price_usd"),
            tokens=tokens,
            approvals=approvals,
            transfers=transfers,
            trust_senders=set(data.get("trust_senders", [])),
            snapshot_ts=meta.get("snapshot_ts"),
            notes=list(meta.get("notes", [])),
        )

    @staticmethod
    def _token_row(t: dict) -> TokenHolding:
        return TokenHolding(
            address=t["address"],
            symbol=t["symbol"],
            name=t.get("name", t["symbol"]),
            decimals=int(t.get("decimals", 18)),
            balance_decimal=float(t.get("balance_decimal", 0.0)),
            price_usd=float(t["price_usd"]) if t.get("price_usd") is not None else None,
            holders_count=int(t["holders_count"]) if t.get("holders_count") is not None else None,
            total_supply=float(t["total_supply"]) if t.get("total_supply") is not None else None,
            top10_holder_share=float(t["top10_holder_share"]) if t.get("top10_holder_share") is not None else None,
            liquidity_usd=float(t["liquidity_usd"]) if t.get("liquidity_usd") is not None else None,
            avg_entry_price=float(t["avg_entry_price"]) if t.get("avg_entry_price") is not None else None,
            entry_is_demo=bool(t.get("entry_is_demo", False)),
            last_transfer_ts=t.get("last_transfer_ts"),
            is_demo=bool(t.get("is_demo", False)),
        )

    @staticmethod
    def _approval_row(a: dict) -> Approval:
        return Approval(
            token_address=a["token_address"],
            token_symbol=a["token_symbol"],
            spender=a["spender"],
            allowance=a.get("allowance", "0"),
            is_unlimited=bool(a.get("is_unlimited", False)),
            spender_is_eoa=a.get("spender_is_eoa"),
            known_bad=bool(a.get("known_bad", False)),
            timestamp=a.get("timestamp"),
            is_demo=bool(a.get("is_demo", False)),
            note=a.get("note", ""),
        )

    @staticmethod
    def _transfer_row(t: dict) -> TransferEvent:
        return TransferEvent(
            token_address=t["token_address"],
            token_symbol=t["token_symbol"],
            timestamp=t.get("timestamp"),
            direction=t["direction"],
            value_decimal=float(t.get("value_decimal", 0.0)),
            sender=t.get("sender", ""),
            receiver=t.get("receiver", ""),
        )


class LiveProvider:
    """Public-RPC provider (Sepolia default; mainnet requires MAINNET_ALLOWED=1).

    Balances are real; transfer/approval *history* needs an indexer key, so
    without one the snapshot carries a provider note instead of fake data.
    """

    name = "live"

    def __init__(
        self,
        chain_id: int = config.CHAIN_ID_SEPOLIA,
        rpc_url: str | None = None,
        token_list: list[dict] | None = None,
    ) -> None:
        self.chain_id = chain_id
        self.rpc_url = rpc_url or config.rpc_url_for(chain_id)
        if not self.rpc_url:
            raise ValueError(
                "mainnet scanning is off by default. Export MAINNET_ALLOWED=1 "
                "to unlock the mainnet RPC (you acknowledge you are scanning "
                "real funds), or use the Sepolia default."
            )
        self.token_list = token_list if token_list is not None else config.SEPOLIA_TOKEN_LIST
        self.errors: list[str] = []

    def fetch(self, address: str) -> WalletSnapshot:
        w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            raise ConnectionError(f"RPC unreachable: {self.rpc_url}")

        try:
            checksummed = Web3.to_checksum_address(address)
        except Exception as exc:
            raise ValueError(f"invalid address: {address} — {exc}") from exc

        eth_balance = float(w3.eth.get_balance(checksummed)) / 1e18
        tokens: list[TokenHolding] = []
        for spec in self.token_list:
            try:
                data = w3.eth.call(
                    {
                        "to": spec["address"],
                        "data": "0x70a08231" + "0" * 24 + checksummed[2:].lower(),
                    }
                )
                raw = int(data, 16)
                if raw > 0:
                    tokens.append(
                        TokenHolding(
                            address=spec["address"],
                            symbol=spec["symbol"],
                            name=spec["name"],
                            decimals=spec["decimals"],
                            balance_decimal=raw / 10 ** spec["decimals"],
                            price_usd=None,  # testnets have no market price
                        )
                    )
            except Exception as exc:  # one token must not kill the scan
                self.errors.append(f"balanceOf({spec['symbol']}) failed: {exc}")
                continue

        errors = []
        if int(w3.eth.chain_id) != self.chain_id:
            errors.append(
                f"RPC chain id {w3.eth.chain_id} does not match requested chain "
                f"{self.chain_id} — results may be for the wrong network."
            )
        errors.append(
            "Transfer & approval history needs an indexer API key "
            "(ETHERSCAN_API_KEY -> ~/portfolio/.env); balances above are live."
        )

        return WalletSnapshot(
            address=checksummed,
            chain=f"chain id {self.chain_id} ({'sepolia' if self.chain_id == config.CHAIN_ID_SEPOLIA else 'mainnet'})",
            data_source="live",
            eth_balance=eth_balance,
            eth_price=None,
            tokens=tokens,
            approvals=[],
            transfers=[],
            snapshot_ts=utc_now_iso(),
            notes=[
                "Live RPC scan: balances are real, history is not indexed keylessly.",
            ],
            provider_errors=errors,
        )


def make_provider(data_source: str, address: str):
    """Resolve the right provider for a data-source choice.

    ``auto``: use the bundled fixture when the address is the demo wallet,
    otherwise fall back to live (Sepolia) scanning.
    """
    mode = (data_source or "auto").strip().lower()
    if mode == "fixture":
        return FixtureProvider()
    if mode == "live":
        return LiveProvider()
    if mode == "auto":
        fixture = FixtureProvider()
        return fixture if fixture.matches(address) else LiveProvider()
    raise ValueError(f"unknown data source: {data_source} (expected auto|fixture|live)")