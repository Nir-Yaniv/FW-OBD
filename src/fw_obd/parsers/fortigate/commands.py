"""FortiGate CLI commands used for config reading.

Each constant is a ready-to-send CLI string.
The READ_SEQUENCE defines the order commands are run on first connect.
"""

# System information
GET_SYSTEM_STATUS = "get system status"
GET_SYSTEM_PERFORMANCE = "get system performance status"
GET_LICENSE_INFO = "get system license status"
GET_HA_STATUS = "get system ha status"

# Interfaces and network
SHOW_SYSTEM_INTERFACE = "show system interface"
SHOW_ROUTER_STATIC = "show router static"
SHOW_ROUTER_INFO_ROUTING = "get router info routing-table all"

# Firewall policies
SHOW_FIREWALL_POLICY = "show firewall policy"
SHOW_FIREWALL_POLICY_HITCOUNT = "get firewall policy"

# VPN
SHOW_VPN_IPSEC_PHASE1 = "show vpn ipsec phase1-interface"
SHOW_VPN_IPSEC_PHASE2 = "show vpn ipsec phase2-interface"
GET_VPN_IPSEC_TUNNEL_STATUS = "get vpn ipsec tunnel summary"

# VDOM management
SHOW_SYSTEM_VDOM = "show system vdom"

# Admin and security settings
SHOW_SYSTEM_ADMIN = "show system admin"
SHOW_SYSTEM_GLOBAL = "show system global"
GET_LOG_SETTING = "show log setting"

# Full config backup (used for backup/rollback)
SHOW_FULL_CONFIG = "show full-configuration"

# Commands run in order on first connection
READ_SEQUENCE = [
    GET_SYSTEM_STATUS,
    GET_SYSTEM_PERFORMANCE,
    GET_LICENSE_INFO,
    SHOW_SYSTEM_VDOM,
    SHOW_SYSTEM_INTERFACE,
    SHOW_ROUTER_STATIC,
    SHOW_FIREWALL_POLICY,
    SHOW_VPN_IPSEC_PHASE1,
    SHOW_VPN_IPSEC_PHASE2,
    GET_VPN_IPSEC_TUNNEL_STATUS,
    SHOW_SYSTEM_ADMIN,
    SHOW_SYSTEM_GLOBAL,
    GET_LOG_SETTING,
]

# Quick audit commands — minimal set for fast first scan
AUDIT_SEQUENCE = [
    GET_SYSTEM_STATUS,
    GET_SYSTEM_PERFORMANCE,
    GET_LICENSE_INFO,
    SHOW_SYSTEM_ADMIN,
    SHOW_SYSTEM_GLOBAL,
    SHOW_FIREWALL_POLICY,
    GET_LOG_SETTING,
]
