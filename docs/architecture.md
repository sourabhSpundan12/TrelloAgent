# Agentic Task Manager - System Architecture Document

## 1. System Overview

The **Agentic Task Manager** is a production-grade enterprise system enabling teams to manage Trello tasks and monitor employee workloads through natural language commands powered by Google Gemini, while maintaining strict data privacy, deterministic execution, and mandatory human-in-the-loop approvals.

```
                      +-----------------------------+
                      |   React + Vite Frontend     |
                      |  (Dashboard & Command Bar)  |
                      +--------------+--------------+
                                     |  HTTP / REST
                                     v
                      +-----------------------------+
                      |      FastAPI Backend        |
                      |          (/api/v1)          |
                      +--+-----------------------+--+
                         |                       |
            +------------+-----------+           |
            |                        |           |
            v                        v           v
+-----------------------+  +------------------+  +-------------------+
|  Google Gemini Agent  |  |  MongoDB Storage |  |  Trello REST API  |
| (Intent & Tool Choice)|  | (Tools, Actions, |  | (Board, Cards,    |
| (Zero Sensitive Data) |  |  Logs, Snapshots)|  |  Lists, Webhooks) |
+-----------------------+  +------------------+  +-------------------+
                                     ^
                                     |
                           +---------+---------+
                           |  n8n Orchestration|
                           | (Webhooks, Cron)  |
                           +-------------------+
```

---

## 2. Dynamic Tool Architecture

To scale seamlessly to 500+ tools without context window exhaustion or hardcoding:

1. **Tool Registry**:
   - Stores tool metadata, JSON parameter schemas, required permissions, versioning, and executor bindings in MongoDB (`tools` collection).
   - Allows dynamically registering, enabling, and deprecating tools without code rewrites.

2. **Tool Discovery**:
   - Queries relevant tools dynamically based on user command semantics (category filters, keyword matching, text search).
   - Gemini only receives the small subset of relevant tool schemas rather than all 500+ definitions.

3. **Tool Executor**:
   - Validates parameter inputs against Pydantic schemas, verifies RBAC permissions, generates execution previews, and runs authorized actions.

---

## 3. Two-Phase Human-in-the-Loop Security Lifecycle

All mutating operations strictly obey a two-phase protocol:

```
[ User NL Command ] 
        |
        v
[ 1. Interpret Intent & Discover Tools ]
        |
        v
[ 2. Validate Parameters via Pydantic ]
        |
        v
[ 3. Generate Preview & Canonical SHA-256 Hash ]
        |
        v
[ 4. Save Pending Action in MongoDB (status: PENDING, with TTL) ]
        |
        v
[ 5. Present Preview in UI for Explicit Human Confirmation ]
        |
   +----+----+
   |         |
[Approved] [Rejected / Edited]
   |         |
   |         +--> [ Invalidate Previous Approval & Abort ]
   v
[ 6. Backend Re-verifies Hash & User Binding ]
        |
        v
[ 7. Execute Mutation via Registered Executor ]
        |
        v
[ 8. Append Immutable Entry to Audit Log ]
```

---

## 4. Privacy & Data Boundary

- **What reaches Gemini**: Sanitized command text and public tool definitions.
- **What NEVER reaches Gemini**:
  - Trello card descriptions and sensitive checklist contents.
  - Employee records, names, contact info, and internal performance metrics.
  - Analytics and calculated workload reports.
  - Passwords, API tokens, and access keys.
- **Calculations**: All analytics, metrics, workload aggregations, and snapshot rollups are computed deterministically in Python.

---

## 5. MongoDB Collections & Indexes

| Collection | Purpose | Primary Indexes |
| :--- | :--- | :--- |
| `tools` | Dynamic tool registry | `name` (unique), `category`, `is_active`, compound text (`name`, `description`, `tags`) |
| `pending_actions` | Staged preview actions | `action_id` (unique), `payload_hash`, `status`, `user_id`, `expires_at` (TTL), `created_at` |
| `audit_logs` | Immutable audit trail | `action_id`, `actor_id`, `created_at`, `execution_status` |
| `task_activities` | Historical task state changes | `card_id`, `timestamp`, `status`, `employee_id` |
| `employee_snapshots`| Daily employee workload rollups | `(employee_id, snapshot_date)` (unique compound), `snapshot_date` |

---

## 6. Model Context Protocol (MCP) & Trello Integration (Phase 4B & Phase 5)

The platform integrates Model Context Protocol (MCP 2.x) to standardize tool exposure and distributed tool execution across external platforms like Trello:

