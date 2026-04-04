"""Tests for admin client management endpoints."""


class TestClientManagement:
    def test_get_all_clients_empty(self, admin_session):
        resp = admin_session.get("/api/clients/allClients")
        data = resp.get_json()
        assert data["status"] is True
        assert isinstance(data["data"], dict)

    def test_client_signup_via_portal(self, client):
        resp = client.post("/client/api/signup", json={
            "Email": "newclient@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        data = resp.get_json()
        assert data["status"] is True

    def test_client_signup_duplicate(self, client):
        # First signup
        client.post("/client/api/signup", json={
            "Email": "dup@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        # Second signup — should fail
        resp = client.post("/client/api/signup", json={
            "Email": "dup@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_client_appears_in_admin_list(self, admin_session):
        # Create a client first
        admin_session.post("/client/api/signup", json={
            "Email": "listed@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        resp = admin_session.get("/api/clients/allClientsRaw")
        data = resp.get_json()
        assert data["status"] is True
        emails = [c["Email"] for c in data["data"]]
        assert "listed@example.com" in emails

    def test_update_client_profile_name(self, admin_session):
        # Create client
        admin_session.post("/client/api/signup", json={
            "Email": "profile@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        # Find the client
        resp = admin_session.get("/api/clients/allClientsRaw")
        clients = resp.get_json()["data"]
        target = next(c for c in clients if c["Email"] == "profile@example.com")

        # Update name
        resp = admin_session.post("/api/clients/updateProfileName", json={
            "ClientID": target["ClientID"],
            "Name": "Test User"
        })
        data = resp.get_json()
        assert data["status"] is True

    def test_delete_client(self, admin_session):
        # Create
        admin_session.post("/client/api/signup", json={
            "Email": "todelete@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        resp = admin_session.get("/api/clients/allClientsRaw")
        clients = resp.get_json()["data"]
        target = next(c for c in clients if c["Email"] == "todelete@example.com")

        # Delete
        resp = admin_session.post("/api/clients/deleteClient", json={
            "ClientID": target["ClientID"]
        })
        data = resp.get_json()
        assert data["status"] is True

    def test_delete_nonexistent_client(self, admin_session):
        resp = admin_session.post("/api/clients/deleteClient", json={
            "ClientID": "nonexistent-id-12345"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_client_signin_wrong_password(self, client):
        client.post("/client/api/signup", json={
            "Email": "wrongpw@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        resp = client.post("/client/api/signin", json={
            "Email": "wrongpw@example.com",
            "Password": "WrongPassword"
        })
        data = resp.get_json()
        assert data["status"] is False
