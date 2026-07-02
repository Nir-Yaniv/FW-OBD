# HIGH-LEVEL DESIGN v1.0
## Multi-Vendor Firewall Management & Diagnostics Platform
### "The OBD-II Scanner for Firewalls"

**Document Version:** 1.0  
**Author:** Nir  
**Date:** May 2026  
**Status:** Draft — Pending Review  

---

## TABLE OF CONTENTS

1. Executive Summary
2. System Architecture Overview
3. Core Layers & Components
   - 3.1 Connection Management
   - 3.2 Vendor-Specific Parsers
   - 3.3 Reverse Engineering Engine
   - 3.4 Universal Data Model
   - 3.5 Knowledge Base
   - 3.6 Recommendation Engine
   - 3.7 Change Planner
   - 3.8 First Connection Preset & Quick Audit
   - 3.9 Backup & Rollback Strategy
   - 3.10 Version Control & Audit Trail
   - 3.11 Device Import & Integration
   - 3.12 Security Requirements
   - 3.13 User Accounts & Licensing
   - 3.14 UI/UX Requirements
4. Workflow Examples
5. Data Flow Diagram
6. Technical Stack
7. Phase 1 Scope (MVP)
8. Future Roadmap
9. Monetization & Partnerships
10. Risks & Mitigation
11. Success Metrics
12. Conclusion

---

## 1. EXECUTIVE SUMMARY

### Product Vision
A desktop application that functions like an "OBD-II scanner for firewalls" — connecting to multi-vendor firewall environments, automatically reading and mapping configurations, translating complex technical output into plain-language, visual results accessible to non-specialists. The platform empowers IT and security teams managing heterogeneous firewall environments to configure, diagnose, and troubleshoot without requiring deep vendor-specific expertise.

### Target Users
- IT administrators and network engineers managing multiple firewall brands
- Security teams without specialized firewall expertise
- Organizations running mixed Fortinet, Palo Alto, Cisco, and Check Point environments
- MSPs managing firewalls across multiple customers
- Hospital and medical facility IT teams requiring HIPAA-compliant configurations

### Core Value Proposition
- **Multi-vendor accessibility** — one tool for all your firewalls, not vendor lock-in
- **Plain-language guidance** — conversational AI walks non-specialists through complex operations
- **Intelligent diagnostics** — scans for misconfigurations, vulnerabilities, and optimization opportunities
- **Git-style versioning** — every change tracked, auditable, and reversible
- **Accelerated operations** — reduces configuration time and human error
- **Compliance-aware** — built-in knowledge of HIPAA, PCI-DSS, ISO 27001 requirements

### Problem Addressed
Organizations managing multi-vendor firewalls today either:
1. Use single-vendor tools (FortiManager, Panorama) that don't talk to each other
2. Require specialist engineers to manage each brand separately
3. Lack visibility into configurations across their entire firewall estate
4. Have no intelligent guidance for non-specialists attempting complex operations
5. Cannot easily audit and rollback changes across different platforms
6. Have no plain-language interface — everything requires deep technical knowledge

### Market Differentiation
Existing tools like **Tufin** and **FireMon** are complex enterprise platforms focused on policy management — not accessible to non-specialists and not conversational. This platform is fundamentally different:

- **Existing tools:** "Here are your 5,000 policies. Good luck managing them."
- **This platform:** "Hi, I want to connect Tel Aviv to New York. I'll read your config, ask you a few questions, and guide you through the whole thing."

No existing product combines multi-vendor support + AI-powered conversational guidance + plain-language interface + Git-style versioning + accessible UX for non-specialists.

---

## 2. SYSTEM ARCHITECTURE OVERVIEW

The platform consists of **ten core subsystems** that work together to provide unified, intelligent firewall management:

**A. Desktop Agent**
Installed application (Windows, Mac, Linux) that runs locally on the user's network. Handles all connectivity, config reading, analysis, and change execution. Communicates with the native GUI. This is critical — it must run locally so it can reach firewalls on internal networks via SSH.

**B. Native GUI**
Desktop application window (not browser-based) built with PyQt or similar framework. Provides the user interface for device management, smart terminal, settings, and reporting. English language only in Phase 1.

**C. Dual Connection Bridge**
Manages both SSH and HTTPS connections to firewalls. Intelligently routes requests based on connection type. Notifies users of feature limitations when using HTTPS (e.g., "VDOM management is SSH-only. Please switch to SSH for full access.").

**D. Config Reader**
Executes vendor-specific CLI commands via SSH or reads configurations via HTTPS APIs. Collects raw firewall output in native vendor format.

**E. Reverse Engineer**
Parses raw configuration output and reconstructs the complete firewall hierarchy including root configs, VDOMs, sub-policies, routing tables, VPN tunnels, interfaces, and security profiles. Creates a unified internal representation.

**F. Universal Data Model (UDM)**
Standardized internal format representing any firewall config regardless of vendor. Common structure for interfaces, policies, VPNs, routes, VLANs, security settings, licensing, system health. Acts as the "Rosetta Stone" between vendor-specific formats and the rest of the system.

**G. Knowledge Base**
Repository of vendor documentation, best practices, security standards (HIPAA, PCI-DSS, medical encryption), compliance frameworks, and feature capabilities per model. Only uses official vendor sources — never third-party advice. Gets updated when vendor docs change.

**H. Recommendation Engine**
Analyzes current config, understands user intent from conversational input, and recommends optimal solutions based on knowledge base, best practices, and industry standards. Explains the "why" behind each recommendation. Sources linked back to official vendor documentation.

**I. Change Planner**
Generates step-by-step configuration changes, identifies downstream impacts (switch configuration, VLAN setup, physical network changes), and creates execution plans. Understands that a firewall change often requires network layer changes too.

**J. Documentation & Audit Engine**
Generates handoff reports for technicians, creates email audit trails or GitHub issues documenting every change, manages version history, and enables rollback.

---

## 3. CORE LAYERS & COMPONENTS

### 3.1 Connection Management

#### SSH Connection Handler
- Securely manages SSH authentication to firewalls
- Maintains persistent or on-demand SSH sessions
- Handles multiple concurrent connections
- Implements connection timeouts and auto-reconnect
- Supports key-based and password-based authentication
- Logs all SSH sessions for audit purposes

