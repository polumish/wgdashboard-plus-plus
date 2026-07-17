"""Unit tests for modules.PeerDefaults — mode-aware default AllowedIPs for new
peers. Regression guard for the client-portal bug where managed peers were
created with endpoint_allowed_ip = 0.0.0.0/0 (full tunnel) on mesh configs."""
import types

from modules.PeerDefaults import (
    mesh_config_subnet,
    default_endpoint_allowed_ip,
    resolve_endpoint_allowed_ip,
)

GLOBAL_DEFAULT = "0.0.0.0/0"


def _wc(address, mode="mesh", routed=""):
    info = types.SimpleNamespace(NetworkMode=mode, RoutedLANSubnets=routed)
    return types.SimpleNamespace(Address=address, configurationInfo=info)


def test_mesh_config_subnet_extracts_network():
    assert mesh_config_subnet("10.200.3.4/24") == "10.200.3.0/24"


def test_mesh_config_subnet_none_when_unparseable():
    assert mesh_config_subnet("not-an-ip") is None


def test_mesh_default_is_config_subnet():
    wc = _wc("10.200.3.0/24", mode="mesh")
    assert default_endpoint_allowed_ip(wc, GLOBAL_DEFAULT) == "10.200.3.0/24"


def test_mesh_requested_full_tunnel_is_reset_to_subnet():
    """THE BUG: a request for 0.0.0.0/0 on a mesh config must NOT be honored."""
    wc = _wc("10.200.3.0/24", mode="mesh")
    assert resolve_endpoint_allowed_ip(wc, GLOBAL_DEFAULT, "0.0.0.0/0") == "10.200.3.0/24"


def test_mesh_requested_none_falls_back_to_subnet():
    wc = _wc("10.200.3.0/24", mode="mesh")
    assert resolve_endpoint_allowed_ip(wc, GLOBAL_DEFAULT, None) == "10.200.3.0/24"


def test_mesh_explicit_valid_request_is_respected():
    wc = _wc("10.200.3.0/24", mode="mesh")
    assert resolve_endpoint_allowed_ip(wc, GLOBAL_DEFAULT, "10.0.50.0/24") == "10.0.50.0/24"


def test_gateway_mode_default_is_full_tunnel():
    wc = _wc("10.200.7.1/24", mode="gateway")
    assert default_endpoint_allowed_ip(wc, GLOBAL_DEFAULT) == "0.0.0.0/0"


def test_gateway_mode_full_tunnel_request_is_kept():
    wc = _wc("10.200.7.1/24", mode="gateway")
    assert resolve_endpoint_allowed_ip(wc, GLOBAL_DEFAULT, "0.0.0.0/0") == "0.0.0.0/0"


def test_point_to_site_default_is_server_slash32():
    wc = _wc("10.200.4.9/24", mode="point-to-site")
    assert default_endpoint_allowed_ip(wc, GLOBAL_DEFAULT) == "10.200.4.9/32"


def test_point_to_site_includes_routed_lan_subnets():
    wc = _wc("10.200.4.9/24", mode="point-to-site", routed="10.0.50.159/32")
    assert default_endpoint_allowed_ip(wc, GLOBAL_DEFAULT) == "10.200.4.9/32, 10.0.50.159/32"


def test_mesh_unparseable_address_falls_back_to_global_default():
    wc = _wc("", mode="mesh")
    assert resolve_endpoint_allowed_ip(wc, GLOBAL_DEFAULT, None) == GLOBAL_DEFAULT
