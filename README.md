# 🛰️ Chain Scout — AI wallet risk scanner

**Paste any Ethereum address → a plain-English AI risk report: rug-pulled
tokens, dangerous approvals, holder concentration, estimated PnL.**

Chain Scout turns public on-chain data into a transparent, weighted risk
score and a human-readable report — **keyless by default** (bundled fixture +
public RPC + CoinGecko free tier), **testnet-first** (Sepolia default, mainnet
default-off), and honest about what it does and does not know.

## The problem

Almost every wallet-drain story follows the same recipe: a *dust airdrop*
arrives from an unknown contract, the victim clicks "Approve to swap" on a
cloned frontend, signs a **max-uint allowance** to an EOA or a brand-new
contract, and their real tokens vanish. Meanwhile, rug-pulled tokens sit in
portfolios at 99% losses, and holders of token *nobody can sell* don't find
out until they try.

The data that exposes all of this — approvals, holder concentration,
liquidity depth, transfer patterns — is public. But reading it takes an
explorer, an indexer key, and a spreadsheet. Chain Scout is that reading,
automated, with the math shown.

## The solution

```
address ──► provider (fixture | live RPC) ──► heuristics ──► weighted score ──► plain-English report
                                                     │
                                                     ├─ approvals: unlimited? EOA spender? known-bad? router?
                                                     ├─ rug flags: top-10 holder share, mcap/liquidity, dead tokens
                                                     ├─ dust & inbound: phishing-bait exposure
                                                     └─ PnL: where a cost basis exists (labeled demo entries otherwise)
```

## Features

| Feature | How it works | Keyless |
|---|---|---|
| **Approvals scan** | ERC-20 allowances classified *safe / watch / dangerous* (unlimited, EOA spender, known-bad list, DEX-router allowlist) with a USD-exposure share | ✅ fixture; live via bounded RPC log scans or `ETHERSCAN_API_KEY` |
| **Rug heuristics** | per-token rug score from holder concentration (exact top-10 share or holders-count proxy), market-cap/liquidity ratio, 30-day activity | ✅ |
| **Dust & phishing exposure** | sub-$50 "dust" tokens + share of 30-day inbound transfers from unknown senders (trusted CEX hot-wallet list) | ✅ |
| **PnL estimate** | `(price − entry) × balance` where an entry price exists — demo entries are labeled, everything else is value-only (cost basis is rarely public) | ✅ CoinGecko pricing; ✅ demo entries in fixture |
| **Composite risk score** | `100 × Σ(w·s known) / Σ(w known)` — every weight and threshold is printed in the app | ✅ |
| **AI report** | OpenAI-compatible LLM (any endpoint: `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`); hard deterministic rule fallback, zero keys required | ✅ |
| **Live scan** | public-RPC balances (web3.py); Sepolia default, mainnet gated behind `MAINNET_ALLOWED=1` | ✅ |

## Quickstart (zero keys, ≤ 5 min)

```bash
git clone https://github.com/pxlcrtiv/chain-scout
cd chain-scout
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

1. The demo address is **pre-filled**:
   `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045` (vitalik.eth).
2. Click **Analyze risk**.
3. You get the risk card: score + band, the transparent formula breakdown,
   warnings, holdings, approvals with verdicts, rug flags, transfers and the
   PnL tab — all offline, all from the bundled fixture.

> The demo fixture is a *real mainnet snapshot* (Blockscout + public RPC +
> CoinGecko, rebuilt via `scripts/fetch_fixtures.py`) plus **clearly-labeled
> simulated entries** (the `RUGX`/`MOONP` tokens, demo approvals, demo cost
> bases — flagged `(demo)` in the UI) that exercise every heuristic branch.
> No bytes are hidden: the JSON marks every synthetic field, and the app
> labels them.

```bash
# the live scan (Sepolia testnet; no funds, no keys):
streamlit run app.py   # data source -> "live (Sepolia RPC)"
```

**Run the tests** (offline, deterministic, ~1s):

```bash
pip install pytest ruff
pytest tests/ -q        # 85 tests
ruff check chain_scout tests scripts app.py
```

## How the score works (transparent formula)

```
risk = 100 × Σ(weight × severity, over KNOWN signals) / Σ(weight, over KNOWN signals)
```

Signals whose data is unavailable are **excluded** and the remaining weights
renormalize — an unknown signal neither adds nor removes risk. Severity per
signal is in [0, 1] (1 = maximum risk).

| Signal | Weight | Severity components |
|---|---|---|
| Approval risk | 0.35 | USD share of the portfolio under *dangerous* (unlimited to EOA / known-bad / unknown contract) or *watch* (unlimited to a known router) approvals |
| Rug exposure | 0.35 | value-weighted per-token rug score — concentration (top-10 ≥ 90% → 1.0; ≥60% → 0.65; ≥40% → 0.30; else 0; holders-count proxy when the exact share is unavailable keylessly) · liquidity (mcap > 20× liq → 1.0; >10× → 0.6; >5× → 0.25) · dead token (no transfers in 30 days → 0.5) |
| Dust exposure | 0.15 | `min(1, dusty_tokens / 15)` — sub-$50 holdings outside the top 3 |
| Inbound exposure | 0.15 | share of 30-day inbound transfers from non-trusted senders (airdrop-bait pattern) |

Bands: **0–19 Low · 20–39 Moderate · 40–69 Elevated · 70–100 High**.

Rug flags are surfaced per token (score ≥ 0.40) with the exact reason —
e.g. `RUGX (rug score 0.76): top-10 holders own >=90% of supply; market cap >20x liquidity; no transfers in the last 30 days`.

## Data & privacy

- **Keyless**: public RPC (publicnode), Blockscout v2 (mainnet snapshots),
  CoinGecko free tier, bundled fixtures. Nothing needs an API key.
- **Optional keys** (never required, README-documented):
  - `ETHERSCAN_API_KEY` → full-history approvals / transfers / holder analytics
    (put it in `~/portfolio/.env` for this dev setup, or export it anywhere).
    Without it, live scans do balances only and say so.
  - `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`, `OPENAI_MODEL`) → LLM-written report;
    without it the deterministic rule reporter writes the report.
- **No private data**: scanning reads public chain state; addresses are not
  stored.
- **Testnet-first**: live scanning defaults to **Sepolia**. Mainnet RPC is
  refused unless `MAINNET_ALLOWED=1` (an explicit opt-in to scanning real
  funds). This project never touches real funds.

## Networks

| Chain | Status |
|---|---|
| Sepolia | ✅ default live scan (`https://ethereum-sepolia-rpc.publicnode.com`, or `CHAIN_SCOUT_RPC_URL`) |
| Mainnet | 🔒 opt-in via `MAINNET_ALLOWED=1`; the bundled *fixture* is a mainnet snapshot used offline |
| Other chains | point `CHAIN_SCOUT_RPC_URL` at any public RPC; pricing/history features degrade gracefully |

