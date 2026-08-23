"""Provider layer: fixture loading + live-RPC guards (offline)."""

from __future__ import annotations

import json

import pytest

from chain_scout import config
from chain_scout.provider import FixtureProvider, LiveProvider, make_provider

from .helpers import fake_address

# ---------------------------------------------------------------------------
# fixture provider
# ---------------------------------------------------------------------------


def test_fixture_loads_demo_wallet():
    prov = FixtureProvider()
    snap = prov.fetch(config.DEMO_WALLET_ADDRESS)
    assert snap.data_source == "fixture"
    assert snap.address.lower() == config.DEMO_WALLET_ADDRESS.lower()
    assert len(snap.tokens) >= 20
    assert len(snap.transfers) >= 20
    assert snap.trust_senders
    total = snap.total_value_usd()
    assert total is not None and total > 0


def test_fixture_rejects_other_addresses():
    prov = FixtureProvider()
    with pytest.raises(ValueError, match="fixture wallet is"):
        prov.fetch(fake_address("someone else"))


def test_fixture_missing_file_raises(tmp_path):
    prov = FixtureProvider(path=tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError):
        prov.fetch(config.DEMO_WALLET_ADDRESS)


def test_fixture_matches_demo_address_case_insensitive():
    prov = FixtureProvider()
    assert prov.matches(config.DEMO_WALLET_ADDRESS.upper())


# ---------------------------------------------------------------------------
# live provider guards (no network needed)
# ---------------------------------------------------------------------------


def test_live_mainnet_refused_without_flag(monkeypatch):
    monkeypatch.delenv("MAINNET_ALLOWED", raising=False)
    monkeypatch.delenv("CHAIN_SCOUT_RPC_URL", raising=False)
    with pytest.raises(ValueError, match="MAINNET_ALLOWED"):
        LiveProvider(chain_id=config.CHAIN_ID_MAINNET)


def test_live_mainnet_unlocked_with_flag(monkeypatch):
    monkeypatch.setenv("MAINNET_ALLOWED", "1")
    monkeypatch.delenv("CHAIN_SCOUT_RPC_URL", raising=False)
    prov = LiveProvider(chain_id=config.CHAIN_ID_MAINNET)
    assert prov.rpc_url == config.RPC_MAINNET


def test_live_sepolia_default_offline(monkeypatch):
    monkeypatch.delenv("MAINNET_ALLOWED", raising=False)
    monkeypatch.delenv("CHAIN_SCOUT_RPC_URL", raising=False)
    prov = LiveProvider(chain_id=config.CHAIN_ID_SEPOLIA)
    assert prov.rpc_url == config.RPC_DEFAULT_SEPOLIA


def test_live_rpc_env_override(monkeypatch):
    monkeypatch.setenv("CHAIN_SCOUT_RPC_URL", "https://example.invalid/rpc")
    prov = LiveProvider(chain_id=config.CHAIN_ID_SEPOLIA)
    assert prov.rpc_url == "https://example.invalid/rpc"


def test_live_unreachable_rpc_raises_connection_error():
    prov = LiveProvider(chain_id=config.CHAIN_ID_SEPOLIA, rpc_url="http://127.0.0.1:1")
    with pytest.raises(ConnectionError):
        prov.fetch("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


def test_live_invalid_address_rejected(monkeypatch):
    monkeypatch.delenv("CHAIN_SCOUT_RPC_URL", raising=False)
    # Skip the RPC entirely for this one: validation happens inside fetch(),
    # so stub out the connectivity check.
    from web3 import Web3

    import chain_scout.provider as provider_mod

    class FakeW3:
        def __init__(self, *a, **k):
            pass

        def is_connected(self):
            return True

        @staticmethod
        def to_checksum_address(value):
            raise ValueError(f"invalid address: {value}")

        @staticmethod
        def HTTPProvider(*a, **k):
            return None

    real = provider_mod.Web3
    provider_mod.Web3 = FakeW3  # type: ignore[assignment]
    try:
        prov = LiveProvider(chain_id=config.CHAIN_ID_SEPOLIA, rpc_url="https://example.invalid")
        with pytest.raises(ValueError, match="invalid address"):
            prov.fetch("not-an-address")
    finally:
        provider_mod.Web3 = real


# ---------------------------------------------------------------------------
# provider resolution
# ---------------------------------------------------------------------------


def test_make_provider_auto_uses_fixture_for_demo_address():
    prov = make_provider("auto", config.DEMO_WALLET_ADDRESS)
    assert prov.name == "fixture"


def test_make_provider_auto_uses_live_for_other_address(monkeypatch):
    monkeypatch.delenv("MAINNET_ALLOWED", raising=False)
    monkeypatch.delenv("CHAIN_SCOUT_RPC_URL", raising=False)
    prov = make_provider("auto", fake_address("unknown"))
    assert prov.name == "live"


def test_make_provider_unknown_mode_rejected():
    with pytest.raises(ValueError, match="unknown data source"):
        make_provider("telepathy", config.DEMO_WALLET_ADDRESS)


def test_fixture_json_is_valid_and_self_consistent():
    data = json.loads(config.DEMO_WALLET_FIXTURE.read_text(encoding="utf-8"))
    assert data["meta"]["address"]
    assert isinstance(data["tokens"], list) and data["tokens"]
    for t in data["tokens"]:
        assert t["balance_decimal"] >= 0
        assert isinstance(t["decimals"], int)
    for a in data["approvals"]:
        assert a["allowance"].isdigit()
    for tr in data["transfers"]:
        assert tr["direction"] in ("in", "out")