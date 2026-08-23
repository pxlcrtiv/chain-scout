"""chain-scout — AI wallet risk scanner.

Paste any Ethereum address -> plain-English risk report: rug-pulled tokens,
dangerous approvals, holder concentration, estimated PnL.

Keyless by default: bundled fixtures + public RPC + CoinGecko free tier.
"""

from .config import VERSION

__all__ = ["VERSION"]