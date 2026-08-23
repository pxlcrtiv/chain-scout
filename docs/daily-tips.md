# Chain-scout tips of the day

> Maintained by `scripts/daily_update.py` (Daily Green automation) — one
> dated, non-empty AI-security / web3-wallet tip per day, rotated from the pool in
> `scripts/tips_pool.json`. Pause by creating a `.daily-pause` file in the
> repo root, or unload the scheduler job (see README, Daily Green).


## 2026-08-23 — Tip of the day: Dead tokens are free money for phishers

A token with no transfers in 30 days is 'dead' — yet it still shows a balance and a fake 'swap' button somewhere. Chain-scout scores dead tokens into rug exposure and dust exposure, because dead balances are precisely what phishing sites drain after a fresh approval.

> `chain-scout: dead_signal() window = 30 days`

