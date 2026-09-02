# Chain-scout tips of the day

> Maintained by `scripts/daily_update.py` (Daily Green automation) — one
> dated, non-empty AI-security / web3-wallet tip per day, rotated from the pool in
> `scripts/tips_pool.json`. Pause by creating a `.daily-pause` file in the
> repo root, or unload the scheduler job (see README, Daily Green).


## 2026-08-23 — Tip of the day: Dead tokens are free money for phishers

A token with no transfers in 30 days is 'dead' — yet it still shows a balance and a fake 'swap' button somewhere. Chain-scout scores dead tokens into rug exposure and dust exposure, because dead balances are precisely what phishing sites drain after a fresh approval.

> `chain-scout: dead_signal() window = 30 days`


## 2026-08-24 — Tip of the day: Your cost basis is not public — PnL tools must say so

Anyone claiming exact PnL from an address alone is guessing: cost basis lives off-chain (exchanges, wallets, tax records). Chain-scout only reports PnL where an entry price exists (demo wallets carry clearly-labeled demo entries); everything else is value-only. Treat 'AI PnL estimates' as entertainment, not tax advice.

> `chain-scout: estimate_pnl() skips tokens without basis`


## 2026-08-25 — Tip of the day: Whitelist your exchanges in the phishing scan

Inbound transfers from Binance/Coinbase hot wallets are normal activity; transfers from random EOA contracts are the airdrop-bait pattern. Chain-scout ships a small trusted-sender set (add your own via the fixture) and scores the share of unknown-sender inbound transfers in the last 30 days.

> `chain-scout: trust_senders in fixtures/demo_wallet.json`


## 2026-08-26 — Tip of the day: Decimals lie: check the token contract, not the label

A token with 6 decimals displays 1,000,000 units where one with 18 decimals shows 1,000,000,000,000,000,000 units of the same 'amount'. Scanners that ignore decimals produce fantasy valuations. Chain-scout always converts raw balances through the token's declared decimals before pricing.

> `chain-scout: TokenHolding.decimals drives all value math`


## 2026-08-27 — Tip of the day: Unlimited approval to a known router is still a risk

Infinite allowances to Uniswap/SushiSwap routers can't be drained by the router code today — but router upgrades, governance attacks and exploit chains make 'known and safe' a status that decays. Chain-scout downgrades router approvals to 'watch' and tells you to right-size them when convenient.

> `chain-scout: classify_approval() router branch -> 'watch'`


## 2026-08-28 — Tip of the day: Rainbow-phishing uses NFT approvals, not just ERC-20

setApprovalForAll is the ERC-721/1155 cousin of approve(): one signature and a marketplace contract can move every NFT you own. Chain-scout currently covers ERC-20; treat setApprovalForAll grants with the same paranoia and revoke them at the same cadence.

> `revoke.cash covers both token standards`


## 2026-08-29 — Tip of the day: A high risk score is a warning, not a verdict

Risk scores aggregate public-data signals and miss everything off-chain (who controls the deployer key, what the team is doing, regulatory status). Chain-scout's report always says so, and the score formula is printed inside the app — read it before you act on it.

> `chain-scout: 'How the score works' expander in app.py`


## 2026-08-30 — Tip of the day: Multichain wallets need per-chain scans

An approval on Ethereum says nothing about your Arbitrum or Polygon exposure: allowances are per-chain, per-token, per-spender. Chain-scout is Ethereum-first (Sepolia default) — add RPC endpoints for other chains and re-run the same heuristics per chain.

> `CHAIN_SCOUT_RPC_URL=https://… any chain's public RPC`


## 2026-08-31 — Tip of the day: Beware the 'verification' fake: verified code ≠ safe code

Scam tokens get their source verified on explorers too — verification only proves the deployed bytecode matches some source, not that the source is honest (hidden mint functions, blacklisted-router tax, owner-only transfers all verify fine). Don't let a green 'verified' checkmark replace your own flag checks.

> `chain-scout: treat holder/liquidity signals as primary, verified flag as noise`


## 2026-09-01 — Tip of the day: Keyless scanners are reproducible scanners

If a scanner needs your private API key, its results cannot be independently re-run — and 'trust me, I have the key' is exactly how scam tools operate. Chain-scout runs keyless (public RPC, free CoinGecko tier, bundled fixtures) so anyone can verify any report. Same logic applies to the tools you use.

> `python scripts/fetch_fixtures.py   # rebuilds the demo data`


## 2026-09-02 — Tip of the day: Fast-blockchain scams are faster — check time-to-rug

On chains with 2s blocks, a 'liquidity added, then removed within an hour' pattern is a rug you can watch in real time. For any token you buy on a fast chain, snapshot liquidity and top-10 holders when you enter, and diff them a week later. Chain-scout's fixture format makes such snapshots easy to persist.

> `chain-scout: run the scanner weekly, diff token_rug scores`