#### HTTPS/API Connection Handler
- Manages REST API or HTTPS GUI connections
- Handles SSL/TLS certificate validation
- Manages API authentication tokens and sessions
- Provides fallback and error handling for API limitations
- Notifies user when feature requires SSH instead of HTTPS

#### Connection Pool
- Reuses connections efficiently across multiple commands
- Manages session state across operations
- Implements heartbeat to keep connections alive
- Graceful reconnection if connection drops

#### Connection Security Notes
- All firewall credentials encrypted at rest (AES-256)
- Credentials never transmitted in plaintext
- SSH sessions logged and auditable
- HTTPS connections verified with SSL/TLS certificate validation

---

### 3.2 Vendor-Specific Parsers

Each vendor has a dedicated parser module. Parsers are modular — new vendors can be added without rewriting the core system.

#### FortiGate Parser (Phase 1 Focus)
Primary vendor for MVP. Commands executed via SSH:

```
get system status              — Device info, model, version, serial
get system performance status  — CPU, memory, uptime
get license info              — License status, expiration, features
config system interface        — Interface configurations
config firewall policy         — Security policies
config router static           — Static routing
config vpn ipsec phase1        — VPN Phase 1 tunnels
config vpn ipsec phase2        — VPN Phase 2 tunnels
config system admin            — Admin access settings
get log setting               — Logging configuration
config system vdom             — Virtual domain list
```

- Parses CLI output into structured format
- Understands VDOM hierarchy and **recursively reads all VDOMs**
- Extracts interface configs, routing policies, VPN tunnels, security profiles, system health
- Handles FortiOS version differences in output format

#### Palo Alto Parser (Phase 2)
- Executes Palo Alto CLI commands for device config retrieval
- Parses XML and text outputs
- Understands firewall hierarchy (vsys, zones, policies)
- Extracts security policies, NAT rules, VPN configs, App-ID settings

#### Cisco ASA/FTD Parser (Phase 2)
- Executes Cisco-specific commands
- Parses ACLs, NAT rules, VPN configurations
- Extracts interface and routing information
- Handles differences between ASA and FTD syntax

#### Check Point Parser (Phase 2)
- Executes Check Point CLI commands
- Parses policy configurations
- Extracts security rules, network objects, and gateway settings

---

### 3.3 Reverse Engineering Engine

#### Configuration Hierarchy Mapping
- Identifies whether config is centralized (root only) or distributed (VDOMs/vsys)
- **Recursively reads all sub-configurations** — doesn't stop at root
- Builds a complete tree structure of the firewall's organizational hierarchy
- Maps parent-child relationships between VDOMs, interfaces, and policies

#### Policy & Rule Extraction
- Extracts all security policies with: source, destination, action, logging settings, security profiles
- Identifies policy gaps (traffic that hits implicit deny)
- Identifies policy overlaps (redundant rules)
- Identifies unused policies (zero-hit rules)
- Maps policies to user/group assignments and security profiles

#### Network Topology Mapping
- Reads all interfaces and their configurations (IP, netmask, VLANs, MTU, admin status)
- Extracts routing tables (static and dynamic routes, BGP, OSPF)
- Identifies which interfaces connect to which networks and remote sites
- Builds a visual representation of connectivity
- Maps ISP connections, internal networks, DMZ zones

#### VPN & Remote Site Extraction
- Identifies all IPSec, SSL, or other VPN tunnels
- Extracts tunnel endpoints, encryption algorithms, key exchange methods, DH groups
- Maps remote sites and branch connectivity
- Identifies redundancy and backup tunnels
- Checks tunnel status (UP/DOWN/NEGOTIATING)

#### System Health & Licensing
- Reads license status, expiration dates, enabled features
- Extracts CPU, memory, and disk usage
- Identifies deprecated or unsupported features
- Notes available security updates or firmware versions
- Flags hardware-specific capabilities (e.g., FortiGate 90G has internal SSD for logging)

---

### 3.4 Universal Data Model (UDM)

The UDM is the central "Rosetta Stone" that allows the system to reason about any firewall, regardless of vendor. All vendor-specific data is normalized into this common structure.

```
Device
├── Metadata
│   ├── Vendor (Fortinet, Palo Alto, Cisco, Check Point)
│   ├── Model (FortiGate 90G, PA-220, ASA 5506-X, etc.)
│   ├── Software Version
│   ├── Serial Number
│   └── Uptime
├── Licensing
│   ├── Status (Active, Expired, Expiring Soon)
│   ├── Expiration Date
│   └── Enabled Features
├── System Health
│   ├── CPU Usage (%)
│   ├── Memory Usage (%)
│   ├── Disk Usage (%)
│   └── Temperature (if available)
├── Interfaces [ ]
├── VLANs [ ]
├── Routing Tables [ ]
├── Security Policies [ ]
├── VPN Tunnels [ ]
├── Virtual Domains [ ]
├── User/Group Mappings [ ]
└── Security Profiles [ ]

Interface
├── Name (port1, ge-0/0/0, GigabitEthernet1, etc.)
├── IP Address & Netmask
├── Physical or Logical Type
├── VLAN Assignment
├── Description/Alias
├── Administrative Status (UP/DOWN)
└── MTU

SecurityPolicy
├── Policy ID
├── Name
├── Source Zone/Interface
├── Source Network(s)
├── Destination Zone/Interface
├── Destination Network(s)
├── Action (Allow, Deny, Drop)
├── Services/Applications
├── Logging Status (enabled/disabled)
├── NAT Configuration
├── Security Profile Attachments (AV, IPS, URL filter, etc.)
├── Schedule
└── Hit Count

VPNTunnel
├── Name
├── Type (IPSec Site-to-Site, IPSec Remote Access, SSL)
├── Local Gateway IP
├── Remote Gateway IP
├── Encryption Algorithm (AES-128, AES-256, 3DES)
├── Authentication (SHA1, SHA256, SHA512)
├── DH Group
├── IKE Version (v1, v2)
├── Status (UP, DOWN, NEGOTIATING)
├── Local Networks [ ]
└── Remote Networks [ ]

VirtualDomain (VDOM/vsys)
├── Name
├── Type (root, non-root)
├── Assigned Interfaces [ ]
├── Security Policies [ ]
├── Routing Tables [ ]
└── VPN Tunnels [ ]
```

---

### 3.5 Knowledge Base

