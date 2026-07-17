"""Tests for client portal endpoints."""
import pytest


class TestClientPortalAuth:
    def test_client_signup(self, client):
        resp = client.post("/client/api/signup", json={
            "Email": "portal_signup@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        data = resp.get_json()
        assert data["status"] is True

    def test_client_signup_weak_password(self, client):
        resp = client.post("/client/api/signup", json={
            "Email": "weakpw@example.com",
            "Password": "123",
            "ConfirmPassword": "123"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_client_signup_mismatch_password(self, client):
        resp = client.post("/client/api/signup", json={
            "Email": "mismatch@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "DifferentP@ss1"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_client_signin(self, client):
        # Create first
        client.post("/client/api/signup", json={
            "Email": "portal_signin@example.com",
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        resp = client.post("/client/api/signin", json={
            "Email": "portal_signin@example.com",
            "Password": "StrongP@ss1"
        })
        data = resp.get_json()
        assert data["status"] is True

    def test_client_validate_auth_unauthenticated(self, client):
        resp = client.get("/client/api/validateAuthentication")
        data = resp.get_json()
        assert data["status"] is False

    def test_client_signout(self, client):
        resp = client.get("/client/api/signout")
        data = resp.get_json()
        assert data["status"] is True


class TestClientPortalConfigurations:
    def _authenticated_client(self, client, email="managed@example.com"):
        """Create and authenticate a client user."""
        client.post("/client/api/signup", json={
            "Email": email,
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        client.post("/client/api/signin", json={
            "Email": email,
            "Password": "StrongP@ss1"
        })
        with client.session_transaction() as sess:
            sess["TotpVerified"] = True
            sess["Role"] = "client"
        return client

    def test_get_configurations(self, client):
        c = self._authenticated_client(client, "configs@example.com")
        resp = c.get("/client/api/configurations")
        data = resp.get_json()
        assert data["status"] is True
        assert isinstance(data["data"], (list, dict, type(None)))

    def test_managed_configurations_empty(self, client):
        c = self._authenticated_client(client, "nomanaged@example.com")
        resp = c.get("/client/api/managedConfigurations")
        data = resp.get_json()
        assert data["status"] is True
        assert data["data"] == []

    def test_managed_config_peers_no_access(self, client):
        c = self._authenticated_client(client, "noaccess@example.com")
        resp = c.get("/client/api/managedConfigurations/wg0/peers")
        data = resp.get_json()
        assert data["status"] is False

    def test_managed_config_add_peer_no_access(self, client):
        c = self._authenticated_client(client, "noaccess_add@example.com")
        resp = c.post("/client/api/managedConfigurations/wg0/addPeers",
                       json={"name": "test-peer"})
        data = resp.get_json()
        assert data["status"] is False

    def test_managed_config_delete_peers_no_access(self, client):
        c = self._authenticated_client(client, "noaccess_del@example.com")
        resp = c.post("/client/api/managedConfigurations/wg0/deletePeers",
                       json={"peers": ["fakeid"]})
        data = resp.get_json()
        assert data["status"] is False

    def test_managed_config_restrict_no_access(self, client):
        c = self._authenticated_client(client, "noaccess_rst@example.com")
        resp = c.post("/client/api/managedConfigurations/wg0/restrictPeers",
                       json={"peers": ["fakeid"]})
        data = resp.get_json()
        assert data["status"] is False

    def test_managed_config_allow_no_access(self, client):
        c = self._authenticated_client(client, "noaccess_alw@example.com")
        resp = c.post("/client/api/managedConfigurations/wg0/allowAccessPeers",
                       json={"peers": ["fakeid"]})
        data = resp.get_json()
        assert data["status"] is False

    def test_managed_config_download_no_access(self, client):
        c = self._authenticated_client(client, "noaccess_dl@example.com")
        resp = c.get("/client/api/managedConfigurations/wg0/downloadPeer?id=fakeid")
        data = resp.get_json()
        assert data["status"] is False


class TestManagedAddPeerAllowedIPs:
    """End-to-end regression: a peer added through the client portal on a mesh
    config must get the config subnet as AllowedIPs, never 0.0.0.0/0."""

    FAKE_KEY = "cFak3Pr1vat3K3y0000000000000000000000000000="

    def test_managed_add_peer_mesh_uses_config_subnet_not_full_tunnel(self, client):
        import dashboard

        # 1. Admin creates a mesh configuration (no NetworkMode -> mesh default).
        auth = client.post("/api/authenticate",
                           json={"username": "admin", "password": "admin", "totp": ""})
        assert auth.get_json()["status"] is True
        cfg_name = "regmesh"
        resp = client.post("/api/addWireguardConfiguration", json={
            "ConfigurationName": cfg_name,
            "Address": "10.123.0.1/24",
            "ListenPort": "51999",
            "PrivateKey": self.FAKE_KEY,
            "Protocol": "wg",
        })
        assert resp.get_json()["status"] is True, resp.get_json()

        # 2. Create a client user and grant it manager access to that config.
        dc = dashboard.DashboardClients
        dc.SignUp(Email="manager_add@example.com",
                  Password="StrongP@ss1", ConfirmPassword="StrongP@ss1")
        cid = next(c["ClientID"] for c in dc.GetAllClientsRaw()
                   if c["Email"] == "manager_add@example.com")
        granted, _ = dc.GrantConfigAccess(cid, cfg_name, "manager")
        assert granted is True

        # 3. Authenticate as that client (TOTP simulated, as other portal tests do).
        client.get("/api/signout")
        client.post("/client/api/signin",
                    json={"Email": "manager_add@example.com", "Password": "StrongP@ss1"})
        with client.session_transaction() as sess:
            sess["TotpVerified"] = True
            sess["Role"] = "client"
            sess["ClientID"] = cid

        # 4. Manager adds a peer sending only a name (the real portal payload).
        add = client.post(f"/client/api/managedConfigurations/{cfg_name}/addPeers",
                          json={"name": "regtest-peer"})
        assert add.get_json()["status"] is True, add.get_json()

        # 5. The stored endpoint_allowed_ip must be the config subnet, not 0.0.0.0/0.
        wc = dashboard.WireguardConfigurations[cfg_name]
        wc.getPeers()
        peer = next(p for p in wc.Peers if p.name == "regtest-peer")
        assert peer.endpoint_allowed_ip == "10.123.0.0/24"
        assert peer.endpoint_allowed_ip != "0.0.0.0/0"


class TestClientPortalSettings:
    def _authenticated_client(self, client, email="settings@example.com"):
        client.post("/client/api/signup", json={
            "Email": email,
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        client.post("/client/api/signin", json={
            "Email": email,
            "Password": "StrongP@ss1"
        })
        with client.session_transaction() as sess:
            sess["TotpVerified"] = True
            sess["Role"] = "client"
        return client

    def test_get_client_profile(self, client):
        c = self._authenticated_client(client, "profile_test@example.com")
        resp = c.get("/client/api/settings/getClientProfile")
        data = resp.get_json()
        assert "Email" in data.get("data", {})

    def test_server_information(self, client):
        resp = client.get("/client/api/serverInformation")
        data = resp.get_json()
        assert "ServerTimezone" in data.get("data", {})
