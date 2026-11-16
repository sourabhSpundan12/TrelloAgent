// MongoDB Initialization Script for Agentic Task Manager

db = db.getSiblingDB("agentic_task_manager");

// 1. Tools Collection
db.createCollection("tools");
db.tools.createIndex({ "name": 1 }, { unique: true, name: "idx_tool_name_unique" });
db.tools.createIndex({ "category": 1 }, { name: "idx_tool_category" });
db.tools.createIndex({ "is_active": 1 }, { name: "idx_tool_is_active" });
db.tools.createIndex(
    { "name": "text", "description": "text", "tags": "text" },
    { name: "idx_tool_text_search" }
);

// 2. Pending Actions Collection
db.createCollection("pending_actions");
db.pending_actions.createIndex({ "action_id": 1 }, { unique: true, name: "idx_action_id_unique" });
db.pending_actions.createIndex({ "payload_hash": 1 }, { name: "idx_action_payload_hash" });
db.pending_actions.createIndex({ "status": 1 }, { name: "idx_action_status" });
db.pending_actions.createIndex({ "user_id": 1 }, { name: "idx_action_user_id" });
db.pending_actions.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0, name: "idx_action_ttl_expiry" });
db.pending_actions.createIndex({ "created_at": -1 }, { name: "idx_action_created_at" });

// 3. Audit Logs Collection
db.createCollection("audit_logs");
db.audit_logs.createIndex({ "action_id": 1 }, { name: "idx_audit_action_id" });
db.audit_logs.createIndex({ "actor_id": 1 }, { name: "idx_audit_actor_id" });
db.audit_logs.createIndex({ "created_at": -1 }, { name: "idx_audit_created_at" });
db.audit_logs.createIndex({ "execution_status": 1 }, { name: "idx_audit_status" });

// 4. Task Activities Collection
db.createCollection("task_activities");
db.task_activities.createIndex({ "card_id": 1 }, { name: "idx_activity_card_id" });
db.task_activities.createIndex({ "timestamp": -1 }, { name: "idx_activity_timestamp" });
db.task_activities.createIndex({ "status": 1 }, { name: "idx_activity_status" });
db.task_activities.createIndex({ "employee_id": 1 }, { name: "idx_activity_employee_id" });

// 5. Employee Snapshots Collection
db.createCollection("employee_snapshots");
db.employee_snapshots.createIndex(
    { "employee_id": 1, "snapshot_date": 1 },
    { unique: true, name: "idx_snapshot_emp_date_unique" }
);
db.employee_snapshots.createIndex({ "snapshot_date": -1 }, { name: "idx_snapshot_date" });

print("Agentic Task Manager indexes successfully created.");

