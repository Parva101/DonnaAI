def test_action_plan_and_execute_with_approval(client):
    target_scope = {
        "tenant_id": "tenant-a",
        "platform": "whatsapp",
        "account_id": "default",
        "chat_key": "chat-beta",
        "read_allowed": False,
        "write_allowed": True,
        "relay_allowed": False,
        "updated_by": "test",
    }
    scope_resp = client.put("/v1/permissions/scopes", json=target_scope)
    assert scope_resp.status_code == 200

    plan_payload = {
        "tenant_id": "tenant-a",
        "intent": "Send summary to chat-beta",
        "source_platform": "whatsapp",
        "source_chat_key": "chat-alpha",
        "target_platform": "whatsapp",
        "target_chat_key": "chat-beta",
    }
    planned = client.post("/v1/actions/plan", json=plan_payload)
    assert planned.status_code == 200
    action_id = planned.json()["action_id"]
    assert planned.json()["requires_approval"] is True

    no_approval_execute = {
        "tenant_id": "tenant-a",
        "action_id": action_id,
        "idempotency_key": "exec-key-1",
    }
    blocked = client.post("/v1/actions/execute", json=no_approval_execute)
    assert blocked.status_code == 400

    approved_execute = {
        "tenant_id": "tenant-a",
        "action_id": action_id,
        "idempotency_key": "exec-key-2",
        "approval_token": "approved-by-user",
    }
    executed = client.post("/v1/actions/execute", json=approved_execute)
    assert executed.status_code == 200
    assert executed.json()["status"] == "executed"

    action_state = client.get(f"/v1/actions/{action_id}", params={"tenant_id": "tenant-a"})
    assert action_state.status_code == 200
    assert action_state.json()["status"] == "executed"

