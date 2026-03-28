from fastapi.testclient import TestClient


def test_users_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


def test_dev_login_sets_cookie_and_returns_current_user(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "parv@example.com",
            "full_name": "Parv",
        },
    )

    assert login_response.status_code == 200
    assert "donna_session=" in login_response.headers["set-cookie"]
    assert login_response.json()["user"]["email"] == "parv@example.com"

    me_response = client.get("/api/v1/users/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "parv@example.com"


def test_logout_clears_session_cookie(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "parv@example.com",
            "full_name": "Parv",
        },
    )

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204
    assert "Max-Age=0" in logout_response.headers["set-cookie"]
