"""Tests for admin authentication endpoints."""


class TestAuthentication:
    def test_handshake(self, admin_session):
        resp = admin_session.get("/api/handshake")
        data = resp.get_json()
        assert data["status"] is True

    def test_authenticate_valid(self, client):
        resp = client.post("/api/authenticate", json={
            "username": "admin",
            "password": "admin",
            "totp": ""
        })
        data = resp.get_json()
        assert data["status"] is True
        assert "authToken" in resp.headers.get("Set-Cookie", "")

    def test_authenticate_wrong_password(self, client):
        resp = client.post("/api/authenticate", json={
            "username": "admin",
            "password": "wrongpassword",
            "totp": ""
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_authenticate_wrong_username(self, client):
        resp = client.post("/api/authenticate", json={
            "username": "notadmin",
            "password": "admin",
            "totp": ""
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_validate_auth_without_session(self, client):
        resp = client.get("/api/validateAuthentication")
        data = resp.get_json()
        assert data["status"] is False

    def test_validate_auth_with_session(self, admin_session):
        resp = admin_session.get("/api/validateAuthentication")
        data = resp.get_json()
        assert data["status"] is True

    def test_signout(self, admin_session):
        resp = admin_session.get("/api/signout")
        data = resp.get_json()
        assert data["status"] is True
        # After signout, validation should fail
        resp2 = admin_session.get("/api/validateAuthentication")
        data2 = resp2.get_json()
        assert data2["status"] is False

    def test_protected_endpoint_without_auth(self, client):
        resp = client.get("/api/getWireguardConfigurations")
        data = resp.get_json()
        assert data["status"] is False
        assert "Unauthorized" in data.get("message", "")
