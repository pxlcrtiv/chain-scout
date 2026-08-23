"""Daily Green automation: pool quality, deterministic rotation, idempotency.

All pure-function tests — no git, no network, no commits.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DU_PATH = REPO_ROOT / "scripts" / "daily_update.py"
POOL_PATH = REPO_ROOT / "scripts" / "tips_pool.json"

MIN_TIPS = 20


@pytest.fixture(scope="module")
def daily():
    assert DU_PATH.exists(), f"missing {DU_PATH}"
    spec = importlib.util.spec_from_file_location("daily_update", DU_PATH)
    assert spec is not None and spec.loader is not None, "daily_update.py not importable"
    mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pool():
    assert POOL_PATH.exists(), f"missing {POOL_PATH}"
    return json.loads(POOL_PATH.read_text(encoding="utf-8"))


def test_pool_has_enough_tips(pool):
    assert len(pool) >= MIN_TIPS, f"pool has {len(pool)} tips, need >= {MIN_TIPS}"


def test_pool_entries_wellformed(pool):
    for tip in pool:
        assert tip["title"].strip()
        assert tip["body"].strip()
        assert len(tip["title"]) <= 120
        assert isinstance(tip.get("command", ""), str)


def test_pool_titles_unique(pool):
    titles = [t["title"] for t in pool]
    assert len(set(titles)) == len(titles), "duplicate titles water down the pool"


def test_rotation_is_deterministic(daily, pool):
    day = dt.date(2026, 8, 23)
    assert daily.pool_tip(day, pool) == daily.pool_tip(day, pool)


def test_rotation_covers_consecutive_days(daily, pool):
    day = dt.date(2026, 8, 23)
    seen = {daily.pool_tip(day + dt.timedelta(days=i), pool)["title"] for i in range(len(pool))}
    assert len(seen) >= len(pool) - 1  # at most one collision when pool size == span


def test_plan_days_idempotent_when_current(daily):
    now = dt.date(2026, 8, 23)
    have = {now}
    assert daily.plan_days(now, have) == []


def test_plan_days_backfills_gap(daily):
    now = dt.date(2026, 8, 23)
    have = {dt.date(2026, 8, 20)}
    days = daily.plan_days(now, have)
    assert days == [dt.date(2026, 8, 21), dt.date(2026, 8, 22), dt.date(2026, 8, 23)]


def test_plan_days_never_predates_history(daily):
    now = dt.date(2026, 8, 23)
    have = {dt.date(2026, 1, 1)}
    assert daily.plan_days(now, have)[0] >= dt.date(2026, 1, 1)


def test_render_entry_contains_date_and_title(daily, pool):
    day = dt.date(2026, 8, 23)
    lines = daily.render_entry(day, pool[0])
    text = "\n".join(lines)
    assert day.isoformat() in text
    assert pool[0]["title"] in text


def test_log_header_present(daily):
    header = "\n".join(daily.LOG_HEADER)
    assert "daily" in header.lower()
    assert any("chains" in h.lower() or "chain-scout" in h.lower() for h in daily.LOG_HEADER)