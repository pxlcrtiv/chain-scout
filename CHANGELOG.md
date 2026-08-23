# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-23

Initial public release.

### Added

- `app.py` — Streamlit UI: paste any Ethereum address → risk card (score +
  band), transparent formula breakdown, warnings, holdings, approvals with
  verdicts, rug flags, transfers, PnL estimate, and a plain-English report.
- Scoring engine (`chain_scout/`): composite weighted risk score with a
  fully transparent formula — `100 × Σ(w·s known) / Σ(w known)` — over four
  signals (approval risk 0.35, rug exposure 0.35, dust exposure 0.15, inbound
  exposure 0.15); unknown signals renormalize away. Bands Low/Moderate/
  Elevated/High.
- Rug heuristics: holder concentration (exact top-10 share with holders-count
  proxy fallback), market-cap/liquidity ratio bands, 30-day dead-token
  signal; per-token rug scores with human reasons.
- Approval classifier: unlimited / EOA-spender / known-bad / unknown-contract
  / DEX-router verdicts (`safe`·`watch`·`dangerous`) with a curated router
  allowlist and env-extensible known-bad list.
- Dust & phishing signals: sub-$50 dust exposure, 30-day unknown-sender
  inbound share with a trusted CEX hot-wallet list.
- PnL estimate: `(price − entry) × balance` where a cost basis exists,
  labeled demo entries otherwise (cost basis is rarely public — the report
  says so).
- Keyless data layer: FixtureProvider (bundled demo wallet:
  `fixtures/demo_wallet.json`) + LiveProvider (public RPC, Sepolia default,
  mainnet gated by `MAINNET_ALLOWED=1`).
- Fixture builder `scripts/fetch_fixtures.py`: reproducible real snapshot
  (Blockscout v2 + public RPC + CoinGecko free tier) merged with
  clearly-labeled simulated entries that exercise every branch.
- Report writers: deterministic RuleReporter + OpenAI-compatible LLMReporter
  with hard fallback (no key required).
- 85 offline deterministic tests, including golden score tests.
- CI workflow (`.github/workflows/ci.yml`) and Daily Green automation
  (`scripts/daily_update.py` + 22-tip pool) — valid workflows; runners gated
  by the account billing lock until resolved.