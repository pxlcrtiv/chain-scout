#!/usr/bin/env python3
"""Regenerate fixtures/demo_wallet.json — reproducible provenance.

The bundled demo wallet is a hybrid, by design:

* REAL data, fetched now from keyless public sources:
    - token holdings + USD prices + holder counts   <- Blockscout v2 (mainnet)
    - ETH balance                                   <- public RPC (publicnode)
    - ETH / token prices                            <- CoinGecko free tier
    - transfer history (direction, timestamps)      <- Blockscout v2
* SIMULATED data, clearly marked ``is_demo``/``entry_is_demo`` and labeled
  in the app: two demo tokens + a demo approval set that exercises every
  heuristic branch (holder concentration, liquidity, dead-token, unlimited
  allowances, EOA spenders, known-bad spenders, routers).

Why: a real address's snapshot rarely contains an unlimited allowance to a
flagged EOA — the demo needs every branch reachable with zero keys, and
honesty requires labeling every synthetic byte.

Usage:  python scripts/fetch_fixtures.py [address] [--out fixtures/demo_wallet.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import requests

ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"  # vitalik.eth (well-known)
BLOCKSCOUT = "https://eth.blockscout.com/api/v2"
RPC = "https://ethereum-rpc.publicnode.com"
COINGECKO = "https://api.coingecko.com/api/v3"
ZERO = "0x0000000000000000000000000000000000000000"

TRUSTED_SENDERS = [
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance 14 (hot wallet)
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d",  # Binance 15 (hot wallet)
    "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",  # Coinbase 1 (hot wallet)
    "0x503828976D22510aad0201ac7EC88293211D23Da",  # Coinbase 2 (hot wallet)
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2",  # Kraken 2 (hot wallet)
]

# --- simulated demo tokens (marked is_demo) ---------------------------------
DEMO_TOKENS = [
    {
        "address": "0x1DEA0000000000000000000000000000000000AA",
        "symbol": "RUGX",
        "name": "RugX Demo Token (simulated)",
        "decimals": 18,
        "balance_decimal": 3_500_000.0,
        "price_usd": 0.00005,
        "holders_count": 312,
        "total_supply": 1_000_000_000.0,
        "top10_holder_share": 0.93,
        "liquidity_usd": 4_200.0,
        "avg_entry_price": 0.00009,
        "entry_is_demo": True,
        "last_transfer_ts": None,  # filled below as "dead" (60d ago)
        "is_demo": True,
    },
    {
        "address": "0x2B0000000000000000000000000000000000B00B",
        "symbol": "MOONP",
        "name": "MoonP Demo Token (simulated)",
        "decimals": 18,
        "balance_decimal": 1_200_000.0,
        "price_usd": 0.0045,
        "holders_count": 4_102,
        "total_supply": 100_000_000.0,
        "top10_holder_share": 0.71,
        "liquidity_usd": 80_000.0,
        "avg_entry_price": 0.002,
        "entry_is_demo": True,
        "last_transfer_ts": None,  # filled below as "alive" (2d ago)
        "is_demo": True,
    },
]

DEMO_APPROVALS = [
    {
        "token_address": "0x9cdF242Ef7975D8c68D5C1F5B6905801699b1940",  # WHITE (real)
        "token_symbol": "WHITE",
        "spender": "0x1DEA0000000000000000000000000000000000E0",  # demo EOA
        "allowance": str(2**256 - 1),
        "is_unlimited": True,
        "spender_is_eoa": True,
        "known_bad": False,
        "is_demo": True,
        "note": "demo: unlimited allowance to an EOA on the wallet's largest holding",
    },
    {
        "token_address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH (real)
        "token_symbol": "WETH",
        "spender": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Uniswap V3 Router02
        "allowance": "1500000000000000000000",
        "is_unlimited": False,
        "spender_is_eoa": False,
        "known_bad": False,
        "is_demo": True,
        "note": "demo: exact allowance to a known router (low risk)",
    },
    {
        "token_address": "0x9cdF242Ef7975D8c68D5C1F5B6905801699b1940",  # WHITE (real)
        "token_symbol": "WHITE",
        "spender": "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3 SwapRouter
        "allowance": str(2**256 - 1),
        "is_unlimited": True,
        "spender_is_eoa": False,
        "known_bad": False,
        "is_demo": True,
        "note": "demo: unlimited allowance to a router (watch, not catastrophic)",
    },
    {
        "token_address": "0x77777FeDdddFfC19Ff86DB637967013e6C6A116C",  # TORN (real)
        "token_symbol": "TORN",
        "spender": "0x2BAD00000000000000000000000000000000BEEF",  # demo unknown contract
        "allowance": str(2**256 - 1),
        "is_unlimited": True,
        "spender_is_eoa": False,
        "known_bad": False,
        "is_demo": True,
        "note": "demo: unlimited allowance to an unknown contract",
    },
    {
        "token_address": "0x1DEA0000000000000000000000000000000000AA",  # RUGX (demo)
        "token_symbol": "RUGX",
        "spender": "0xBAD0000000000000000000000000000000000BAD",  # demo known-bad
        "allowance": str(2**256 - 1),
        "is_unlimited": True,
        "spender_is_eoa": False,
        "known_bad": True,
        "is_demo": True,
        "note": "demo: unlimited allowance to a known-bad spender",
    },
    {
        "token_address": "0x2B0000000000000000000000000000000000B00B",  # MOONP (demo)
        "token_symbol": "MOONP",
        "spender": "0x1DEA0000000000000000000000000000000000E1",  # demo EOA
        "allowance": "1000000000000000000000000",
        "is_unlimited": False,
        "spender_is_eoa": True,
        "known_bad": False,
        "is_demo": True,
        "note": "demo: exact allowance to an EOA (dangerous)",
    },
]


def get_json(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def eth_balance(address: str) -> float:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBalance",
        "params": [address, "latest"],
    }
    r = requests.post(RPC, json=payload, timeout=30)
    r.raise_for_status()
    return int(r.json()["result"], 16) / 1e18


def eth_usd_price() -> float | None:
    try:
        r = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"},
            timeout=15,
        )
        r.raise_for_status()
        return float(r.json()["ethereum"]["usd"])
    except Exception:
        return None


def fetch_real_tokens(address: str) -> list[dict]:
    data = get_json(f"{BLOCKSCOUT}/addresses/{address}/tokens", {"type": "ERC-20"})
    out: list[dict] = []
    for item in data.get("items", []):
        t = item["token"]
        decimals = int(t.get("decimals") or 18)
        try:
            balance = int(item.get("value") or 0) / 10**decimals
        except (TypeError, ValueError):
            balance = 0.0
        rate = t.get("exchange_rate")
        out.append(
            {
                "address": t["address_hash"],
                "symbol": t["symbol"],
                "name": t.get("name") or t["symbol"],
                "decimals": decimals,
                "balance_decimal": round(balance, 8),
                "price_usd": round(float(rate), 12) if rate else None,
                "holders_count": int(t["holders_count"]) if t.get("holders_count") else None,
                "total_supply": round(int(t["total_supply"]) / 10**decimals, 4)
                if t.get("total_supply") else None,
                "top10_holder_share": None,  # needs an indexer key (Etherscan)
                "liquidity_usd": None,        # needs DEX data
                "avg_entry_price": None,      # cost basis is not public
                "entry_is_demo": False,
                "last_transfer_ts": None,     # filled from transfer feed below
                "is_demo": False,
            }
        )
    return out


def fetch_real_transfers(address: str) -> list[dict]:
    data = get_json(f"{BLOCKSCOUT}/addresses/{address}/token-transfers")
    out: list[dict] = []
    for item in data.get("items", []):
        total = item.get("total") or {}
        value_raw = total.get("value") or "0"
        decimals = int(total.get("decimals") or 18)
        try:
            value_dec = int(value_raw) / 10**decimals
        except (TypeError, ValueError):
            value_dec = 0.0
        tok = item.get("token") or {}
        sender = (item.get("from") or {}).get("hash") or ""
        receiver = (item.get("to") or {}).get("hash") or ""
        out.append(
            {
                "token_address": tok.get("address_hash") or "",
                "token_symbol": tok.get("symbol") or "?",
                "timestamp": item.get("timestamp"),
                "direction": "in" if receiver.lower() == address.lower() else "out",
                "value_decimal": round(value_dec, 8),
                "sender": sender,
                "receiver": receiver,
            }
        )
    return out


def apply_transfer_timestamps(tokens: list[dict], transfers: list[dict]) -> None:
    """lazy fill: last_transfer_ts for real tokens from the transfer feed."""
    by_symbol: dict[str, str] = {}
    for t in transfers:
        if t["timestamp"] and t["token_symbol"] not in by_symbol:
            by_symbol[t["token_symbol"]] = t["timestamp"]
    for tok in tokens:
        tok["last_transfer_ts"] = by_symbol.get(tok["symbol"])


def fill_demo_dates(now: dt.datetime) -> None:
    for tok in DEMO_TOKENS:
        ago = 60 if tok["symbol"] == "RUGX" else 2
        tok["last_transfer_ts"] = (now - dt.timedelta(days=ago)).isoformat(timespec="seconds")


def _validate_addresses() -> None:
    """Guard against typos in demo addresses (40 hex chars after 0x)."""
    import re

    ok = re.compile(r"^0x[0-9a-fA-F]{40}$")
    bad = []
    for tok in DEMO_TOKENS:
        if not ok.match(tok["address"]):
            bad.append(tok["address"])
    for appr in DEMO_APPROVALS:
        for field in ("token_address", "spender"):
            if not ok.match(appr[field]):
                bad.append(appr[field])
    if bad:
        raise SystemExit(f"invalid demo address(es): {bad}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", nargs="?", default=ADDRESS)
    parser.add_argument("--out", default="fixtures/demo_wallet.json")
    args = parser.parse_args()

    _validate_addresses()
    now = dt.datetime.now(dt.UTC)
    print(f"fetching snapshot for {args.address} ...", flush=True)

    try:
        tokens = fetch_real_tokens(args.address)
        transfers = fetch_real_transfers(args.address)
        balance = eth_balance(args.address)
    except Exception as exc:  # network/API hiccup -> hard fail, never half-write
        print(f"ERROR: could not fetch live data: {exc}", file=sys.stderr)
        return 1

    apply_transfer_timestamps(tokens, transfers)
    fill_demo_dates(now)
    eth_price = eth_usd_price()

    # Two demo tokens merged in, tagged is_demo. Keep the top real holdings
    # (slice) — and force-include any real token a demo approval references,
    # so fixture integrity never depends on indexer ranking shifts.
    tokens.sort(key=lambda t: (t.get("price_usd") or 0) * t["balance_decimal"], reverse=True)
    referenced = {a["token_address"].lower() for a in DEMO_APPROVALS}
    ordered: list[dict] = []
    seen: set[str] = set()
    for t in (*tokens, *[t for t in tokens if t["address"].lower() in referenced]):
        if t["address"].lower() not in seen:
            seen.add(t["address"].lower())
            ordered.append(t)
    fixture_tokens = ordered[:25] + DEMO_TOKENS

    meta_notes = [
        ("Real snapshot (mainnet, Blockscout v2 + public RPC + CoinGecko free tier) of "
         f"{args.address}; fetched {now.isoformat(timespec='seconds')}."),
        ("Approvals, entry prices and the RUGX/MOONP tokens are SIMULATED demo entries "
         "(flagged is_demo / entry_is_demo in the JSON and in the UI) that exercise every "
         "heuristic branch — full-history approval scanning needs an ETHERSCAN_API_KEY."),
        ("Holder-concentration uses the holders-count proxy where top-10 shares are "
         "unavailable keylessly (see README, rug heuristics)."),
        "This is a demo dataset, not financial advice.",
    ]
    fixture = {
        "meta": {
            "address": args.address,
            "ens": "vitalik.eth",
            "chain": "ethereum (mainnet snapshot)",
            "source": "blockscout v2 + public RPC + coingecko free tier",
            "snapshot_ts": now.isoformat(timespec="seconds"),
            "notes": meta_notes,
        },
        "eth": {
            "balance_decimal": round(balance, 8),
            "price_usd": eth_price,
        },
        "tokens": fixture_tokens,
        "approvals": DEMO_APPROVALS,
        "transfers": transfers[:40],
        "trust_senders": TRUSTED_SENDERS,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")

    known = sum((t.get("price_usd") or 0) * t["balance_decimal"] for t in fixture_tokens)
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(f"  real tokens: {len(fixture_tokens) - len(DEMO_TOKENS)}, demo tokens: {len(DEMO_TOKENS)}")
    print(f"  transfers: {len(fixture['transfers'])}, approvals: {len(fixture['approvals'])}")
    print(f"  ETH: {balance:.4f} @ {eth_price}, token value: ~${known:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())