#### Data Sources
The Knowledge Base is built exclusively from **official vendor sources**:

- Official Fortinet FortiGate CLI Reference Manuals
- Fortinet Security Best Practices Guides
- Palo Alto Networks Administration Guides
- Cisco ASA/FTD Configuration Guides
- Check Point Security Management Documentation
- Compliance frameworks: HIPAA, PCI-DSS, ISO 27001, CIS Benchmarks

> **Policy:** Only trusted, official sources are used. The system tells users exactly which document a recommendation comes from, e.g., "This recommendation comes from the Fortinet Security Best Practices Guide (2024)."

#### Knowledge Base Structure

```
VendorKnowledge
├── Device Models
│   ├── FortiGate 60 / 60F
│   │   ├── Hardware: CPU, RAM, no internal SSD
│   │   ├── Max throughput specs
│   │   ├── Supported features
│   │   └── Limitations
│   ├── FortiGate 90 / 90G
│   │   ├── Hardware: CPU, RAM, internal SSD (enables logging, caching)
│   │   ├── Max throughput specs
│   │   ├── Supported features
│   │   └── Limitations
│   └── [All other models...]
├── CLI Commands
│   ├── Command Name
│   ├── Syntax
│   ├── Parameters
│   ├── Expected Output Format
│   └── Use Case
├── Best Practices
│   ├── Security Hardening (admin access, logging, unused features)
│   ├── Performance Optimization
│   ├── High Availability Setup
│   ├── VPN Configuration Standards
│   └── Disaster Recovery
├── Compliance Mappings
│   ├── HIPAA
│   │   ├── Required encryption: AES-256
│   │   ├── Required logging: all access events
│   │   └── Required audit controls
│   ├── PCI-DSS
│   │   ├── Firewall policy requirements
│   │   ├── Network segmentation requirements
│   │   └── Change management requirements
│   └── ISO 27001
│       └── Security control mappings
└── Common Scenarios
    ├── VPN Setup: Site-to-Site (IPSec)
    ├── VPN Setup: Remote Access (SSL)
    ├── High Availability (Active-Passive, Active-Active)
    ├── SD-WAN Configuration
    ├── Security Policy Design
    └── Troubleshooting Workflows
```

#### Update Mechanism
- System periodically checks official vendor websites for documentation updates
- Admin is notified when new firmware releases or security bulletins are available
- New knowledge integrates without requiring full application update
- Version-tracked so users know how current the knowledge base is

---

### 3.6 Recommendation Engine

#### Input
- Current firewall configuration (via Reverse Engineer)
- User intent in natural language ("I want to build a VPN to Tel Aviv")
- Device model and hardware capabilities (via Knowledge Base)
- Compliance requirements (if specified, e.g., "HIPAA")

#### Processing
1. Parses user intent using NLP
2. Queries Knowledge Base for relevant best practices and compliance requirements
3. Analyzes current config for conflicts, gaps, or existing relevant configurations
4. Cross-references with device model capabilities (e.g., "this model supports IKEv2")
5. Generates ranked recommendations from critical to nice-to-have
6. Explains the reasoning behind each recommendation in plain language

#### Output
- Ranked list of recommended configuration steps
- Plain-language explanations (no jargon, or jargon explained)
- Source links to vendor documentation
- Identified prerequisites and dependencies
- Suggested optimal VDOM or interface placement
- Warnings about potential downstream impacts

#### Example Output
```
User: "I need to connect Tel Aviv office to New Jersey data center. 
       We handle hospital data."

System: "I've read both firewalls. Here's what I found and recommend:

CURRENT STATE:
- New Jersey: FortiGate 90G, 3 existing VPN tunnels, VDOM-Hospital-Main active
- Tel Aviv: FortiGate 60F, fixed public IP: 203.0.113.50, no existing VPN

RECOMMENDATION:
Use VDOM-Hospital-Main on the NJ side because:
- It already contains your hospital traffic policies
- It connects to your main data center network
- HIPAA best practice: isolate hospital traffic from other operations

CONFIGURATION PLAN:
1. Create IPSec tunnel using AES-256 encryption (HIPAA requirement)
2. Configure IKEv2 key exchange (FortiGate 90G supports this, more secure)
3. Add policy-based routing to direct hospital subnets through tunnel
4. Set up redundant backup tunnel via secondary ISP
5. Enable full logging on VPN policies (HIPAA audit requirement)

All recommendations sourced from: Fortinet Security Best Practices Guide 2024, 
Section 4.3 (VPN Configuration) and HIPAA Technical Safeguards §164.312(e)(1).

Proceed? [Yes — Create backup and execute] [Show me the commands] [Cancel]"
```

---

### 3.7 Change Planner

#### Pre-Change Analysis
- Lists all configuration changes needed before execution
- Checks for policy conflicts or overlaps that would be created
- Verifies device has capacity (policy slots, tunnel slots, etc.)
- Identifies all downstream impacts: switch trunk ports, VLAN creation, routing changes

#### Change Sequencing
- Orders changes logically: interface config → routing → policies → security profiles
- Identifies rollback checkpoints after each phase
- Creates automatic backup before first change is made

#### Impact Analysis
- **Firewall-level:** "This change will modify 3 existing policies"
- **Network-level:** "Switch port ge-0/0/1 needs to be configured as trunk"
- **User-level:** "This may cause a 30-second interruption for Tel Aviv users during tunnel renegotiation"

#### On-Site Task Generation
After executing changes, system generates a clear task list for on-site technicians:

```
POST-CHANGE TASKS FOR ON-SITE TECHNICIAN (Tel Aviv):

1. SWITCH CONFIGURATION:
   - Connect to switch: Switch-TelAviv-01
   - Configure port ge-0/0/1 as 802.1Q trunk
   - Add VLANs: 100 (Hospital), 200 (Management)
   - Command: set port ge-0/0/1 mode trunk

2. VLAN ROUTING:
   - Verify VLAN 100 routing on branch router
   - Add static route: 10.1.0.0/24 → 10.0.0.1 (NJ data center)

3. TESTING:
   - Ping test from Tel Aviv workstation to NJ server: 10.1.0.10
   - Expected latency: < 80ms
   - Test hospital application connectivity

4. VERIFICATION:
   - VPN tunnel status should show: UP
   - Report completion to IT helpdesk

Contact IT support if any step fails: it@organization.com
```

