"""Shipped fixture hygiene: schema, addresses, cross-references, demo flags."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from chain_scout import config
from chain_scout.models import parse_ts

HEX40 = re.compile(r"^0x[0-9a-fA-F]{40}$")

FIXTURE = config.DEMO_WALLET_FIXTURE


@pytest.fixture(scope="module")
def data():
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    import json

    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_meta_shape(data):
    meta = data["meta"]
    assert HEX40.match(meta["address"])
    assert meta["chain"]
    assert meta["source"]
    assert parse_ts(meta["snapshot_ts"]) is not None
    assert isinstance(meta["notes"], list) and meta["notes"]


def test_eth_block(data):
    eth = data["eth"]
    assert eth["balance_decimal"] > 0
    assert eth["price_usd"] is None or eth["price_usd"] > 0


def test_token_rows_wellformed(data):
    seen = set()
    for t in data["tokens"]:
        assert HEX40.match(t["address"]), t
        assert t["symbol"] and t["name"]
        assert 0 <= t["decimals"] <= 77
        assert t["balance_decimal"] >= 0
        assert t["address"] not in seen
        seen.add(t["address"])
        if t.get("price_usd"):
            assert not (t["price_usd"] < 0)
        if t.get("top10_holder_share") is not None:
            assert 0.0 <= t["top10_holder_share"] <= 1.0
        if t.get("total_supply"):
            assert t["total_supply"] > 0 or t["total_supply"] == 0


def test_demo_flags_present_in_fixture(data):
    assert any(t["is_demo"] for t in data["tokens"]), "demo tokens must exist"
    assert any(a["is_demo"] for a in data["approvals"]), "demo approvals must exist"


def test_approvals_reference_known_tokens(data):
    token_addrs = {t["address"].lower() for t in data["tokens"]}
    for a in data["approvals"]:
        assert HEX40.match(a["spender"])
        assert a["token_address"].lower() in token_addrs, (
            f"approval references unknown token {a['token_address']}"
        )
        assert a["allowance"].isdigit() or a["allowance"] == "0"


def test_transfers_wellformed(data):
    for tr in data["transfers"]:
        assert tr["direction"] in ("in", "out")
        assert tr["token_symbol"]
        assert parse_ts(tr["timestamp"]) is not None
        assert tr["value_decimal"] >= 0


def test_trust_senders_are_hex(data):
    for s in data["trust_senders"]:
        assert HEX40.match(s)


def test_demo_wallet_is_the_shipped_address(data):
    assert data["meta"]["address"].lower() == config.DEMO_WALLET_ADDRESS.lower()


def test_fixture_parses_with_provider(data):
    from chain_scout.provider import FixtureProvider

    snap = FixtureProvider().fetch(config.DEMO_WALLET_ADDRESS)
    assert len(snap.tokens) == len(data["tokens"])