"""Chain Scout — AI wallet risk scanner (Streamlit UI).

Zero-key demo:  ``streamlit run app.py`` -> paste the demo address
(0xd8dA...96045, shown below) -> full risk report. Works with no RPC, no
API keys, no LLM key (deterministic rule reporter kicks in automatically).

Live scanning defaults to **Sepolia**; mainnet needs ``MAINNET_ALLOWED=1``
(see README "Networks"). Optional upgrades, all via env vars:

    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL  -> LLM-written report
    ETHERSCAN_API_KEY                                -> full history scans
    CHAIN_SCOUT_RPC_URL                              -> custom RPC endpoint
"""

from __future__ import annotations

import streamlit as st

from chain_scout import config
from chain_scout.analysis import analyze, validate_address
from chain_scout.report import LLMReporter

BAND_COLORS = {"Low": "#22c55e", "Moderate": "#eab308", "Elevated": "#f97316", "High": "#ef4444"}

st.set_page_config(page_title="Chain Scout — AI wallet risk scanner", page_icon="🛰️", layout="wide")

st.title("🛰️ Chain Scout")
st.caption(
    "Paste any Ethereum address → plain-English AI risk report: rug-pulled tokens, "
    "dangerous approvals, holder concentration, estimated PnL. "
    "**Risk screening aid — not financial advice.**"
)

DEMO_ADDRESS = config.DEMO_WALLET_ADDRESS

with st.sidebar:
    st.header("Scan")
    source = st.selectbox(
        "Data source",
        ["auto (recommended)", "fixture demo", "live (Sepolia RPC)"],
        help=(
            "auto: the bundled fixture wallet uses its offline demo data; any other "
            "address falls back to a live Sepolia RPC scan. fixture: offline demo data "
            "only. live: Sepolia public RPC (mainnet requires MAINNET_ALLOWED=1)."
        ),
    )
    address = st.text_input(
        "Ethereum address",
        value=DEMO_ADDRESS,
        placeholder="0x…",
        help=f"Demo wallet (bundled fixture): {DEMO_ADDRESS}",
    )
    run = st.button("Analyze risk", type="primary", use_container_width=True)
    with st.expander("Zero-key defaults & keys"):
        st.markdown(
            "- **No keys needed** for the demo: bundled fixture + public RPC + "
            "CoinGecko free tier.\n"
            "- `OPENAI_API_KEY` → LLM-written report (otherwise the deterministic "
            "rule reporter writes it).\n"
            "- `ETHERSCAN_API_KEY` → full-history approvals/transfers (see README).\n"
            "- `MAINNET_ALLOWED=1` → unlock the mainnet RPC (testnet-first design)."
        )