---

### 3.8 First Connection Preset & Quick Audit

When connecting to a device for the **first time**, the system automatically runs a quick security audit before anything else.

#### Step 1: Device Identification
- Vendor name and logo displayed
- Exact model (e.g., FortiGate 90G)
- Software/firmware version
- Serial number
- Uptime and last reboot time

#### Step 2: Security Posture Scan
Automatically checks:
- License status and expiration dates
- Admin access restrictions ("Is management open to any IP or restricted?")
- Logging configuration ("Are critical policies logging traffic?")
- Deprecated or end-of-life features in use
- Known vulnerabilities or security bulletins for this model and version
- Default credentials (still using admin/admin?)
- Unused or unnecessary open ports/services

#### Step 3: Quick Recommendations (Prioritized)

```
🔴 CRITICAL (fix immediately):
- License expires in 20 days — plan renewal now
- Admin HTTPS access is open to ANY source IP — restrict to known admin IPs
- Default admin password has not been changed

🟡 HIGH (fix soon):
- Logging is disabled on 12 critical policies — enable for compliance
- Firmware version 7.2.1 has known vulnerability CVE-2024-XXXX — update recommended

🟢 MEDIUM (plan for next maintenance):
- Firmware is 6 months old — update available (v7.4.2)
- 8 unused security policies consuming slots — consider cleanup

🔵 LOW (optional improvements):
- FortiGuard subscription expiring in 90 days
- 3 inactive admin accounts not logged in for 180+ days
```

#### Step 4: User Actions
For each finding, user can:
- **"Fix Now"** — guided step-by-step remediation via Smart Terminal
- **"Generate Report"** — PDF audit report saved to project folder
- **"Address Later"** — added to device task list
- **"Dismiss"** — for non-applicable findings

#### Step 5: Project Organization
- User specifies project folder (local path or cloud sync target)
- All audit reports, recommendations, and change logs saved to project folder
- Reports include: timestamp, device name, findings, actions taken

#### Optional Upsells (Future)
When license expiry is detected, system can optionally show:
- "Renew your FortiCare license" → link to partner portal
- "Upgrade your FortiGuard bundle" → link to Fortinet reseller
- Partnership-tracked links generating referral revenue

---

### 3.9 Backup & Rollback Strategy

#### Automatic Backups
- Every time system connects to a device, current config is automatically backed up
- Backups stored encrypted (AES-256) locally on user's machine
- Retention: user configurable (default 14 days, minimum 7 days)
- Backup naming convention: `FortiGate-90G_TelAviv_2026-04-08_14-32.cfg`

#### Pre-Change Backup Prompt
Before executing any configuration changes:
```
"Before I make changes, I'll create a backup for rollback.
Backup retention: [14 days ▼]
Backup location: [Local + OneDrive ▼]

This backup lets you restore the firewall to its current state 
if anything goes wrong.

[Create backup and proceed] [Skip backup] [Cancel]"
```

#### Cloud Sync Options
User can choose to sync backups to:
- **OneDrive:** Synced to folder `/Firewall OBD/Backups/`
- **Google Drive:** Synced to folder `/Firewall OBD/Backups/`
- **GitHub:** Committed to private repository (with version history)
- **Local only:** No cloud sync (highest privacy)

Settings and device inventory also sync to cloud — switching computers is seamless.

#### Rollback Workflow
1. User navigates to "Rollback" section for a device
2. Sees list of backup points with date, time, and summary of what changed
3. Selects desired rollback point
4. System shows diff: "These configurations will revert:"
5. User approves
6. System pushes rollback commands via SSH
7. Verifies: "Rollback complete — SSH connection still active, config verified"

#### Critical Safety Rules
- System **always verifies SSH/HTTPS still accessible** before confirming rollback success
- Clear warning if rollback might lock out management access
- System refuses rollback if it detects it would remove all management IP access
- Rollback always creates a "before rollback" snapshot first

---

### 3.10 Version Control & Audit Trail

#### Option A: GitHub Integration (for Technical Users)
Treats firewall configurations like source code — full Git version control.

**Workflow when change is requested:**

1. **User initiates:** "Build VPN from Tel Aviv to New Jersey"

2. **GitHub Issue auto-created:**
```
Title: [VPN Setup] Tel Aviv ↔ New Jersey
Labels: change-request, vpn, fortinet
Body:
  Requested by: Nir (admin@company.com)
  Date: 2026-04-08 14:30 UTC
  Devices: FortiGate-90G-NJ, FortiGate-60F-TelAviv
  Intent: Site-to-site VPN for hospital data
  Compliance: HIPAA required
```

3. **Pre-change backup committed:**
```
Commit: "BACKUP: FortiGate-90G-NJ — pre-VPN-setup-2026-04-08"
Files: configs/FG-90G-NJ-original-2026-04-08.cfg
       configs/FG-60F-TelAviv-original-2026-04-08.cfg
```

4. **Each change committed:**
```
Commit 1: "CONFIG: Create IPSec Phase1 tunnel NJ↔TelAviv (AES-256)"
Commit 2: "CONFIG: Create IPSec Phase2 tunnel NJ↔TelAviv"
Commit 3: "POLICY: Add VPN allow policy in VDOM-Hospital-Main"
Commit 4: "ROUTING: Add policy-based route for hospital subnets"
Commit 5: "LOGGING: Enable logging on VPN policies"
```

5. **GitHub Issue updated with result:**
```
Status: ✅ COMPLETED
Duration: 18 minutes
Commits: 5
VPN Status: UP (45ms latency)
Rollback: Available — revert to commit abc123
```

6. **Rollback via Git:**
- Browse commit history on GitHub
- Select "Revert to this commit"
- System pushes rollback via SSH
- New commit created: "ROLLBACK: Reverted to pre-VPN state (user request)"

#### Option B: Email-Based Audit Trail (for All Users)
For users without GitHub — full documentation via email.