```
+-----------------------------------------------------------------------------------+
|                            FastAPI Application (Port 8000)                        |
|                                                                                   |
|  +---------------------------+                +--------------------------------+  |
|  |   Gemini AI Assistant     |                |  Mounted MCP Server (/mcp)     |  |
|  |   (Natural Language)      |                |  (Official MCP Python SDK)     |  |
|  +-------------+-------------+                +---------------+----------------+  |
|                |                                              |                   |
|                v                                              | tools/call        |
|  +-------------+-------------+                                | (Streamable HTTP) |
|  | Dynamic Tool Discovery    |                                |                   |
|  | (MongoDB 'tools' catalog) |                                |                   |
|  +-------------+-------------+                                |                   |
|                |                                              |                   |
|                v                                              |                   |
|  +-------------+-------------+   delegates    +---------------+----------------+  |
|  | Tool Executor Service     | ------------>  | MCP Client Manager             |  |
|  | (Policy, Schema, Roles)   |                | (Connection, Discovery, RPC)   |  |
|  +---------------------------+                +---------------+----------------+  |
+---------------------------------------------------------------|-------------------+
                                                                |
                                                                v
                                                +---------------+----------------+
                                                | Trello REST Client (httpx)     |
                                                | - boards, lists, cards, moves  |
                                                +---------------+----------------+
                                                                |
                                                                v
                                                +--------------------------------+
                                                | Trello REST API                |
                                                | (https://api.trello.com/1)     |
                                                +--------------------------------+
```

### Key MCP Architectural Principles
1. **Dynamic Tool Registry Synchronization**: Tools exposed by MCP servers are discovered via `tools/list`, fingerprinted (SHA-256), and namespaced as `mcp.<server_id>.<remote_tool_name>`.
2. **SSRF Network Isolation**: Remote MCP connections are audited and private/loopback network targets are blocked unless explicit permission is granted.
3. **Multi-Source Execution**: The Tool Executor automatically routes native tools through vetted local handlers and remote tools through the MCP Client Manager.
4. **Credential Isolation**: Trello API credentials (`TRELLO_API_KEY`, `TRELLO_TOKEN`) remain confined to the backend service and are never exposed via RPC or Gemini prompts.

---

## 7. Database Layer Architecture (MongoDB Atlas & Standalone)

The backend database layer utilizes `motor.motor_asyncio` (asynchronous driver on top of `pymongo` 4.x and `dnspython`) to interface with either **MongoDB Atlas** or local/standalone MongoDB instances.

```
                      +------------------------------------------+
                      |         MongoDBManager (Singleton)        |
                      |   - URI Masking for Credentials          |
                      |   - Connection Pooling (min: 5, max: 50) |
                      |   - Health & Readiness Probes (ping)     |
                      +--------------------+---------------------+
                                           | AsyncIOMotorDatabase
               +---------------------------+---------------------------+
               |                           |                           |
               v                           v                           v
     +-------------------+       +-------------------+       +-------------------+
     |  UserRepository   |       |  ToolRepository   |       |ApprovalRepository |
     |  & TokenRepository|       |  & MCPServerRepo  |       |                   |
     | (users, tokens)   |       | (tools, servers)  |       | (pending_actions) |
     +-------------------+       +-------------------+       +-------------------+
               |                           |                           |
               +---------------------------+---------------------------+
                                           |
                                           v
             +-----------------------------------------------------------+
             |         MongoDB Atlas Cloud Replica Set Cluster           |
             |   - mongodb+srv:// SRV DNS seedlist resolution            |
             |   - Automated TLS 1.3 encryption                          |
             |   - Replica set failover & retryable writes               |
             |   - TTL Indexes (automatic document expiry)               |
             +-----------------------------------------------------------+
```

### Core Database Capabilities
1. **Cloud & Local Dual Compatibility**:
   - Configured via `MONGODB_URL` and `MONGODB_DATABASE` (with legacy fallback to `MONGODB_URI` and `MONGODB_DB_NAME`).
   - Supports `mongodb+srv://` URIs for MongoDB Atlas as well as standard `mongodb://` for local Docker development.
2. **Unified Database Instance**:
   - All repositories (`UserRepository`, `RefreshTokenRepository`, `ToolRepository`, `MCPServerRepository`, `ApprovalRepository`) receive the single `AsyncIOMotorDatabase` injected from `MongoDBManager.get_db()`.
3. **Automated Schema Indexes & TTL Expiration**:
   - `users`: unique index on `email`.
   - `refresh_tokens`: unique index on `token_hash`, TTL index on `expires_at` (`expireAfterSeconds=0`).
   - `tools`: unique indexes on `tool_id` and `name`, indexes on `category` and `enabled`.
   - `pending_actions`: unique index on `action_id`, index on `payload_hash`, TTL index on `expires_at` (`expireAfterSeconds=0`).
   - `mcp_servers`: unique index on `server_id`.
4. **Credential Protection**:
   - Secrets are masked during logging via `mask_mongo_uri` (`mongodb+srv://user:****@cluster.mongodb.net/`).
5. **Resilient Health & Readiness Probes**:
   - `/health` and `/health/ready` perform active ping checks and report connection status.

---

## 8. API Versioning & Endpoints

All application routes are scoped under `/api/v1` with standard health monitoring:
- `GET /health` & `GET /api/v1/health`: Checks MongoDB ping, service configuration flags, version, and uptime.
- `GET /health/ready`: Readiness probe verifying active MongoDB connectivity.
- `GET /health/live`: Liveness probe for orchestrators.
- `GET /docs`: Interactive OpenAPI documentation.
- `GET /redoc`: Alternative ReDoc documentation.

