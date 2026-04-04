"""Tests for configuration access management (admin API + model)."""
import pytest


class TestConfigAccessModel:
    """Unit tests for DashboardClientConfigAccess directly."""

    def test_grant_access(self, app):
        import dashboard
        dc = dashboard.DashboardClients

        # Create a client
        dc.SignUp(Email="model_grant@example.com",
                  Password="StrongP@ss1", ConfirmPassword="StrongP@ss1")
        clients = dc.GetAllClientsRaw()
        client = next(c for c in clients if c["Email"] == "model_grant@example.com")
        cid = client["ClientID"]

        # Since no WG configs exist in test, grant should fail
        status, result = dc.GrantConfigAccess(cid, "nonexistent_config")
        assert status is False

    def test_has_access_false(self, app):
        import dashboard
        dc = dashboard.DashboardClients
        assert dc.HasConfigAccess("fake-id", "fake-config", "viewer") is False

    def test_get_managed_configs_empty(self, app):
        import dashboard
        dc = dashboard.DashboardClients
        result = dc.GetClientManagedConfigurations("fake-id")
        assert result == []

    def test_get_config_access_empty(self, app):
        import dashboard
        dc = dashboard.DashboardClients
        result = dc.GetClientConfigAccess("fake-id")
        assert result == []


class TestConfigAccessAPI:
    """Integration tests for config access admin API endpoints."""

    def _create_client(self, admin_session, email):
        admin_session.post("/client/api/signup", json={
            "Email": email,
            "Password": "StrongP@ss1",
            "ConfirmPassword": "StrongP@ss1"
        })
        resp = admin_session.get("/api/clients/allClientsRaw")
        clients = resp.get_json()["data"]
        return next(c for c in clients if c["Email"] == email)

    def test_grant_access_missing_fields(self, admin_session):
        resp = admin_session.post("/api/clients/grantConfigAccess", json={
            "ClientID": ""
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_grant_access_nonexistent_client(self, admin_session):
        resp = admin_session.post("/api/clients/grantConfigAccess", json={
            "ClientID": "nonexistent-id",
            "ConfigurationName": "wg0"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_grant_access_nonexistent_config(self, admin_session):
        client = self._create_client(admin_session, "grant_noconf@example.com")
        resp = admin_session.post("/api/clients/grantConfigAccess", json={
            "ClientID": client["ClientID"],
            "ConfigurationName": "nonexistent_config"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_get_config_access_api(self, admin_session):
        client = self._create_client(admin_session, "getaccess@example.com")
        resp = admin_session.get(
            f"/api/clients/getConfigAccess?ClientID={client['ClientID']}")
        data = resp.get_json()
        assert data["status"] is True
        assert isinstance(data["data"], list)

    def test_get_config_access_missing_client(self, admin_session):
        resp = admin_session.get("/api/clients/getConfigAccess")
        data = resp.get_json()
        assert data["status"] is False

    def test_revoke_nonexistent_access(self, admin_session):
        resp = admin_session.post("/api/clients/revokeConfigAccess", json={
            "AccessID": "nonexistent-access-id"
        })
        data = resp.get_json()
        assert data["status"] is False

    def test_revoke_missing_access_id(self, admin_session):
        resp = admin_session.post("/api/clients/revokeConfigAccess", json={})
        data = resp.get_json()
        assert data["status"] is False