**Auto-generated email after operation:**
```
Subject: [Firewall OBD] Configuration Complete — VPN Setup NJ↔TelAviv

Requested by: Nir
Date: April 8, 2026 | 14:30 UTC
Devices: FortiGate 90G (New Jersey) + FortiGate 60F (Tel Aviv)

ORIGINAL REQUEST:
"Build VPN from Tel Aviv to New Jersey for hospital data transfer"

CHANGES EXECUTED:
1. ✅ Created IPSec Phase1 tunnel (AES-256, DH-group-14) 
2. ✅ Created IPSec Phase2 tunnel
3. ✅ Added VPN policy in VDOM-Hospital-Main
4. ✅ Configured policy-based routing for hospital subnets
5. ✅ Enabled logging on VPN policies (HIPAA compliance)

VERIFICATION:
✅ VPN Tunnel Status: UP
✅ Latency: 45ms
✅ Test traffic: passing

BACKUP & ROLLBACK:
Pre-change backup: FG-90G-NJ-2026-04-08-14-30.cfg (retained 14 days)
To rollback: Open Firewall OBD → Devices → FortiGate-NJ → Rollback → 2026-04-08

NEXT STEPS FOR ON-SITE TECHNICIAN (Tel Aviv):
1. Configure switch port as 802.1Q trunk (VLAN 100, 200)
2. Verify VLAN routing on branch router
3. Test hospital application from Tel Aviv workstations
4. Confirm connectivity and close ticket

Questions? Contact: it@company.com
```

**User stores emails in folder:** `Firewall OBD / Change Reports` in Office 365 or Gmail. Full searchable audit history. Printable for compliance audits.

#### Audit Trail Features (Both Methods)
- Who made the change (user account + email)
- When it was made (UTC timestamp)
- What was changed (detailed before/after diff)
- Why it was changed (original user request)
- Compliance standards applied
- Rollback availability and expiry
- On-site technician tasks

---

### 3.11 Device Import & Integration (Phase 1 Feature)

#### Supported Import Sources
- **SolarWinds Orion:** Export device list (CSV or XML)
- **PRTG Network Monitor:** Export device list (CSV)
- **Generic CSV:** Any platform that can export to CSV format

#### Required Import Fields
| Field | Required | Description |
|---|---|---|
| Site IP | Yes | Firewall management IP address |
| Site Name | Yes | Human-readable device name |
| Vendor/Brand | Yes | Fortinet, Palo Alto, Cisco, Check Point |
| Location | No | Physical location (New York, Tel Aviv, etc.) |
| Region | No | Geographic or organizational grouping |
| Device Type | No | Data Center, Branch, Remote Site |
| Contact | No | Responsible admin contact |

#### Import Workflow
1. User exports device list from SolarWinds/PRTG/etc.
2. Opens "Import Devices" in application
3. Selects CSV/XML file
4. Maps columns to system fields (drag-and-drop field mapping)
5. Previews import (shows 5 sample rows)
6. Confirms import
7. System imports devices and preserves hierarchy:
   - `US Region > Data Centers > FortiGate-NJ`
   - `Israel Region > Branch Offices > FortiGate-TelAviv`
8. Dashboard populates with all imported devices
9. Option to immediately run Quick Audit on all imported devices

#### Benefits
- Organizations with 400+ devices can onboard in minutes
- No manual data entry
- Preserves existing organizational structure from SolarWinds/PRTG
- Familiar organization for teams switching from SolarWinds

---

### 3.12 Security Requirements

#### User Authentication

**Account Creation:**
- Email-based registration
- Password requirements: minimum 12 characters, uppercase, lowercase, number, special character
- Email verification required before account activation

**Multi-Factor Authentication (2FA):**
- Primary option: Authenticator app (Google Authenticator, Microsoft Authenticator, Authy)
- Secondary option: SMS-based one-time codes to registered phone number
- User selects preferred method during account setup
- Both methods can be enabled simultaneously as fallbacks

**Account Recovery:**
- 10 single-use recovery codes generated at 2FA setup (user saves these securely)
- Password reset via verified email or SMS code
- Admin can reset 2FA if user loses access (requires identity verification)
- Recovery process prevents permanent lockout while maintaining security

**Session Management:**
- Session timeout: 30 minutes of inactivity (configurable by admin)
- Automatic logout on application close
- Active sessions visible in account settings
- User can remotely terminate sessions on other devices

#### Permission Levels
| Role | Read Config | Generate Reports | Execute Changes | Approve Changes | Manage Users |
|---|---|---|---|---|---|
| Read-Only | ✅ | ✅ | ❌ | ❌ | ❌ |
| Operator | ✅ | ✅ | ✅ | ❌ | ❌ |
| Administrator | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auditor | ✅ | ✅ | ❌ | ❌ | ❌ |

#### Credential Security
- Firewall credentials encrypted at rest (AES-256)
- Option to store in OS keychain (Windows Credential Manager, macOS Keychain)
- Never transmitted in plaintext
- SSH private keys: encrypted storage with optional passphrase
- API tokens: encrypted, auto-refreshed, revocable

#### Audit Logging
All events logged and immutable:
- User login/logout (timestamp, IP address, device)
- Every configuration change (who, what, when, why)
- Backup creation and rollback operations
- Failed authentication attempts
- Permission changes
- Settings modifications

Logs stored encrypted locally. Optional cloud sync. Retention: configurable (minimum 30 days, default 90 days). Exportable as PDF or CSV for compliance reporting.

#### Data Protection
- All SSH connections: encrypted in transit
- All HTTPS connections: SSL/TLS encrypted
- All backups: AES-256 encrypted at rest
- Cloud sync: encrypted before upload
- No unnecessary telemetry collected
- User controls all data retention policies

---

### 3.13 User Accounts & Licensing

#### User Account System

**Account Creation:**
- Email address + password + 2FA
- Organization name (for reporting headers)
- Phone number (for SMS 2FA, optional)
- Preferred cloud storage (OneDrive, Google Drive, GitHub, or local)

**Cloud Sync (User-Configured):**
Upon first login, user configures cloud storage:
- **OneDrive:** OAuth connection → syncs to `/Firewall OBD/`
- **Google Drive:** OAuth connection → syncs to `/Firewall OBD/`
- **GitHub:** Personal access token → syncs to private repository
- **Local only:** No cloud dependency

What syncs:
- Application settings and preferences (theme, layout, language)
- Device inventory (all imported/added firewalls)
- Configuration backups (encrypted)
- Audit reports and change logs

**Cross-Device Portability:**
When user installs application on new computer:
1. Login with email + password + 2FA
2. Connect to cloud storage (OneDrive/Google Drive/GitHub)
3. Application automatically restores:
   - All settings (dark mode, preferences, etc.)
   - All device connections (IPs, credentials)
   - All backup history
   - All audit reports

