"""Report writers: deterministic rule reporter + LLM fallback."""

from __future__ import annotations

from chain_scout.report import LLMReporter, RuleReporter
from chain_scout.scoring import build_report

from .helpers import NOW, approval_heavy_wallet, rug_heavy_wallet


def test_rule_reporter_is_deterministic():
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    a = RuleReporter().render(report, wallet)
    b = RuleReporter().render(report, wallet)
    assert a == b


def test_rule_reporter_contains_key_sections():
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    text = RuleReporter().render(report, wallet)
    assert "Risk report —" in text
    assert "78/100" in text or f"{report.score}/100" in text
    assert "How the score was computed" in text
    assert "risk = 100 x SUM" in text
    assert "RUGX" in text
    assert "unlimited allowance" in text
    assert "not financial advice" in text


def test_rule_reporter_lists_warnings_and_ruff_flags():
    wallet = approval_heavy_wallet()
    report = build_report(wallet, now=NOW)
    text = RuleReporter().render(report, wallet)
    assert "Key warnings" in text
    assert "BIGA" in text


def test_llm_without_key_falls_back_to_rule(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    reporter = LLMReporter(api_key="")
    text, backend = reporter.render(report, wallet)
    assert backend == "rule (no OPENAI_API_KEY)"
    assert "Risk report —" in text


def test_llm_unreachable_endpoint_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    reporter = LLMReporter(api_key="sk-test", base_url="http://127.0.0.1:1", timeout=2)
    text, backend = reporter.render(report, wallet)
    assert backend == "rule (LLM failed — fallback)"
    assert "Risk report —" in text


def test_llm_uses_llm_when_endpoint_ok(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Nothing is safe, but RUGX is the worst."}}]}

    monkeypatch.setattr(
        "chain_scout.report.requests.post", lambda *a, **k: FakeResp()
    )
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    reporter = LLMReporter(api_key="sk-test", base_url="https://llm.invalid", timeout=2)
    text, backend = reporter.render(report, wallet)
    assert backend == "llm"
    assert text == "Nothing is safe, but RUGX is the worst."


def test_llm_empty_response_falls_back(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "   "}}]}

    monkeypatch.setattr(
        "chain_scout.report.requests.post", lambda *a, **k: FakeResp()
    )
    wallet = rug_heavy_wallet()
    report = build_report(wallet, now=NOW)
    reporter = LLMReporter(api_key="sk-test", base_url="https://llm.invalid", timeout=2)
    _text, backend = reporter.render(report, wallet)
    assert backend == "rule (LLM failed — fallback)"