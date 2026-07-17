"""Mode-aware default AllowedIPs (endpoint_allowed_ip) for new WireGuard peers.

Single source of truth shared by the admin add-peer path (dashboard.py) and the
client-portal managed add-peer path (client.py) so the two can never diverge
again — that divergence is what let managed peers be created with
endpoint_allowed_ip = 0.0.0.0/0 (full tunnel) on mesh configs.
"""
import ipaddress


def mesh_config_subnet(address):
    """Return the IPv4 network CIDR from a WG interface Address, or None."""
    for addr in (a.strip() for a in (address or "").split(",")):
        if not addr:
            continue
        try:
            iface = ipaddress.ip_interface(addr)
            if iface.version == 4:
                return str(iface.network)
        except ValueError:
            continue
    return None


def default_endpoint_allowed_ip(wc, global_default):
    """Compute the default AllowedIPs for a new peer from the config's
    NetworkMode (mesh / point-to-site / gateway)."""
    mode = getattr(wc.configurationInfo, "NetworkMode", "mesh")
    if mode == "gateway":
        return "0.0.0.0/0"
    if mode == "point-to-site":
        addr = (wc.Address or "").split(",")[0].strip()
        try:
            base = f"{ipaddress.ip_interface(addr).ip}/32"
        except (ValueError, Exception):
            base = addr
        routed = (getattr(wc.configurationInfo, "RoutedLANSubnets", "") or "").strip()
        return f"{base}, {routed}" if routed else base
    # mesh
    return mesh_config_subnet(wc.Address) or global_default


def resolve_endpoint_allowed_ip(wc, global_default, requested):
    """Resolve the endpoint_allowed_ip to persist for a new peer.

    Uses ``requested`` when provided, else the mode-aware default. A request for
    the bare full tunnel ``0.0.0.0/0`` on a non-gateway config is rejected and
    replaced with the mode-aware default — this is the regression guard.
    """
    default = default_endpoint_allowed_ip(wc, global_default)
    eaip = requested if requested is not None else default
    mode = getattr(wc.configurationInfo, "NetworkMode", "mesh")
    if eaip == "0.0.0.0/0" and mode != "gateway":
        eaip = default
    return eaip
