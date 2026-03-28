from fastapi.testclient import TestClient


def test_create_and_get_user(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/users",
        json={
            "email": "parv@example.com",
            "full_name": "Parv",
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["email"] == "parv@example.com"
    assert created["full_name"] == "Parv"

    get_response = client.get(f"/api/v1/users/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["email"] == "parv@example.com"


def test_list_users_returns_created_user(client: TestClient) -> None:
    client.post(
        "/api/v1/users",
        json={
            "email": "parv@example.com",
            "full_name": "Parv",
            "is_active": True,
        },
    )

    response = client.get("/api/v1/users")

    assert response.status_code == 200
    emails = [user["email"] for user in response.json()]
    assert "parv@example.com" in emails
