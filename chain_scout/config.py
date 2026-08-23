"""chain-scout — central configuration: weights, thresholds, RPC endpoints.

Everything here is plain data on purpose: the scoring formula is fully
transparent (see scoring.py) and every constant below shows up either in the
Streamlit UI's "How the score works" panel or in the README.
"""

from __future__ import annotations

import os
from pathlib import Path

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Addresses / chains
# ---------------------------------------------------------------------------
CHAIN_ID_MAINNET = 1
CHAIN_ID_SEPOLIA = 11155111

RPC_DEFAULT_SEPOLIA = "https://ethereum-sepolia-rpc.publicnode.com"
RPC_MAINNET = "https://ethereum-rpc.publicnode.com"

# Mainnet is default-OFF: live scanning works on Sepolia/testnets out of the
# box. Using a mainnet RPC additionally requires MAINNET_ALLOWED=1 so an
# accidental paste can never scan real funds before the user opts in.
def mainnet_allowed() -> bool:
    return os.environ.get("MAINNET_ALLOWED", "").strip().lower() in ("1", "true", "yes")

def rpc_url_for(chain_id: int) -> str | None:
    env = os.environ.get("CHAIN_SCOUT_RPC_URL", "").strip()
    if env:
        return env
    if chain_id == CHAIN_ID_SEPOLIA:
        return RPC_DEFAULT_SEPOLIA
    if chain_id == CHAIN_ID_MAINNET:
        return None if not mainnet_allowed() else RPC_MAINNET
    return None

# Curated allowlist of well-known DEX routers — an allowance to one of these
# is still worth watching (it is a contract, not an EOA) but is NOT flagged
# as dangerous on its own.
KNOWN_ROUTERS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 SwapRouter",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 SwapRouter02",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch Router v5",
}

# Extend the known-bad count via env: CHAIN_SCOUT_KNOWN_BAD=0x…,0x…
def known_bad_spenders() -> set[str]:
    raw = os.environ.get("CHAIN_SCOUT_KNOWN_BAD", "").strip()
    return {a.strip().lower() for a in raw.split(",") if a.strip()}

# Well-known exchange hot wallets treated as trusted inbound senders.
TRUSTED_SENDERS = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 1",
    "0x83a4f7e1e8d1f1f7d3b9e2e73f8f6d15de6d1a9c7": "Kraken 3",
    "0x73957709695e1fd6f31b52e3d8a4b9d3f1d8a4b9d": "OKX 1",
}

# ---------------------------------------------------------------------------
# Scoring formula — composite weighted risk score, fully transparent.
#
#   risk = round( 100 * SUM(w_i * s_i for KNOWN signals)
#                       / SUM(w_i for KNOWN signals) )
#
# Every signal s_i is in [0, 1] (1 = maximum risk). Signals whose data is
# unknown are excluded and the remaining weights renormalize — an unknown
# signal neither adds nor removes risk. See scoring.py.
# ---------------------------------------------------------------------------
SIGNAL_WEIGHTS = {
    "approvals": 0.35,   # unlimited + flagged-spender exposure
    "rug": 0.35,         # value-weighted token rug score
    "dust": 0.15,        # dust-token exposure (phishing bait)
    "inbound": 0.15,     # unknown-sender inbound transfers (30d)
}

RISK_BANDS = [
    (70, "High"),
    (40, "Elevated"),
    (20, "Moderate"),
    (0, "Low"),
]

MAX_UINT = 2**256 - 1  # ERC20 "infinite" allowance

# Rug sub-signals (per token, weighted mean of known components)
RUG_WEIGHTS = {"concentration": 0.45, "liquidity": 0.35, "dead": 0.20}

CONCENTRATION_BANDS = [
    (0.90, 1.00, "top-10 holders own >=90% of supply"),
    (0.60, 0.65, "top-10 holders own >=60% of supply"),
    (0.40, 0.30, "top-10 holders own >=40% of supply"),
    (0.00, 0.00, "holder base looks distributed"),
]
# Fallback proxy when top-10 share is unknown (e.g. keyless data).
HOLDERS_PROXY_BANDS = [
    (500, 0.70, "fewer than 500 holders"),
    (2500, 0.40, "fewer than 2,500 holders"),
    (0, 0.00, "holder base looks healthy"),
]
LIQUIDITY_BANDS = [
    (20.0, 1.00, "market cap >20x liquidity"),
    (10.0, 0.60, "market cap >10x liquidity"),
    (5.0, 0.25, "market cap >5x liquidity"),
    (0.0, 0.00, "liquidity is reasonable"),
]
DEAD_DAYS = 30  # no transfer in N days -> "dead token" signal
DEAD_SCORE = 0.50

DUST_VALUE_USD = 50.0   # a holding worth less than this is "dust"
DUST_MAX = 15           # dust signal saturates at 15 dusty tokens
PHISHING_WINDOW_DAYS = 30
TOP_K_EXCLUDED_FROM_DUST = 3  # the biggest holdings are never "dust"

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DEMO_WALLET_FIXTURE = FIXTURES_DIR / "demo_wallet.json"

DEMO_WALLET_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

# ERC-20 tokens commonly minted on Sepolia (faucets) used by the live
# (RPC-only) provider so a testnet scan still finds something.
SEPOLIA_TOKEN_LIST = [
    {
        "address": "0x1c7d4b196cb0c7b01d743fbc6116a902379c7238",
        "symbol": "USDC",
        "name": "USD Coin (Sepolia)",
        "decimals": 6,
    },
    {
        "address": "0xff34b3d4aee8ddcd6f9a9f7d4a2c94994a6a3fc7",
        "symbol": "DAI",
        "name": "Dai Stablecoin (Sepolia)",
        "decimals": 18,
    },
]

# ---------------------------------------------------------------------------
# LLM report (OpenAI-compatible, keyless fallback). No key -> rule reporter.
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
LLM_TIMEOUT_S = 12

# Etherscan key is optional: full-history approvals / holder analytics light
# up when it is present. Documented in README; never required to run.
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "").strip()