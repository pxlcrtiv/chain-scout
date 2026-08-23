"""chain-scout — plain-English risk report writers.

``RuleReporter`` is fully deterministic and keyless: it renders the score,
formula breakdown, warnings, holdings, approvals and PnL as markdown.

``LLMReporter`` posts a compact JSON digest to any OpenAI-compatible
``/chat/completions`` endpoint (key via OPENAI_API_KEY, base/model via
OPENAI_BASE_URL / OPENAI_MODEL). **On any failure — missing key, timeout,
HTTP error, empty response — it silently falls back to the rule reporter**,
so the app always has a report.
"""

from __future__ import annotations

import json

import requests

from . import config
from .models import RiskReport, WalletSnapshot


class RuleReporter:
    """Deterministic markdown report. Same snapshot -> same bytes."""

    name = "rule"

    def render(self, report: RiskReport, snapshot: WalletSnapshot) -> str:
        lines: list[str] = []
        ens = f" ({report.ens_name})" if report.ens_name else ""
        lines.append(f"# Risk report — {report.address}{ens}")
        lines.append("")
        lines.append(f"- **Chain:** {report.chain}")
        lines.append(f"- **Data source:** {report.data_source}"
                     f"{' (bundled demo fixture)' if report.data_source == 'fixture' else ''}")
        lines.append(f"- **Score:** {report.score}/100 — **{report.band}**")
        if report.total_value_usd is not None:
            lines.append(f"- **Portfolio value (known):** ${report.total_value_usd:,.2f}")
        lines.append("")

        lines.append("## How the score was computed")
        lines.append("")
        lines.append("`risk = 100 x SUM(weight x severity for known signals) / SUM(weight for known signals)`")
        lines.append("")
        lines.append("| Signal | Weight | Severity | Contribution |")
        lines.append("|---|---|---|---|")
        for s in report.signals:
            sev = f"{s.severity:.3f}" if s.known else "n/a (unknown)"
            contrib = f"{s.contribution:.3f}" if s.known else "n/a"
            lines.append(f"| {s.label} | {s.weight:.2f} | {sev} | {contrib} |")
        lines.append("")

        if report.warnings:
            lines.append("## ⚠️ Key warnings")
            lines.append("")
            for w in report.warnings:
                lines.append(f"- {w}")
            lines.append("")

        if report.token_rug:
            flagged = {sym: info for sym, info in report.token_rug.items() if info["known"] and info["score"] >= 0.4}
            if flagged:
                lines.append("## 🚩 Token rug flags (score >= 0.40)")
                lines.append("")
                for sym in sorted(flagged, key=lambda s: -flagged[s]["score"]):
                    info = flagged[sym]
                    lines.append(f"- **{sym}** (rug score {info['score']:.2f}): "
                                 + "; ".join(info["reasons"]))
                lines.append("")

        if snapshot.approvals:
            lines.append("## 🔓 Approvals")
            lines.append("")
            from .heuristics import classify_approval

            lines.append("| Token | Spender | Allowance | Verdict | Why |")
            lines.append("|---|---|---|---|---|")
            for appr in sorted(snapshot.approvals, key=lambda a: (a.is_demo, a.token_symbol)):
                sev, reasons = classify_approval(appr)
                demo = " (demo)" if appr.is_demo else ""
                allowance = "unlimited" if appr.is_unlimited else f"{int(appr.allowance or 0):,}"
                lines.append(
                    f"| {appr.token_symbol}{demo} | {appr.spender[:12]}… | {allowance} "
                    f"| **{sev.upper()}** | {'; '.join(reasons)} |"
                )
            lines.append("")

        if report.pnl and report.pnl.entries:
            lines.append("## 📈 PnL estimate (unrealized, where cost basis is known)")
            lines.append("")
            lines.append("| Symbol | Balance | Price | Entry (est.) | Value | PnL | PnL % |")
            lines.append("|---|---|---|---|---|---|---|")
            for e in report.pnl.entries:
                demo = " (demo)" if e.is_demo else ""
                entry = f"${e.entry_price:,.6f}" if e.entry_price is not None else "n/a"
                pnl = f"${e.pnl_usd:,.2f}" if e.pnl_usd is not None else "n/a — cost basis unknown"
                pct = f"{e.pnl_pct:+.1f}%" if e.pnl_pct is not None else ""
                lines.append(
                    f"| {e.symbol}{demo} | {e.balance:,.4f} | ${e.price_usd:,.6f} "
                    f"| {entry} | ${e.value_usd:,.2f} | {pnl} | {pct} |"
                )
            if report.pnl.pnl_usd is not None:
                lines.append("")
                lines.append(f"**Total estimated PnL:** ${report.pnl.pnl_usd:+,.2f} "
                             f"(covers ${report.pnl.covered_value_usd:,.2f} of "
                             f"${report.pnl.value_usd:,.2f} value; the rest has no public cost basis)")
                lines.append(f"**Portfolio value (known):** ${report.total_value_usd:,.2f}" if report.total_value_usd is not None else "")
            lines.append("")

        if report.research_notes:
            lines.append("## 🔎 Research notes")
            lines.append("")
            for n in report.research_notes:
                lines.append(f"- {n}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            "⚠️ **This is a risk-screening aid, not financial advice.** Signals are "
            "heuristics over public data (RPC, CoinGecko, bundled snapshots); a clean "
            "report does not mean a wallet is safe and a bad one does not mean theft "
            "is imminent. Always verify on-chain before acting."
        )
        return "\n".join(lines)


class LLMReporter:
    """OpenAI-compatible LLM writer with hard rule-based fallback."""

    name = "llm"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = config.LLM_TIMEOUT_S,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.LLM_API_KEY
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.model = model or config.LLM_MODEL
        self.timeout = timeout

    def _digest(self, report: RiskReport, snapshot: WalletSnapshot) -> dict:
        return {
            "address": report.address,
            "score": report.score,
            "band": report.band,
            "signals": [s.__dict__ for s in report.signals],
            "warnings": report.warnings,
            "token_rug": report.token_rug,
            "pnl": report.pnl.as_dict() if report.pnl else None,
            "total_value_usd": report.total_value_usd,
            "holdings": [t.as_dict() for t in snapshot.tokens if t.value_usd is not None][:25],
            "approvals": [a.as_dict() for a in snapshot.approvals],
            "notes": report.research_notes,
        }

    def render(self, report: RiskReport, snapshot: WalletSnapshot) -> tuple[str, str]:
        """Returns (report_text, backend_used). Never raises."""
        if not self.api_key:
            fallback = RuleReporter().render(report, snapshot)
            return fallback, "rule (no OPENAI_API_KEY)"
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "max_tokens": 1200,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a cautious on-chain risk analyst. Write a "
                                "plain-English wallet risk report (max ~250 words): "
                                "score, the biggest dangers, what the user should do "
                                "(revoke approvals etc.), and a one-line disclaimer "
                                "that this is a screening aid, not financial advice. "
                                "Never invent numbers that are not in the digest."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(self._digest(report, snapshot)),
                        },
                    ],
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            if not text:
                raise ValueError("empty LLM response")
            return text, "llm"
        except Exception:
            return RuleReporter().render(report, snapshot), "rule (LLM failed — fallback)"