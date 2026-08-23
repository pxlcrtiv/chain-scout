# Contributing to chain-scout

First off: **thank you** — this project lives on community findings. Wallet
security is a team sport.

## Ground rules

- **The score must stay transparent.** Every weight, threshold and band
  lives in `chain_scout/config.py`; the formula is documented in `scoring.py`
  and printed in the UI. Any change to the math must land in *all three*
  places and update the golden tests (`tests/test_scoring_golden.py`).
- **The offline path must keep working.** `analyze(addr, "fixture")` runs
  with no network, no keys, no LLM. New data sources and backends must
  degrade gracefully to the bundled fixture + rule reporter.
- **Never hardcode a key.** Everything network-y reads env vars
  (`ETHERSCAN_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`,
  `CHAIN_SCOUT_RPC_URL`) or public endpoints. No secrets in fixtures either —
  simulated demo data is always flagged `is_demo`/`entry_is_demo`.
- **Label every synthetic byte.** The bundled demo wallet exists to exercise
  every heuristic branch; anything simulated must carry its flag and a note.
- **Testnet-first.** Live scanning defaults to Sepolia; mainnet stays behind
  `MAINNET_ALLOWED=1`.

## Getting started

```bash
git clone https://github.com/pxlcrtiv/chain-scout
cd chain-scout
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest ruff
pytest tests/ -q          # 85 offline tests
ruff check chain_scout tests scripts app.py
```

## Adding a heuristic or signal

1. Implement the pure function in `chain_scout/heuristics.py`
   (input → severity/score, no network, no clock — pass `now` explicitly).
2. Wire it into `compute_signals()` in `chain_scout/scoring.py` with a weight
   in `config.SIGNAL_WEIGHTS`.
3. Render it in `RuleReporter` (`chain_scout/report.py`) and the Streamlit
   tabs (`app.py`).
4. Add unit tests + a golden test with a hand-computed expected score.

## Tests

- Everything is offline and deterministic (fixtures only; network tests are
  marked `network` and skipped by default).
- Golden tests pin exact integer scores — change a threshold and a golden
  test should tell you loudly.

## Pull requests

Small, focused PRs; update `CHANGELOG.md` ("Unreleased" section); run tests
and ruff before pushing. Keep the README feature table in sync.