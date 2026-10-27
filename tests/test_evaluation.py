def test_briefing_scenarios_match_specialist_and_tool(client, scenarios) -> None:
    assert len(scenarios) == 10
    for scenario in scenarios:
        response = client.post(
            "/v1/chat",
            json={"message": scenario["message"], "user_id": scenario["user_id"]},
        )
        assert response.status_code == 200, scenario["id"]
        body = response.json()
        trace = client.get(f"/v1/traces/{body['trace_id']}").json()
        assert trace["intent"] == scenario["intent"], scenario["id"]
        assert scenario["route_contains"] in body["route"], scenario["id"]
        for tool in scenario["tools_contain"]:
            assert tool in body["tools_used"], scenario["id"]
        if scenario["sources_required"]:
            assert body["sources"], scenario["id"]
            assert all("getnet" in source["url"] for source in body["sources"])
        else:
            assert body["sources"] == [], scenario["id"]


def test_general_questions_do_not_cite_getnet(client, scenarios) -> None:
    general = [item for item in scenarios if item["intent"] == "general_web"]
    assert len(general) == 2
    for scenario in general:
        body = client.post(
            "/v1/chat",
            json={"message": scenario["message"], "user_id": scenario["user_id"]},
        ).json()
        assert body["sources"] == []
        assert "web_search" in body["tools_used"]
        assert "getnet.net" not in body["answer"].lower()
        assert "site.getnet" not in body["answer"].lower()