def render_report(snapshot, report) -> None:
    score = report.score
    band = report.band
    color = BAND_COLORS.get(band, "#64748b")

    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        st.markdown(
            f"<div style='font-size:52px;font-weight:800;color:{color}'>{score}/100</div>"
            f"<div style='font-size:18px;color:{color}'>Risk band: {band}</div>",
            unsafe_allow_html=True,
        )
        st.progress(min(score, 100) / 100.0)
    with c2:
        st.metric("Portfolio value (known)", f"${report.total_value_usd:,.0f}" if report.total_value_usd is not None else "n/a")
        st.metric("Chain", report.chain)
    with c3:
        st.metric("Data source", "fixture (demo)" if report.data_source == "fixture" else "live RPC")
        ens = report.ens_name or "—"
        st.metric("ENS", ens)

    if report.warnings:
        st.subheader("⚠️ Key warnings")
        for w in report.warnings[:12]:
            st.error(w)

    with st.expander("How the score works (transparent formula)"):
        st.markdown(
            "`risk = 100 × SUM(weight × severity for known signals) / "
            "SUM(weight for known signals)` — unknown signals are excluded and "
            "the remaining weights renormalize; nothing is hidden."
        )
        rows = [
            {
                "signal": f"{s.label} (w={s.weight:.2f})",
                "severity": f"{s.severity:.3f}" if s.known else "unknown",
                "contribution": f"{s.contribution:.3f}" if s.known else "—",
                "detail": s.detail,
            }
            for s in report.signals
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    tabs = st.tabs(
        ["📝 Plain-English report", "💼 Holdings", "🔓 Approvals", "🚩 Rug flags", "📊 Transfers", "📈 PnL estimate"]
    )

    with tabs[0]:
        llm = LLMReporter()
        text, backend = llm.render(report, snapshot)
        st.caption(f"Report backend: {backend}")
        st.markdown(text)
        st.download_button(
            "Download report (.md)",
            data=text,
            file_name=f"chain-scout-{report.address[:8]}.md",
            mime="text/markdown",
        )

    with tabs[1]:
        if snapshot.tokens:
            st.dataframe(
                [
                    {
                        "symbol": t.symbol + (" (demo)" if t.is_demo else ""),
                        "balance": f"{t.balance_decimal:,.4f}",
                        "price": f"${t.price_usd:,.6f}" if t.price_usd is not None else "n/a",
                        "value": f"${t.value_usd:,.2f}" if t.value_usd is not None else "n/a",
                        "holders": t.holders_count if t.holders_count is not None else "n/a",
                        "rug score": report.token_rug.get(t.symbol, {}).get("score", "n/a"),
                    }
                    for t in sorted(
                        snapshot.tokens,
                        key=lambda t: t.value_usd or 0.0,
                        reverse=True,
                    )
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No token holdings in this snapshot.")

    with tabs[2]:
        if snapshot.approvals:
            from chain_scout.heuristics import classify_approval

            st.dataframe(
                [
                    {
                        "token": a.token_symbol + (" (demo)" if a.is_demo else ""),
                        "spender": a.spender,
                        "allowance": "unlimited" if a.is_unlimited else f"{int(a.allowance or 0):,}",
                        "verdict": classify_approval(a)[0],
                        "why": "; ".join(classify_approval(a)[1]),
                    }
                    for a in snapshot.approvals
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No approval data — full-history approval scans need ETHERSCAN_API_KEY.")

    with tabs[3]:
        flagged = {
            sym: info
            for sym, info in report.token_rug.items()
            if info["known"] and info["score"] >= 0.4
        }
        if flagged:
            for sym in sorted(flagged, key=lambda s: -flagged[s]["score"]):
                info = flagged[sym]
                st.warning(f"**{sym}** — rug score {info['score']:.2f} | " + "; ".join(info["reasons"]))
        else:
            st.success("No tokens with rug score ≥ 0.40.")

    with tabs[4]:
        if snapshot.transfers:
            st.dataframe(
                [
                    {
                        "when": t.timestamp or "n/a",
                        "symbol": t.token_symbol,
                        "dir": t.direction,
                        "value": f"{t.value_decimal:,.6f}",
                        "sender": (t.sender or "")[:14],
                        "receiver": (t.receiver or "")[:14],
                    }
                    for t in snapshot.transfers[:40]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No transfer history (keyless live scans don't index history).")

    with tabs[5]:
        if report.pnl and report.pnl.entries:
            st.dataframe(
                [
                    {
                        "symbol": e.symbol + (" (demo)" if e.is_demo else ""),
                        "balance": f"{e.balance:,.4f}",
                        "price": f"${e.price_usd:,.6f}",
                        "entry (est.)": f"${e.entry_price:,.6f}" if e.entry_price is not None else "n/a",
                        "value": f"${e.value_usd:,.2f}",
                        "pnl": f"${e.pnl_usd:+,.2f}" if e.pnl_usd is not None else "n/a — cost basis unknown",
                        "pnl %": f"{e.pnl_pct:+.1f}%" if e.pnl_pct is not None else "",
                    }
                    for e in report.pnl.entries
                ],
                use_container_width=True,
                hide_index=True,
            )
            if report.pnl.pnl_usd is not None:
                st.metric(
                    "Total estimated PnL",
                    f"${report.pnl.pnl_usd:+,.2f}",
                    delta=f"covers ${report.pnl.covered_value_usd:,.0f} of ${report.pnl.value_usd:,.0f} value",
                )
            st.caption(
                "Cost basis is usually not public — demo entries are labeled; everything "
                "else reports value only. This is an estimate, not tax advice."
            )
        else:
            st.info("No holdings to price.")

    if report.research_notes:
        st.subheader("🔎 Research notes")
        for n in report.research_notes:
            st.info(n)


if run or address:
    try:
        addr = validate_address(address)
        mode = "auto"
        if source.startswith("fixture"):
            mode = "fixture"
        elif source.startswith("live"):
            mode = "live"
        with st.spinner("Scanning public data…"):
            snapshot, report = analyze(addr, mode)
        st.divider()
        render_report(snapshot, report)
    except (ValueError, ConnectionError, FileNotFoundError) as exc:
        st.error(str(exc))

st.divider()
st.caption(
    f"Chain Scout v{config.VERSION} — keyless by design · testnet-first (Sepolia default, "
    "mainnet default-off) · data: BlockScout/CoinGecko/RPC snapshots + bundled fixtures · "
    "not investment advice."
)