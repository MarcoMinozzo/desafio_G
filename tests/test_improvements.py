"""Sequence of specialists, session memory, and the metrics snapshot."""

import logging
import os
from datetime import datetime, timezone

from app.observability.metrics import MIN_SAMPLE, MetricsStore, corpus_age_days

METRICS_FIELDS = {
    "requests",
    "answered",
    "refused",
    "handoffs",
    "verified",
    "hallucinated",
    "unverified",
    "corpus_age_days",
    "corpus_stale",
    "alerts",
}


def test_mixed_question_runs_support_then_knowledge(client) -> None:
    response = client.post(
        "/v1/chat",
        json={
            "message": (
                "My card machine won't connect to the internet. "
                "How does receivables advance (antecipação) work?"
            ),
            "user_id": "cliente1988",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == ["guardrail", "router", "support", "knowledge"]
    assert "diagnose_terminal" in body["tools_used"]
    assert body["sources"]
    assert all("getnet" in source["url"] for source in body["sources"])
    trace = client.get(f"/v1/traces/{body['trace_id']}").json()
    assert trace["intent"] == "account_support"
    assert trace["route"] == body["route"]
    assert "1840" not in str(trace)


def test_follow_up_keeps_the_same_user_topic(client) -> None:
    first = client.post(
        "/v1/chat",
        json={
            "message": "How does receivables advance (antecipação) work with Getnet?",
            "user_id": "cliente1988",
        },
    ).json()
    second = client.post(
        "/v1/chat",
        json={
            "message": "and the fee?",
            "user_id": "cliente1988",
            "session_id": first["session_id"],
        },
    ).json()
    assert second["session_id"] == first["session_id"]
    assert "knowledge" in second["route"]
    assert "support" not in second["route"]
    assert second["sources"]
    trace = client.get(f"/v1/traces/{second['trace_id']}").json()
    assert trace["intent"] == "product_knowledge"
    assert trace["session_id"] == first["session_id"]


def test_session_does_not_open_for_a_different_user(client) -> None:
    first = client.post(
        "/v1/chat",
        json={
            "message": "How does receivables advance (antecipação) work with Getnet?",
            "user_id": "cliente1988",
        },
    ).json()
    other = client.post(
        "/v1/chat",
        json={
            "message": "and the fee?",
            "user_id": "cliente2000",
            "session_id": first["session_id"],
        },
    ).json()
    assert other["route"] == ["guardrail", "router"]
    assert other["sources"] == []
    assert other["tools_used"] == []
    assert "antecip" not in other["answer"].lower()
    own = client.app.state.service.sessions.latest("cliente1988", first["session_id"])
    assert own is not None
    assert client.app.state.service.sessions.latest("cliente2000", first["session_id"]) is not None
    assert own.topic != client.app.state.service.sessions.latest("cliente2000", first["session_id"]).topic
    assert "1840" not in own.topic


def test_metrics_snapshot_has_no_customer_data(client) -> None:
    client.post(
        "/v1/chat",
        json={"message": "When will the money from yesterday's sales be deposited?", "user_id": "cliente1988"},
    )
    response = client.get("/v1/metrics")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == METRICS_FIELDS
    assert body["requests"] >= 1
    assert body["answered"] >= 1
    text = str(body)
    assert "cliente1988" not in text
    assert "1840" not in text
    assert "legal_name" not in text


def test_hallucinated_ratio_alert_is_logged(caplog) -> None:
    store = MetricsStore(corpus_age_days=0)
    with caplog.at_level(logging.WARNING, logger="getnet.assist.metrics"):
        for _ in range(MIN_SAMPLE):
            store.record(outcome="answered", verdict="hallucinated")
    snapshot = store.snapshot()
    assert "hallucinated_ratio" in snapshot.alerts
    assert "corpus_stale" not in snapshot.alerts
    assert any("hallucinated_ratio" in record.message for record in caplog.records)


def test_handoff_ratio_alert(caplog) -> None:
    store = MetricsStore(corpus_age_days=0)
    with caplog.at_level(logging.WARNING, logger="getnet.assist.metrics"):
        for _ in range(6):
            store.record(outcome="handoff", verdict="unverified")
        for _ in range(4):
            store.record(outcome="answered", verdict="verified")
    assert "handoff_ratio" in store.snapshot().alerts
    assert any("handoff_ratio" in record.message for record in caplog.records)


def test_corpus_older_than_thirty_days_is_stale(tmp_path) -> None:
    page = tmp_path / "page.md"
    page.write_text("old", encoding="utf-8")
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(page, (old, old))
    age = corpus_age_days(tmp_path, now=datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert age >= 30
    snapshot = MetricsStore(corpus_age_days=age).snapshot()
    assert snapshot.corpus_stale
    assert "corpus_stale" in snapshot.alerts
