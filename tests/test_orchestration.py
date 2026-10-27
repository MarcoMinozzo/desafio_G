import re

from app.llm.client import FakeLLM
from app.main import create_app
from app.tools.merchant import get_merchant_account
from app.tools.receivables import get_receivables
from app.tools.store import load_merchants
from app.tools.terminal import diagnose_terminal
from app.tools.web_search import FakeWebSearch
from fastapi.testclient import TestClient
from tests.conftest import offline_settings

HANDOFF = re.compile(r"^ESC-[A-Z0-9]{8}$")


def test_deposit_uses_only_the_request_user(client) -> None:
    response = client.post(
        "/v1/chat",
        json={"message": "When will the money from yesterday's sales be deposited?", "user_id": "cliente1988"},
    )
    body = response.json()
    assert body["tools_used"] == ["get_receivables"]
    assert "support" in body["route"]
    assert "next business day" in body["answer"]
    trace = client.get(f"/v1/traces/{body['trace_id']}").json()
    assert trace["user_id"] == "cliente1988"
    assert "1840" not in str(trace)
    assert "Comercio" not in str(trace)


def test_unknown_user_does_not_receive_the_fixture(client) -> None:
    response = client.post(
        "/v1/chat",
        json={"message": "When will the money from yesterday's sales be deposited?", "user_id": "cliente0001"},
    )
    body = response.json()
    assert "1840" not in body["answer"]
    assert "not found" in body["answer"].lower() or "no receivables" in body["answer"].lower()


def test_connectivity_and_decline_use_the_terminal_tool(client) -> None:
    offline = client.post(
        "/v1/chat",
        json={"message": "My card machine won't connect to the internet, what should I do?", "user_id": "cliente1988"},
    ).json()
    decline = client.post(
        "/v1/chat",
        json={"message": "My card machine is showing a transaction decline error.", "user_id": "cliente1988"},
    ).json()
    assert offline["tools_used"] == ["diagnose_terminal"]
    assert "Wi-Fi" in offline["answer"] or "4G" in offline["answer"]
    assert decline["tools_used"] == ["diagnose_terminal"]
    assert "decline" in decline["answer"].lower()


def test_tools_do_not_accept_an_id_other_than_the_argument() -> None:
    merchants = load_merchants(offline_settings().merchants_path)
    missing = get_receivables(merchants, "cliente999")
    assert missing["status"] == "not_found"
    assert "amount_brl" not in missing
    profile = get_merchant_account(merchants, "cliente999")
    assert profile["status"] == "not_found"
    terminal = diagnose_terminal(merchants, "cliente999", "decline")
    assert terminal["steps"] == []


def test_profile_question_uses_the_merchant_tool(client) -> None:
    response = client.post(
        "/v1/chat",
        json={"message": "What is my machine model and receiving setup?", "user_id": "cliente1988"},
    )
    body = response.json()
    assert body["tools_used"] == ["get_merchant_account"]
    assert "Get Smart" in body["answer"]
    assert "1840" not in body["answer"]


def test_human_request_returns_a_handoff_reference(client) -> None:
    response = client.post(
        "/v1/chat",
        json={"message": "I want to talk to a human", "user_id": "cliente1988"},
    )
    body = response.json()
    assert "escalation" in body["route"]
    assert body["handoff"]["reason"] == "human_requested"
    assert HANDOFF.match(body["handoff"]["reference"])
    trace = client.get(f"/v1/traces/{body['trace_id']}").json()
    assert trace["outcome"] == "handoff"


def test_fake_llm_intent_overrides_the_keyword_table() -> None:
    application = create_app(
        settings=offline_settings(),
        llm=FakeLLM(intent="product_knowledge"),
        web_search=FakeWebSearch(),
    )
    client = TestClient(application)
    response = client.post("/v1/chat", json={"message": "hello there", "user_id": "cliente1988"})
    body = response.json()
    assert "knowledge" in body["route"]
    assert "support" not in body["route"]