#### Licensing Model (To Be Finalized)

Licensing tiers under consideration:
- **Solo:** 1 user, up to 10 devices
- **Team:** Up to 5 users, up to 50 devices
- **Professional:** Up to 20 users, up to 200 devices
- **Enterprise:** Unlimited users and devices

License tied to user account, not machine. License includes:
- Number of managed devices
- Backup retention days
- Cloud storage allocation
- Support tier (community / priority / premium)

**Trial Period:**
- 30-day free trial with full features
- No credit card required to start
- Trial countdown visible in settings
- Upgrade prompt appears at trial end (not during trial)

**License Activation:**
- Automatic on account creation
- Visible and manageable in account settings
- Transferable to new machine (deactivate old, activate new)
- Grace period if payment lapses (read-only mode for 14 days)

---

### 3.14 UI/UX Requirements

#### Main Dashboard
- List of all managed devices with status (Online/Offline/Warning/Critical)
- Vendor logos displayed alongside device names (Fortinet, Palo Alto, Cisco, Check Point)
- Organized by region/site/data center (preserves imported structure)
- Color-coded health status:
  - 🟢 Green: All clear
  - 🟡 Yellow: Warnings (expiring licenses, outdated firmware, etc.)
  - 🔴 Red: Critical issues (expired license, critical security risk)
- Last scan time and next scheduled scan shown per device
- Search/filter bar for large device inventories
- Quick action buttons: Scan, Backup, Connect, Report

#### Visual Network Topology View
- Geographic or hierarchical map showing device locations
- Data Centers vs. Branch Offices clearly marked
- Lines showing VPN connections between sites (colored by status: green=UP, red=DOWN)
- Click-through to device details
- Zoom in/out for large networks

#### Theme Support
- **Light Mode:** Default, clean professional appearance
- **Dark Mode:** Reduced eye strain for evening/night work
- Toggle in top menu bar or settings
- Theme preference saved to cloud sync — applies on all devices

#### Smart Terminal Interface
When user double-clicks any device:
- Left panel: Device summary (model, software, health status, last backup)
- Center panel: Conversational chat interface
- Right panel: Quick action shortcuts (common operations)
- User types natural language: "What would you like to do?"
- System responds conversationally
- Approval dialog before any changes execute
- "Show me the commands" option for technical users

#### Application Menu
Standard desktop application menus:
- **File:** New device, Import devices, Save report, Settings, Exit
- **Devices:** Connect, Scan, Backup, Rollback, Delete
- **Reports:** Quick Audit, Change History, Compliance Report, Export
- **Tools:** Knowledge Base, License Manager, Cloud Sync, Update
- **Help:** Documentation, Support, About, Version

#### Settings Panel
- **General:** Language (English), date format, timezone, default backup retention
- **Appearance:** Light/Dark theme, font size, dashboard layout
- **Cloud Sync:** Configure OneDrive / Google Drive / GitHub
- **Security:** Change password, 2FA settings, active sessions, recovery codes
- **Notifications:** License expiry alerts, security bulletins, firmware updates
- **Advanced:** Connection timeouts, log levels, cache settings, developer mode

#### Platform Requirements
- Windows 10/11 (x64)
- macOS 12+ (Intel and Apple Silicon)
- Linux (Ubuntu 20.04+, Debian 11+)
- Minimum 4GB RAM, 2GB disk space
- Screen resolution: 1280×720 minimum

---

## 4. WORKFLOW EXAMPLES

### Workflow A: Site-to-Site VPN Configuration

**Scenario:** Connecting Tel Aviv office to New Jersey data center for hospital data.

**Step 1 — User opens Smart Terminal and types:**
```
"I need to connect my Tel Aviv office to New Jersey. We handle hospital patient data."
```

**Step 2 — System asks clarifying questions:**
```
System: "I'm reading both firewalls now... [scanning]

Found:
- New Jersey: FortiGate 90G | 3 existing tunnels | VDOM-Hospital-Main active
- Tel Aviv: FortiGate 60F | Fixed IP: 203.0.113.50 | No existing VPN

A few questions before I proceed:

1. Do you have a secondary ISP in Tel Aviv for redundancy?
2. What subnet does Tel Aviv use? (I see 10.0.0.0/24 — is this correct?)
3. Since this is hospital data, I'll use AES-256 (HIPAA requirement) — confirm?"

User: "Yes secondary ISP, correct subnet, yes AES-256"
```

**Step 3 — System presents recommendation:**
```
System: "Here's my plan:

RECOMMENDATION:
- Use VDOM-Hospital-Main on NJ side (already has hospital policies — HIPAA best practice)
- Primary tunnel: AES-256, IKEv2, DH-group-14
- Backup tunnel: Secondary ISP, same encryption
- Route hospital subnets through tunnel
- Enable full logging (HIPAA audit requirement)

BEFORE I START:
I'll create backups of both firewalls first.
Estimated time: 18-22 minutes

[Create backup and proceed] [Show me the commands first] [Cancel]"
```

**Step 4 — Execution:**
```
[Creating backup FG-90G-NJ-2026-04-08-14-30.cfg... ✅]
[Creating backup FG-60F-TelAviv-2026-04-08-14-30.cfg... ✅]
[Creating IPSec Phase1 primary tunnel... ✅]
[Creating IPSec Phase1 backup tunnel... ✅]
[Creating IPSec Phase2 tunnels... ✅]
[Adding policy in VDOM-Hospital-Main... ✅]
[Configuring policy-based routing... ✅]
[Enabling logging on VPN policies... ✅]
[Testing tunnel... VPN Status: UP ✅ | Latency: 45ms ✅]

✅ ALL DONE! Your VPN is live.
```

**Step 5 — Documentation:**
- GitHub issue created with all commits
- Email sent with summary and on-site technician tasks
- Report saved to project folder

---

### Workflow B: First Connection Quick Audit

**Scenario:** Connecting to a FortiGate 90G for the first time.