## Tech stack

| Layer | Choice |
|---|---|
| UI | Streamlit (`app.py`) |
| Data | web3.py (public RPC), Blockscout v2 (fixture builder), CoinGecko (pricing) |
| Analysis | pure-Python heuristic + scoring engine (`chain_scout/`), pandas for display |
| LLM report | any OpenAI-compatible `/chat/completions` endpoint, with deterministic rule fallback |
| Tests | pytest — 85 offline tests incl. golden score tests; ruff lint |

## Repository layout

```
app.py                     Streamlit UI (zero-key demo)
chain_scout/               engine: models, heuristics, scoring, pricing, provider, report, analysis
fixtures/demo_wallet.json  bundled demo wallet (real snapshot + labeled sims)
scripts/fetch_fixtures.py  reproducible fixture builder (provenance)
scripts/daily_update.py    Daily Green automation
scripts/tips_pool.json     22 curated AI-security/web3 tips
tests/                     85 offline tests
.github/workflows/         ci.yml + daily.yml (valid; runners gated by account billing lock)
```

## Daily Green automation

This repo makes one meaningful, dated commit every single day — no empty
commits and no filler: each day appends one hand-curated AI-security / web3
wallet tip to `docs/daily-tips.md`, rotated deterministically from a pool.

**How it runs**

- `scripts/daily_update.py` picks today's tip from `scripts/tips_pool.json`
  (calendar-day rotation), appends it to `docs/daily-tips.md`, commits it as
  `docs: daily chain-scout tip YYYY-MM-DD` and pushes.
- Idempotent: a day is never committed twice; repeated runs are no-ops.
- Local scheduler (primary): macOS `launchd` runs it at **12:07 and 18:07
  local** (`~/Library/LaunchAgents/com.pxlcrtiv.daily-green.plist`, wrapper
  `~/portfolio/scripts/daily-green.sh` — it auto-discovers every repo under
  `~/portfolio/repos/`, so this repo was picked up with no wrapper edits).
- Cloud fallback: `.github/workflows/daily.yml` runs the same script at
  **12:00 UTC** on GitHub Actions. Whichever fires first wins the day; the
  other sees the entry already exists and exits cleanly. If the machine was
  off for days, the next run **backfills every missed day** — one dated,
  non-empty commit per day (max 14) — so the contribution graph stays green.
- Run log: `~/.daily-green/daily-green.log`.

> Note: this GitHub account currently cannot start Actions runners at all
> (account billing lock — every job dies before starting, CI badge included).
> The workflow files are valid and take over automatically once that's
> resolved; until then the local launchd job is the live scheduler and the
> CI badge stays red.

**Customize**

- Add or edit entries in `scripts/tips_pool.json` (`title`, `body`, optional
  `command`). The pool rotates by calendar day, so any change reshuffles the
  sequence from then on.
- Change the time: edit `Hour`/`Minute` in the launchd plist and reload
  (`launchctl bootout` + `bootstrap`), or the `cron:` line in
  `.github/workflows/daily.yml`.

**Pause**

- This repo only: `touch .daily-pause` in the repo root (delete the file to
  resume).
- Everything: `launchctl bootout gui/$(id -u)/com.pxlcrtiv.daily-green`

## Honest caveats

- **This is a risk-screening aid, not financial advice.** Signals are
  heuristics over public data; a clean report ≠ a safe wallet, and a bad one
  ≠ imminent theft. Verify on-chain before acting.
- **Fixtures are snapshots, not live truth.** The bundled wallet mixes a real
  mainnet snapshot with labeled simulated entries.
- **Keyless live scans are limited**: balances are real, but transfer/approval
  *history* needs an indexer key.
- **PnL is an estimate** and only where a cost basis exists — cost basis is
  rarely public. Demo entries are labeled as such.
- **Score coverage**: unknown signals are excluded and weights renormalize —
  a wallet with little data gets a score covering only what is known.

## Sister projects

- [model-ledger](https://github.com/pxlcrtiv/model-ledger) — on-chain asset registry: Solidity + Foundry + CLI
- [slither-chat](https://github.com/pxlcrtiv/slither-chat) — smart-contract audit copilot: Slither findings explained
- [agent-lab](https://github.com/pxlcrtiv/agent-lab) — agentic tooling lab

## License

MIT — see [LICENSE](LICENSE). Roadmap and contributing notes in
[CONTRIBUTING.md](CONTRIBUTING.md) / [CHANGELOG.md](CHANGELOG.md).