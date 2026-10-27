from uuid import uuid4


def test_chat_contract_and_unknown_trace(client) -> None:
    response = client.post(
        "/v1/chat",
        json={"message": "How does receivables advance (antecipação) work with Getnet?", "user_id": "cliente1988"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"trace_id", "answer", "route", "sources", "confidence", "handoff", "tools_used"}
    assert body["route"][0] == "guardrail"
    assert body["sources"]
    assert body["handoff"] is None

    missing = client.get(f"/v1/traces/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Unknown trace"


def test_invalid_user_id_is_rejected(client) -> None:
    response = client.post("/v1/chat", json={"message": "Hello", "user_id": "bad id"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid request"


def test_trace_hides_customer_payload(client) -> None:
    created = client.post(
        "/v1/chat",
        json={"message": "When will the money from yesterday's sales be deposited?", "user_id": "cliente1988"},
    ).json()
    trace = client.get(f"/v1/traces/{created['trace_id']}")
    assert trace.status_code == 200
    record = trace.json()
    assert record["tools"] == ["get_receivables"]
    assert record["outcome"] == "answered"
    assert "amount_brl" not in record
    assert "1840" not in str(record)
    assert "legal_name" not in record
    assert isinstance(record["latency_ms"], int)
