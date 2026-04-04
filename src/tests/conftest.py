"""
Test fixtures for WGDashboard.

Sets up an isolated environment so dashboard.py can initialize without
real WireGuard interfaces, using a temporary directory for config/DB.
"""
import os
import sys
import shutil
import tempfile
import subprocess

import bcrypt
import pytest

# Deterministic WG keys for tests
FAKE_PRIVATE_KEY = "cFak3Pr1vat3K3y0000000000000000000000000000="
FAKE_PUBLIC_KEY = "cFak3Publ1cK3y00000000000000000000000000000="

# Store original values for cleanup
_original_cwd = os.getcwd()
_original_check_output = subprocess.check_output


def _safe_check_output(*args, **kwargs):
    """Intercept subprocess calls to prevent real wg/wg-quick execution."""
    cmd = args[0] if args else kwargs.get("args", "")
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    if "wg " in cmd_str or "wg-quick" in cmd_str or "awg" in cmd_str:
        if "genkey" in cmd_str:
            return (FAKE_PRIVATE_KEY + "\n").encode()
        if "pubkey" in cmd_str:
            return (FAKE_PUBLIC_KEY + "\n").encode()
        if "show" in cmd_str:
            return b"\n"
        if "set" in cmd_str or "up" in cmd_str or "down" in cmd_str:
            return b""
        return b""
    return _original_check_output(*args, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Create isolated environment before dashboard.py is imported."""
    tmpdir = tempfile.mkdtemp(prefix="wgdtest_")

    # Create directories expected by the app
    wg_path = os.path.join(tmpdir, "wg")
    awg_path = os.path.join(tmpdir, "awg")
    db_path = os.path.join(tmpdir, "db")
    log_path = os.path.join(tmpdir, "log")
    os.makedirs(wg_path, exist_ok=True)
    os.makedirs(awg_path, exist_ok=True)
    os.makedirs(db_path, exist_ok=True)
    os.makedirs(log_path, exist_ok=True)

    # Pre-hash the admin password
    hashed_pw = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()

    ini_content = f"""[Account]
username = admin
password = {hashed_pw}
enable_totp = false
totp_verified = false
totp_key = JBSWY3DPEHPK3PXP

[Server]
wg_conf_path = {wg_path}
awg_conf_path = {awg_path}
app_prefix =
app_ip = 0.0.0.0
app_port = 10086
auth_req = true
version = v4.3.2
dashboard_refresh_interval = 60000
dashboard_peer_list_display = grid
dashboard_sort = status
dashboard_theme = dark
dashboard_api_key = false
dashboard_language = en-US

[Peers]
peer_global_DNS = 1.1.1.1
peer_endpoint_allowed_ip = 0.0.0.0/0
peer_display_mode = grid
remote_endpoint = 127.0.0.1
peer_MTU = 1420
peer_keep_alive = 21

[Other]
welcome_session = false

[Database]
type = sqlite
host =
port =
username =
password =

[Email]
server =
port =
encryption =
username =
email_password =
authentication_required = true
send_from =
email_template =

[OIDC]
admin_enable = false
client_enable = false

[Clients]
enable = true

[WireGuardConfiguration]
autostart =
"""
    with open(os.path.join(tmpdir, "wg-dashboard.ini"), "w") as f:
        f.write(ini_content)

    # Set environment variable for DashboardConfig
    os.environ["CONFIGURATION_PATH"] = tmpdir

    # Patch subprocess BEFORE any imports
    subprocess.check_output = _safe_check_output

    # Patch GetRemoteEndpoint before DashboardConfig default reads it
    src_dir = os.path.join(os.path.dirname(__file__), "..")
    sys.path.insert(0, src_dir)
    import modules.Utilities as util_module
    util_module.GetRemoteEndpoint = lambda: "127.0.0.1"

    # Change to temp dir so ConnectionString reads our wg-dashboard.ini
    os.chdir(tmpdir)

    # Symlink static dir so Locale and templates can find their files
    real_static = os.path.join(src_dir, "static")
    static_link = os.path.join(tmpdir, "static")
    if os.path.isdir(real_static) and not os.path.exists(static_link):
        os.symlink(real_static, static_link)
    # Symlink templates dir if needed
    real_templates = os.path.join(src_dir, "templates")
    templates_link = os.path.join(tmpdir, "templates")
    if os.path.isdir(real_templates) and not os.path.exists(templates_link):
        os.symlink(real_templates, templates_link)

    yield tmpdir

    # Cleanup
    os.chdir(_original_cwd)
    subprocess.check_output = _original_check_output
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def app(test_environment):
    """Import and return the Flask app configured for testing."""
    import dashboard

    dashboard.app.config["TESTING"] = True
    return dashboard.app


@pytest.fixture(scope="function")
def client(app):
    """Flask test client."""
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="function")
def admin_session(client):
    """Authenticated admin session. Returns the test client with session set."""
    resp = client.post("/api/authenticate", json={
        "username": "admin",
        "password": "admin",
        "totp": ""
    })
    assert resp.get_json()["status"] is True
    return client


@pytest.fixture(scope="function")
def client_user(admin_session):
    """Create a test client user and return its info."""
    from modules.DashboardClients import DashboardClients as DashboardClientsClass
    import dashboard

    # Create user directly via the DashboardClients instance
    dc = dashboard.DashboardClients
    status, msg = dc.SignUp(
        Email="test@example.com",
        Password="TestPass123!",
        ConfirmPassword="TestPass123!"
    )
    return {
        "email": "test@example.com",
        "password": "TestPass123!",
    }


@pytest.fixture(scope="function")
def client_session(client, client_user):
    """Authenticated client session. Returns (test_client, client_info)."""
    # Sign in
    resp = client.post("/client/api/signin", json={
        "Email": client_user["email"],
        "Password": client_user["password"],
    })
    data = resp.get_json()
    if not data["status"]:
        pytest.skip(f"Client signin failed: {data.get('message')}")

    # For TOTP — since we created user without TOTP, simulate verified session
    with client.session_transaction() as sess:
        sess["TotpVerified"] = True
        sess["Role"] = "client"

    return client, client_user