```
[Connecting via SSH to 10.0.1.1...]
[Detected: FortiGate 90G | FortiOS 7.4.2 | Serial: FG90GXXXXXXX]

QUICK SECURITY AUDIT RESULTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 CRITICAL (2 issues):
  1. Admin access open to ANY IP — Critical security risk
  2. License expires in 18 days — Renewal required

🟡 HIGH (1 issue):
  3. Logging disabled on 8 policies — Compliance risk

🟢 MEDIUM (2 issues):
  4. Firmware 7.4.2 — Update available (7.4.5)
  5. 5 admin accounts inactive 180+ days

WHAT WOULD YOU LIKE TO DO?
[Fix Critical Issues Now] [Generate PDF Report] [Address Later] [Skip Audit]
```

---

### Workflow C: Troubleshooting Blocked Traffic

**Scenario:** Users in Tel Aviv can't reach the NJ application server.

```
User: "Tel Aviv users can't access the hospital application in New Jersey"

System: "Let me trace the traffic path... [analyzing both firewalls]

Checking:
✅ Tel Aviv firewall: outbound policy allows traffic
✅ Tel Aviv VPN tunnel: UP and passing traffic
✅ NJ firewall: inbound policy allows traffic
❌ NJ firewall routing: PROBLEM FOUND

ROOT CAUSE:
The NJ firewall doesn't have a route back to Tel Aviv's subnet (10.0.0.0/24).
Response traffic is going to the internet instead of back through the VPN.

FIX:
Add static route on NJ FortiGate:
  Destination: 10.0.0.0/24
  Gateway: VPN tunnel interface (tunnel.1)
  
This tells NJ: 'Send responses to Tel Aviv back through the VPN tunnel'

[Apply Fix] [Show Commands] [Cancel]"

User: "Apply Fix"

System: "[Creating backup before change... ✅]
[Adding static route on NJ FortiGate... ✅]
[Verifying: Test traffic Tel Aviv → NJ... ✅]

✅ RESOLVED! Tel Aviv users can now reach the NJ application.
Response time: 125ms

Issue logged and email report sent."
```

---

## 5. DATA FLOW DIAGRAM

```
USER INPUT (Natural Language)
"Connect Tel Aviv to New Jersey"
         ↓
SMART TERMINAL (Intent Recognition / NLP)
Identifies: VPN setup, 2 locations, hospital data, HIPAA needed
         ↓
CONFIG READER (SSH to both firewalls)
Executes vendor-specific CLI commands
Collects raw configuration output
         ↓
REVERSE ENGINEER (Parses raw output)
Rebuilds full hierarchy: VDOMs, policies, VPNs, interfaces
         ↓
UNIVERSAL DATA MODEL
Normalizes config into standardized objects
         ↓
KNOWLEDGE BASE QUERY
"FortiGate VPN best practices"
"HIPAA encryption requirements"
"IPSec Phase1/Phase2 configuration"
         ↓
RECOMMENDATION ENGINE
Analyzes: current config + user intent + knowledge base
Generates: ranked recommendations + plain-language explanations
         ↓
USER APPROVAL
System shows plan, user confirms
         ↓
CHANGE PLANNER
Sequences changes, identifies downstream impacts
Creates backup point
         ↓
EXECUTION (SSH to firewalls)
Pushes commands in correct sequence
Monitors for errors
         ↓
POST-CHANGE VERIFICATION
Tests VPN status, pings, logs
         ↓
DOCUMENTATION & AUDIT ENGINE
→ GitHub: issue created, commits logged
→ Email: change report + technician tasks
→ Local: backup + audit log updated
         ↓
USER NOTIFICATION
"✅ Done! VPN is UP. On-site tasks sent to technician."
```

---

## 6. TECHNICAL STACK

### Core Language
**Python 3.11+**
- Cross-platform (Windows, Mac, Linux)
- Strong library ecosystem for SSH, networking, encryption
- Rapid development and iteration

### Desktop GUI Framework
**PyQt6 or PySide6**
- Native desktop application look and feel
- Cross-platform (same code, different renders per OS)
- Supports light/dark themes
- Rich widget library for complex UIs

### SSH & Network Libraries
- **Paramiko or Netmiko:** SSH connections and command execution
- **Netmiko:** Higher-level library with FortiGate, Palo Alto, Cisco, Check Point support built-in
- **Requests:** HTTPS API connections

### Encryption & Security
- **cryptography.io (Fernet):** AES-256 encryption for credentials and backups
- **OS Keychain integration:** Windows Credential Manager, macOS Keychain

### Database & Storage
- **SQLite:** Local database for device inventory, audit logs, settings
- **JSON files:** Knowledge base storage (vendor commands, best practices)

### Cloud Integration
- **Microsoft Graph API:** OneDrive sync
- **Google Drive API:** Google Drive sync
- **PyGithub / GitHub REST API:** GitHub integration

### NLP / AI Integration
- **OpenAI API or local LLM:** Natural language understanding for Smart Terminal
- **Custom intent classifier:** Map user requests to firewall operation types

### Packaging & Distribution
- **PyInstaller:** Creates .exe (Windows), .dmg (Mac), .AppImage (Linux)
- **Code signing certificates:** Trusted installer on Windows and Mac
- **Auto-update:** Squirrel (Windows), Sparkle (Mac), AppImage update (Linux)

### Development Tools
- **Git + GitHub:** Source control
- **GitHub Actions:** CI/CD pipeline (automated testing and builds)
- **Pytest:** Unit and integration testing
- **Black:** Code formatting
- **Pylint:** Code quality
- **Sphinx/MkDocs:** Documentation generation

---

## 7. PHASE 1 SCOPE (MVP)

### In Scope — Phase 1

**Vendor Support:**
- Fortinet FortiGate (all models — 60, 60F, 90, 90G, 100F, etc.)
- SSH connection (full feature support)
- HTTPS connection (limited feature support, with user notification)

**Core Features:**
- ✅ Desktop application (Windows and Mac initially, Linux Phase 1.1)
- ✅ SSH and HTTPS connection management
- ✅ FortiGate config reader (full command set)
- ✅ Reverse engineering: VDOMs, policies, interfaces, routing, VPN
- ✅ Universal Data Model (FortiGate objects)
- ✅ First Connection Quick Audit
- ✅ Smart Terminal (conversational interface)
- ✅ VPN configuration guidance (site-to-site IPSec)
- ✅ Static routing configuration
- ✅ Security policy management
- ✅ Automatic backup and rollback
- ✅ Email-based audit trail
- ✅ Device import from CSV (SolarWinds, PRTG, generic)
- ✅ 2FA authentication (authenticator app + SMS)
- ✅ User accounts and cloud sync (OneDrive, Google Drive)
- ✅ Light/Dark theme
- ✅ Knowledge Base (FortiGate documentation)
- ✅ Basic recommendations and diagnostics
- ✅ PDF/email report generation

