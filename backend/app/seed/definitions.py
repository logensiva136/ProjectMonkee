"""Reference data seeded into every instance: permissions, roles, panels.

This is code, not database content an operator edits. A permission only means
something if an endpoint declares it, and a panel only means something if the
frontend has a route for it — so both are defined next to the code that uses
them and applied idempotently on every boot.

Adding a screen in a later phase means adding a `PanelDef` here and granting it
to the roles that should see it. Adding an endpoint that mutates state means
adding a `PermissionDef` and referencing it with `Depends(require(...))`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionDef:
    key: str
    resource: str
    action: str
    description: str


@dataclass(frozen=True)
class PanelDef:
    key: str
    name: str
    route: str
    icon: str
    nav_group: str
    sort_order: int


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    description: str
    #: Permission keys. "*" grants every permission, re-evaluated on each sync so
    #: permissions added in a later phase attach automatically.
    permissions: list[str]
    #: Panel keys this role can see. "*" means every panel.
    panels: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Permissions (SPEC §6.3)
# --------------------------------------------------------------------------- #

PERMISSIONS: list[PermissionDef] = [
    # --- collection ---
    PermissionDef("source:read", "source", "read", "View intel sources and their run history"),
    PermissionDef("source:write", "source", "write", "Add, edit, disable and poll sources"),
    PermissionDef("signal:read", "signal", "read", "Search and read collected items"),
    PermissionDef("signal:write", "signal", "write", "Tag and annotate collected items"),
    # --- vulnerability ---
    PermissionDef("cve:read", "cve", "read", "Browse CVEs and watchlist hits"),
    PermissionDef("cve:write", "cve", "write", "Create and edit CVE watchlists"),
    # --- third-party risk ---
    PermissionDef("vendor:read", "vendor", "read", "View the vendor register and matches"),
    PermissionDef("vendor:write", "vendor", "write", "Add and edit vendors, keywords and domains"),
    # --- tech stack ---
    PermissionDef("component:read", "component", "read", "View the technology inventory"),
    PermissionDef("component:write", "component", "write", "Add and edit tracked components"),
    # --- attack surface ---
    PermissionDef("easm:read", "easm", "read", "View assets, changes and scan history"),
    PermissionDef("easm:write", "easm", "write", "Add and edit scopes and assets"),
    PermissionDef("easm:scan", "easm", "scan", "Start active scans against authorized scopes"),
    PermissionDef(
        "easm:approve_scope",
        "easm",
        "approve_scope",
        "Authorize a scope for active scanning — the legal gate on probing",
    ),
    # --- detection ---
    PermissionDef("rule:read", "rule", "read", "View detection rules"),
    PermissionDef("rule:write", "rule", "write", "Create, edit and enable rules"),
    PermissionDef("alert:read", "alert", "read", "View alerts"),
    PermissionDef("alert:acknowledge", "alert", "acknowledge", "Acknowledge and resolve alerts"),
    # --- delivery ---
    PermissionDef("telegram:read", "telegram", "read", "View bots, destinations and deliveries"),
    PermissionDef("telegram:write", "telegram", "write", "Configure bots and destinations"),
    PermissionDef("template:write", "template", "write", "Edit message templates"),
    # --- administration ---
    PermissionDef("user:manage", "user", "manage", "Create, edit, lock and unlock users"),
    PermissionDef("role:manage", "role", "manage", "Create roles and assign permissions"),
    PermissionDef("settings:manage", "settings", "manage", "Change instance settings"),
    PermissionDef("audit:read", "audit", "read", "Read the audit log"),
]


# --------------------------------------------------------------------------- #
# Panels (SPEC §5.1) — only screens that actually exist
# --------------------------------------------------------------------------- #
#
# A panel row puts a link in the sidebar. Seeding one for a screen that has not
# been built yet produces a link to a 404, so panels are added phase by phase
# alongside their routes.

PANELS: list[PanelDef] = [
    PanelDef("dashboard", "Dashboard", "/", "layout-dashboard", "Overview", 10),
    PanelDef("admin_users", "Users", "/admin/users", "users", "Administration", 900),
    PanelDef("admin_roles", "Roles", "/admin/roles", "shield-check", "Administration", 910),
    PanelDef("admin_settings", "Settings", "/admin/settings", "settings", "Administration", 920),
    PanelDef("admin_audit", "Audit log", "/admin/audit", "scroll-text", "Administration", 930),
]


# --------------------------------------------------------------------------- #
# Roles (SPEC §6.3)
# --------------------------------------------------------------------------- #

_READ_PERMISSIONS = [
    "source:read",
    "signal:read",
    "cve:read",
    "vendor:read",
    "component:read",
    "easm:read",
    "rule:read",
    "alert:read",
    "telegram:read",
]

ROLES: list[RoleDef] = [
    RoleDef(
        key="super_admin",
        name="Super Admin",
        description="Full access to every capability and every screen.",
        permissions=["*"],
        panels=["*"],
    ),
    RoleDef(
        key="security_analyst",
        name="Security Analyst",
        description=(
            "Reads everything, acknowledges alerts, and manages watchlists and rules. "
            "Cannot administer users or authorize active scanning."
        ),
        permissions=[
            *_READ_PERMISSIONS,
            "signal:write",
            "cve:write",
            "rule:write",
            "alert:acknowledge",
        ],
        panels=["dashboard"],
    ),
    RoleDef(
        key="tprm_officer",
        name="TPRM Officer",
        description=(
            "Manages the vendor register and works alerts. "
            "Explicitly excluded from EASM scanning (SPEC §6.3)."
        ),
        permissions=[
            "source:read",
            "signal:read",
            "cve:read",
            "vendor:read",
            "vendor:write",
            "alert:read",
            "alert:acknowledge",
        ],
        panels=["dashboard"],
    ),
    RoleDef(
        key="viewer",
        name="Viewer",
        description="Read-only access to dashboards. Cannot change anything.",
        # Deliberately narrow: SPEC §6.3 says "read-only, dashboards only".
        permissions=["alert:read", "signal:read"],
        panels=["dashboard"],
    ),
]

#: The role the first operator receives during onboarding (SPEC §6.1 step 5).
BOOTSTRAP_ROLE_KEY = "super_admin"
