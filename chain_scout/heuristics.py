"""chain-scout — deterministic risk heuristics.

All functions here are pure: same input -> same output, no network, no clock
beyond an explicitly-passed ``now`` (so tests are fully deterministic).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import config
from .models import Approval, TokenHolding, TransferEvent, parse_ts

# ---------------------------------------------------------------------------
# Rug-flags: per-token score = weighted mean of the *known* sub-signals.
# ---------------------------------------------------------------------------


def concentration_signal(
    top10_holder_share: float | None, holders_count: int | None
) -> tuple[float, bool, str]:
    """Holder-concentration risk in [0,1]. Uses exact top-10 share when the
    data source provides it; otherwise falls back to a holders-count proxy
    (documented trade-off of keyless data). Unknown -> (0, False, ...)."""
    if top10_holder_share is not None:
        for threshold, score, reason in config.CONCENTRATION_BANDS:
            if top10_holder_share >= threshold:
                return score, True, reason
        return 0.0, True, "top-10 holders own <40% of supply"
    if holders_count is None:
        return 0.0, False, "holder data unavailable"
    for threshold, score, reason in config.HOLDERS_PROXY_BANDS:
        if holders_count < threshold:
            return score, True, f"proxy: {reason}"
    return 0.0, True, "holder base looks healthy (proxy: holders count)"


def liquidity_signal(
    mcap_usd: float | None, liquidity_usd: float | None
) -> tuple[float, bool, str]:
    """Liquidity depth vs market cap. Low liquidity = a whale can't exit,
    which is a classic rug exit-liquidity signature."""
    if mcap_usd is None or liquidity_usd is None or liquidity_usd <= 0:
        return 0.0, False, "liquidity data unavailable"
    ratio = mcap_usd / liquidity_usd
    for threshold, score, reason in config.LIQUIDITY_BANDS:
        if ratio >= threshold:
            return score, True, reason
    return 0.0, True, "liquidity is reasonable"


def dead_signal(
    last_transfer_ts: str | None, now: datetime | None = None
) -> tuple[float, bool, str]:
    """'Dead token' signal: no transfer touching this token in DEAD_DAYS."""
    if not last_transfer_ts:
        return 0.0, False, "transfer activity unknown"
    ts = parse_ts(last_transfer_ts)
    if ts is None:
        return 0.0, False, "transfer timestamp unparsable"
    now = now or datetime.now(UTC)
    if now - ts > timedelta(days=config.DEAD_DAYS):
        return config.DEAD_SCORE, True, f"no transfers in the last {config.DEAD_DAYS} days"
    return 0.0, True, "token is actively traded"


def token_rug_score(
    holding: TokenHolding, now: datetime | None = None
) -> tuple[float, bool, list[tuple[str, float]]]:
    """Composite rug risk for one token in [0,1].

    Returns (score, known, reasons) where ``reasons`` is a list of
    (human-reason, sub-signal-severity). Unknown components drop out; the
    known weights renormalize (same rule as the wallet-level score).
    """
    subs: list[tuple[str, float]] = []
    reasons: list[tuple[str, float]] = []

    c_score, c_known, c_reason = concentration_signal(
        holding.top10_holder_share, holding.holders_count
    )
    if c_known:
        subs.append(("concentration", c_score))
        reasons.append((c_reason, c_score))

    liq_score, liq_known, liq_reason = liquidity_signal(
        holding.mcap_usd, holding.liquidity_usd
    )
    if liq_known:
        subs.append(("liquidity", liq_score))
        reasons.append((liq_reason, liq_score))

    dead_score, dead_known, dead_reason = dead_signal(holding.last_transfer_ts, now)
    if dead_known:
        subs.append(("dead", dead_score))
        reasons.append((dead_reason, dead_score))

    if not subs:
        return 0.0, False, []

    denom = sum(config.RUG_WEIGHTS[k] for k, _ in subs)
    score = sum(config.RUG_WEIGHTS[k] * v for k, v in subs) / denom
    return round(score, 4), True, reasons


def classify_approval(
    approval: Approval, known_bad: set[str] | None = None
) -> tuple[str, list[str]]:
    """Classify an approval as ``safe`` | ``watch`` | ``dangerous``.

    Rules (documented in README):
      * unlimited allowance                      -> dangerous
      * spender on the known-bad list            -> dangerous
      * unlimited + non-EOA unknown contract     -> dangerous
      * EOA spender (any allowance >= $value)    -> dangerous
      * well-known DEX router, exact allowance   -> safe
      * unknown contract, exact allowance        -> watch
      * expiry/zero allowances                   -> safe
    """
    reasons: list[str] = []
    spender_l = (approval.spender or "").lower()
    kb = known_bad or config.known_bad_spenders()
    unlimited = approval.is_unlimited
    eoa = approval.spender_is_eoa is True

    if unlimited:
        reasons.append("unlimited allowance (max uint256)")
    if spender_l in kb:
        reasons.append("spender is on the known-bad list")
    if eoa and not unlimited:
        reasons.append("spender is an EOA (not a contract)")

    router = config.KNOWN_ROUTERS.get(spender_l)

    # EOA + any allowance, or unlimited to anything unknown -> dangerous
    if eoa:
        if unlimited:
            reasons.append("unlimited allowance to an EOA — total loss of the token balance")
        else:
            reasons.append("allowance granted to an EOA")
        return "dangerous", reasons

    if spender_l in kb:
        if unlimited:
            reasons.append("unlimited allowance + known-bad spender — revoke immediately")
        else:
            reasons.append("known-bad spender — revoke immediately")
        return "dangerous", reasons

    if unlimited:
        if router is not None:
            reasons.append(f"unlimited allowance to {router} (routers can move funds atomically)")
            return "watch", reasons
        reasons.append("unlimited allowance to an unknown contract")
        return "dangerous", reasons

    if router is not None:
        return "safe", reasons or [f"exact allowance to {router}"]

    return "watch", reasons or ["allowance to an unknown contract (no unlimited flag)"]


# ---------------------------------------------------------------------------
# Dust & phishing (wallet-level)
# ---------------------------------------------------------------------------


def dust_tokens(tokens: list[TokenHolding]) -> list[TokenHolding]:
    """Tokens worth less than DUST_VALUE_USD, excluding the top holdings."""
    valued = [t for t in tokens if t.value_usd is not None]
    valued.sort(key=lambda t: t.value_usd or 0.0, reverse=True)
    excluded = {id(t) for t in valued[: config.TOP_K_EXCLUDED_FROM_DUST]}
    return [t for t in valued if id(t) not in excluded and (t.value_usd or 0.0) < config.DUST_VALUE_USD]


def dust_severity(tokens: list[TokenHolding]) -> float:
    """How dusty is this wallet? Saturates at DUST_MAX dusty tokens."""
    return min(1.0, len(dust_tokens(tokens)) / config.DUST_MAX)


def inbound_phishing_share(
    transfers: list[TransferEvent],
    trust_senders: set[str] | None = None,
    now: datetime | None = None,
) -> tuple[float, bool, str]:
    """Share of inbound transfers (PHISHING_WINDOW_DAYS) sent by addresses
    outside the trusted set. Airdrop-stuffed wallets score high — such
    transfers are the classic seed for approval-phishing."""
    trust = trust_senders or set()
    window = now or datetime.now(UTC)
    inbounds = []
    for t in transfers:
        if t.direction != "in":
            continue
        ts = parse_ts(t.timestamp)
        if ts is None or window - ts <= timedelta(days=config.PHISHING_WINDOW_DAYS):
            inbounds.append(t)
    if not inbounds:
        return 0.0, False, "no inbound transfers in the window"
    unknown = sum(1 for t in inbounds if t.sender.lower() not in trust)
    return round(unknown / len(inbounds), 4), True, f"{unknown}/{len(inbounds)} inbound transfers in {config.PHISHING_WINDOW_DAYS}d from unknown senders"


# ---------------------------------------------------------------------------
# Approval exposure (value-weighted)
# ---------------------------------------------------------------------------


def approval_exposure(
    approvals: list[Approval], tokens: list[TokenHolding]
) -> tuple[float, bool, list[str]]:
    """Value-weighted share of the portfolio sitting under dangerous or
    watch-level approvals. Returns (severity, known, warnings)."""
    if not approvals:
        return 0.0, False, ["no approval data"]

    values = {t.address.lower(): t.value_usd for t in tokens if t.value_usd is not None}
    total_value = sum(values.values())
    if total_value <= 0:
        return 0.0, False, ["no priced tokens to weight approvals against"]

    unlimited_value = 0.0
    flagged_value = 0.0
    warnings: list[str] = []
    for appr in approvals:
        severity, reasons = classify_approval(appr)
        exposed = values.get(appr.token_address.lower())
        if severity == "dangerous":
            flagged_value += exposed or 0.0
            warnings.append(
                f"{appr.token_symbol} -> {appr.spender[:10]}…: " + "; ".join(reasons)
            )
        elif severity == "watch":
            unlimited_value += exposed or 0.0
            warnings.append(
                f"{appr.token_symbol} -> {appr.spender[:10]}…: " + "; ".join(reasons)
            )

    severity = min(1.0, (unlimited_value + flagged_value) / total_value)
    return round(severity, 4), True, warnings