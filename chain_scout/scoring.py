"""chain-scout — composite weighted risk score.

Transparent formula (shown verbatim in the UI "How the score works" panel
and in the README):

    risk = round( 100 * SUM(w_i * s_i  over KNOWN signals)
                        / SUM(w_i      over KNOWN signals) )

* ``w_i``  — fixed weight per signal (see config.SIGNAL_WEIGHTS).
* ``s_i``  — observed severity in [0, 1]; 1 = maximum risk.
* Signals whose data is unavailable are **excluded** and the remaining
  weights renormalize: an unknown signal neither adds nor removes risk.

Bands: 0-19 Low, 20-39 Moderate, 40-69 Elevated, 70-100 High.

Everything here is deterministic and pure — the golden tests in
tests/test_scoring_golden.py pin exact scores for crafted wallets.
"""

from __future__ import annotations

from datetime import datetime

from . import config, heuristics
from .models import RiskReport, SignalResult, WalletSnapshot


def band_for(score: int) -> str:
    for threshold, label in config.RISK_BANDS:
        if score >= threshold:
            return label
    return "Low"


def compute_signals(snapshot: WalletSnapshot, now: datetime | None = None) -> list[SignalResult]:
    """Compute every wallet-level signal for the transparent formula."""
    signals: list[SignalResult] = []

    # --- approvals: share of value under dangerous/watch approvals ---------
    approval_sev, approval_known, approval_warnings = heuristics.approval_exposure(
        snapshot.approvals, snapshot.tokens
    )
    signals.append(
        SignalResult(
            key="approvals",
            label="Approval risk (unlimited / flagged spenders)",
            weight=config.SIGNAL_WEIGHTS["approvals"],
            severity=approval_sev,
            known=approval_known,
            contribution=config.SIGNAL_WEIGHTS["approvals"] * approval_sev,
            detail="; ".join(approval_warnings[:3]) or approval_known and "no dangerous approvals" or "no approval data",
        )
    )

    # --- rug: value-weighted mean of per-token rug scores ------------------
    rug_total = 0.0
    rug_weight = 0.0
    token_rug: dict[str, dict] = {}
    rug_warnings: list[str] = []
    for tok in snapshot.tokens:
        score, known, reasons = heuristics.token_rug_score(tok, now)
        token_rug[tok.symbol] = {
            "score": score,
            "known": known,
            "reasons": [r for r, _ in reasons],
        }
        if known and tok.value_usd is not None:
            rug_total += score * tok.value_usd
            rug_weight += tok.value_usd
            flagged = [(r, s) for r, s in reasons if s >= 0.4]
            if flagged:
                rug_warnings.append(
                    f"{tok.symbol} (${tok.value_usd:,.0f}): " + "; ".join(r for r, _ in flagged)
                )
    if rug_weight > 0:
        rug_sev = round(rug_total / rug_weight, 4)
        rug_known = True
        detail = f"value-weighted across {len([t for t in token_rug.values() if t['known']])} scored tokens"
    else:
        rug_sev, rug_known = 0.0, False
        detail = "no token rug scores computable from available data"
    signals.append(
        SignalResult(
            key="rug",
            label="Rug exposure (holder concentration, liquidity, dead tokens)",
            weight=config.SIGNAL_WEIGHTS["rug"],
            severity=rug_sev,
            known=rug_known,
            contribution=config.SIGNAL_WEIGHTS["rug"] * rug_sev,
            detail=detail,
        )
    )

    # --- dust: phishing-bait tokens under the dust line ---------------------
    dust_sev = heuristics.dust_severity(snapshot.tokens)
    dust_count = len(heuristics.dust_tokens(snapshot.tokens))
    signals.append(
        SignalResult(
            key="dust",
            label="Dust exposure (sub-$50 holdings = phishing bait)",
            weight=config.SIGNAL_WEIGHTS["dust"],
            severity=round(dust_sev, 4),
            known=True,
            contribution=config.SIGNAL_WEIGHTS["dust"] * dust_sev,
            detail=f"{dust_count} dust token(s) found" if dust_count else "no dust tokens",
        )
    )

    # --- inbound: unknown-sender transfers (30d) ----------------------------
    phish_sev, phish_known, phish_detail = heuristics.inbound_phishing_share(
        snapshot.transfers, snapshot.trust_senders, now
    )
    signals.append(
        SignalResult(
            key="inbound",
            label="Inbound exposure (airdrops / unknown senders, 30d)",
            weight=config.SIGNAL_WEIGHTS["inbound"],
            severity=phish_sev,
            known=phish_known,
            contribution=config.SIGNAL_WEIGHTS["inbound"] * phish_sev,
            detail=phish_detail,
        )
    )

    return signals


def composite_score(signals: list[SignalResult]) -> tuple[int, str]:
    """Apply the transparent formula. Returns (score, band)."""
    known = [s for s in signals if s.known]
    if not known:
        return 0, band_for(0)
    denom = sum(s.weight for s in known)
    if denom <= 0:
        return 0, band_for(0)
    raw = 100.0 * sum(s.contribution for s in known) / denom
    score = round(raw)
    return max(0, min(100, score)), band_for(score)


def build_report(snapshot: WalletSnapshot, now: datetime | None = None) -> RiskReport:
    """Full pipeline: signals -> score -> warnings -> PnL. Deterministic."""
    signals = compute_signals(snapshot, now)
    score, band = composite_score(signals)
    token_rug = compute_token_rug(snapshot, now)

    warnings: list[str] = []
    for s in signals:
        if s.key == "approvals" and s.known and s.severity > 0:
            warnings.append(f"Approval risk: {s.detail}")
        if s.key == "rug" and s.known and s.severity >= 0.4:
            warnings.append(f"Rug exposure: {s.detail}")

    # Rug-flagged tokens (per-token reasons)
    for tok in snapshot.tokens:
        info = token_rug.get(tok.symbol)
        if info and info["known"]:
            for reason, sev in info["reason_pairs"]:
                if sev >= 0.4:
                    warnings.append(f"{tok.symbol}: {reason}")

    research_notes = list(snapshot.notes)
    if snapshot.data_source == "fixture":
        research_notes.append(
            "Fixture wallet: bundled demo data (real mainnet snapshot + clearly-labeled "
            "simulated entries) — see README 'Data & privacy'."
        )
    if len(snapshot.provider_errors):
        research_notes.extend(f"provider note: {e}" for e in snapshot.provider_errors)

    from .pricing import estimate_pnl

    pnl = estimate_pnl(snapshot)

    return RiskReport(
        address=snapshot.address,
        chain=snapshot.chain,
        data_source=snapshot.data_source,
        ens_name=snapshot.ens_name,
        score=score,
        band=band,
        signals=signals,
        token_rug={k: {kk: vv for kk, vv in v.items() if kk != "reason_pairs"} for k, v in token_rug.items()},
        warnings=warnings,
        research_notes=research_notes,
        pnl=pnl,
        total_value_usd=snapshot.total_value_usd(),
    )


def compute_token_rug(snapshot: WalletSnapshot, now: datetime | None = None) -> dict:
    """Per-token rug breakdown (symbol -> {score, known, reasons, reason_pairs})."""
    out: dict[str, dict] = {}
    for tok in snapshot.tokens:
        score, known, reasons = heuristics.token_rug_score(tok, now)
        out[tok.symbol] = {
            "score": score,
            "known": known,
            "reasons": [r for r, _ in reasons],
            "reason_pairs": reasons,
        }
    return out