**Out of Scope — Phase 1:**
- ❌ GitHub integration (Phase 2)
- ❌ Palo Alto, Cisco, Check Point support (Phase 2)
- ❌ Mobile app (Phase 3)
- ❌ Advanced compliance reporting (Phase 2)
- ❌ Multi-tenant / MSP features (Phase 3)
- ❌ Machine learning diagnostics (Phase 3)
- ❌ Multi-language support (Phase 2)
- ❌ Cloud-hosted deployment (Phase 3)

---

## 8. FUTURE ROADMAP

### Phase 2 (Q3-Q4 2026)
- Add Palo Alto Networks full support
- Add Cisco ASA/FTD full support
- Add Check Point full support
- GitHub integration for config versioning
- Advanced troubleshooting workflows
- Performance analytics dashboards
- Compliance reporting (HIPAA, PCI-DSS, ISO 27001)
- Partnership integrations (license renewal links)
- Optional upsells (premium support, advanced features)
- Linux installer

### Phase 3 (2027)
- Mobile application (iOS first, Android second)
- Cloud-based central management portal (optional)
- Multi-user/multi-tenant collaboration
- API for third-party integrations
- Advanced AI-powered predictive diagnostics
- Multi-language support (Hebrew, Spanish, German, French, Japanese)
- SD-WAN configuration and management
- SIEM integration (Splunk, QRadar, etc.)
- Automated vulnerability scanning

### Phase 4 (2027-2028)
- White-label platform for MSPs and resellers
- On-premises hosted deployment option
- GitOps workflow integration (CI/CD for firewall configs)
- Federated firewall orchestration (manage 1000s of devices)
- Machine learning anomaly detection
- Predictive maintenance and capacity planning
- Integration with ITSM platforms (ServiceNow, Jira)

---

## 9. MONETIZATION & PARTNERSHIPS

### Revenue Streams

**Software Licensing:**
- Subscription model (monthly/annual per user)
- Perpetual license option for enterprises
- Freemium tier (limited devices, basic features)
- Trial-to-paid conversion (30-day full trial)

**Partnership Revenue:**
When system detects actionable needs (license expiry, firmware updates, subscription renewals):
- Inline "Renew Now" buttons linking to authorized resellers
- Affiliate tracking for referral commissions
- Co-marketing agreements with Fortinet, Palo Alto partners

**Example partnership flow:**
```
System detects: "FortiCare license expires in 18 days"
Displays: "⚠️ License expiring soon
           [Renew with AuthorizedReseller.com] [Remind me later]"
User clicks link → system tracks referral → commission earned
```

**Premium Features / Add-Ons:**
- Advanced compliance reporting module (+$X/month)
- Priority support tier (+$X/month)
- MSP/multi-tenant management (+$X/month)
- Training and certification courses
- Professional services (complex migrations, custom parsers)

**MSP / Channel Partner Program:**
- White-label version for managed service providers
- Partner pricing tiers (buy low, sell high)
- Partner portal for managing customer accounts
- Revenue sharing on referrals

---

## 10. RISKS & MITIGATION

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Vendor changes CLI syntax | High | Medium | Modular parser architecture, automated regression testing, quick patch cycle |
| User accidentally locks out firewall | Critical | Low | Pre-flight validation, mandatory backup, warnings, rollback capability |
| SSH credentials compromised | Critical | Low | AES-256 encryption, OS keychain, audit logging, 2FA |
| Knowledge base becomes outdated | Medium | Medium | Automated doc monitoring, update notifications, version tracking |
| Vendor releases competing tool | High | Low | Focus on multi-vendor and UX differentiation, build community |
| SSH connection drops mid-change | High | Medium | Atomic operations where possible, partial rollback detection, resume capability |
| User misunderstands recommendation | Medium | Medium | Plain-language explanations, "show commands" option, documentation links |
| Scaling to large device inventories | Medium | Low | Async operations, connection pooling, pagination in UI |

---

## 11. SUCCESS METRICS

### Technical Performance
- SSH connection established in < 5 seconds
- Full config read and parse in < 30 seconds
- Quick Audit scan in < 45 seconds
- VPN configuration completed (end-to-end) in < 20 minutes
- 99.9% backup reliability (no failed backups)
- 100% rollback success rate (when management access maintained)

### User Experience
- Time to configure site-to-site VPN (non-specialist): < 20 minutes
- Net Promoter Score (NPS): > 50
- User satisfaction rating: > 4.5/5
- Support ticket rate: < 5% of operations require support

### Business Metrics (Year 1 Targets)
- 100+ active users by end of Year 1
- 500+ managed firewalls total
- 90%+ monthly user retention
- NPS > 50
- Trial-to-paid conversion > 20%

---

## 12. CONCLUSION

The **Firewall OBD Platform** addresses a genuine market gap. Organizations managing multi-vendor firewall environments today have no single accessible, intelligent tool that helps non-specialists configure and troubleshoot firewalls in plain language while maintaining enterprise-grade security, auditability, and compliance.

### Key Differentiators
1. **Conversational AI interface** — no other tool talks to you like this
2. **Multi-vendor from day one** — not locked to one vendor
3. **Git-style versioning** — configs treated like code
4. **Accessible to non-specialists** — you don't need to know CLI syntax
5. **Knowledge-backed recommendations** — sourced from official vendor docs
6. **Complete audit trail** — every change logged, trackable, reversible
7. **Downstream awareness** — understands switch and network layer impacts

### Starting Point
Phase 1 focuses on **Fortinet FortiGate** — the most common enterprise firewall — to validate the concept, build real-world feedback, and establish the architecture pattern that will scale to other vendors.

**Next steps:**
1. Finalize and approve this HLD document
2. Set up GitHub repository and development workflow
3. Define Phase 1 milestones and GitHub Issues
4. Begin coding: SSH connection module → FortiGate parser → UDM → Smart Terminal

---

*END OF DOCUMENT — HLD v1.0*  
*Next Version: v1.1 (pending review and feedback)*  
*Author: Nir | Date: May 2026*
