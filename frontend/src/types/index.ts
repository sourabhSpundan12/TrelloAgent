// Core Task & Status Definitions
export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'IN_REVIEW' | 'DONE';
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  trelloList: string;
  assignee: {
    id: string;
    name: string;
    avatar: string;
    email: string;
  };
  dueDate: string;
  isOverdue: boolean;
  createdAt: string;
  tags: string[];
}

// Employee Metrics & Workload
export interface Employee {
  id: string;
  empId: string; // e.g. EMP-101
  name: string;
  email: string;
  role: string;
  department: string;
  avatar: string;
  status: 'ACTIVE' | 'ON_LEAVE' | 'AWAY';
  assignedTasksCount: number;
  inProgressCount: number; // Actively working
  inReviewCount: number;
  completedCount: number;
  overdueCount: number;
}

// AI Assistant & Approval Workflow
export interface ActionApprovalPreview {
  actionId: string;
  actionType: 'CREATE_CARD' | 'MOVE_CARD' | 'UPDATE_CARD' | 'DELETE_CARD' | 'ARCHIVE_CARD' | string;
  targetEntity: string;
  cardName: string;
  description?: string;
  boardName: string;
  boardId?: string;
  listName: string;
  listId?: string;
  priority?: string;
  dueDate?: string;
  parameters: Record<string, any>;
  status: 'PENDING' | 'CONFIRMED' | 'REJECTED' | 'EXECUTING' | 'EXECUTED' | 'FAILED' | 'EXPIRED';
  createdAt: string;
  cardUrl?: string;
  cardId?: string;
  errorMessage?: string;
  executionResult?: Record<string, any>;
}

export interface ApprovalEditPayload {
  title?: string;
  description?: string;
  board_name?: string;
  board_id?: string;
  list_name?: string;
  list_id?: string;
  priority?: string;
  due_date?: string;
}

export interface ApprovalConfirmResult {
  action_id: string;
  status: string;
  tool_id: string;
  card_id?: string;
  card_url?: string;
  execution_result?: any;
  message: string;
}

export interface Board {
  id: string;
  board_id: string;
  name: string;
  desc?: string;
  url?: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  board_id?: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface ChatMessage {
  id: string;
  conversation_id?: string;
  board_id?: string;
  model_id?: string;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  created_at?: string;
  intent?: string;
  parameters?: Record<string, any>;
  discoveredTool?: {
    name: string;
    category: string;
    relevanceScore: number;
    explanation: string;
  };
  approvalPreview?: ActionApprovalPreview;
  executionStatus?: 'DISCOVERING' | 'PREPARING_PREVIEW' | 'AWAITING_APPROVAL' | 'CONFIRMED' | 'REJECTED' | 'EXECUTED';
  isLiveApiResult?: boolean;
  executionResult?: Record<string, any>;
}

export interface AIInterpretResponse {
  command: string;
  intent: string;
  entity: string;
  parameters: Record<string, any>;
  board_id?: string | null;
  model_id?: string | null;
  selected_tool_id?: string | null;
  selected_tool_name?: string | null;
  approval_required: boolean;
  requires_clarification: boolean;
  clarification_message?: string | null;
  confidence: number;
  candidate_tools_count: number;
  action_id?: string | null;
  conversational_message?: string | null;
  conversation_id?: string | null;
  execution_result?: any;
  execution_preview?: {
    action_id: string;
    tool_id: string;
    tool_name: string;
    category: string;
    action_type?: string;
    parameters: Record<string, any>;
    payload_hash: string;
    status: string;
    message: string;
    draft?: {
      title: string;
      description?: string;
      board_name?: string;
      board_id?: string | null;
      list_name?: string;
      list_id?: string | null;
      priority?: string;
      due_date?: string | null;
      parameters?: Record<string, any>;
    };
  } | null;
}

// Activity History
export type ActivityEventType = 
  | 'CARD_CREATED' 
  | 'CARD_UPDATED' 
  | 'CARD_MOVED' 
  | 'EMPLOYEE_ASSIGNED' 
  | 'TASK_COMPLETED' 
  | 'CARD_DELETED';

export interface ActivityEvent {
  id: string;
  eventType: ActivityEventType;
  actor: {
    name: string;
    avatar: string;
  };
  cardTitle: string;
  cardId: string;
  details: string;
  timestamp: string;
  statusChange?: {
    from: string;
    to: string;
  };
}

// Tool Management
export type ToolCategory = 'TRELLO' | 'REPORTING' | 'EMPLOYEE' | 'ANALYTICS' | 'SYSTEM';
export type ToolStatus = 'ACTIVE' | 'DISABLED';

export interface RegisteredTool {
  id: string;
  name: string;
  description: string;
  category: ToolCategory;
  version: string;
  status: ToolStatus;
  requiresApproval: boolean;
  executorType: string;
  parametersSchema: Record<string, any>;
  tags: string[];
  totalExecutions: number;
  lastExecutedAt?: string;
}

// Reports & Analytics
export type ReportType = 'DAILY' | 'WEEKLY' | 'EMPLOYEE' | 'TEAM' | 'CUSTOM';

export interface WorkloadReport {
  reportType: ReportType;
  generatedAt: string;
  dateRange: {
    startDate: string;
    endDate: string;
  };
  summary: {
    totalTasks: number;
    completedTasks: number;
    inProgressTasks: number;
    inReviewTasks: number;
    pendingTasks: number;
    overdueTasks: number;
    completionRatePercent: number;
  };
  employeeBreakdown: Array<{
    employeeId: string;
    name: string;
    assignedCount: number;
    inProgressCount: number;
    completedCount: number;
    overdueCount: number;
    workloadScore: 'OPTIMAL' | 'HIGH' | 'OVERLOADED';
  }>;
}

// System Health from Phase 1
export interface ServiceStatus {
  mongodb: string;
  gemini_configured: boolean;
  trello_configured: boolean;
  n8n_configured: boolean;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  version: string;
  environment: string;
  database: string;
  uptime_seconds: number;
  timestamp: string;
  services: ServiceStatus;
}

// Phase 4B: Model Context Protocol (MCP) Types
export interface MCPServer {
  server_id: string;
  name: string;
  description?: string;
  transport_type: 'streamable_http' | 'sse' | 'stdio' | string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  timeout_seconds: number;
  enabled: boolean;
  status: 'CONNECTED' | 'DISCONNECTED' | 'ERROR' | string;
  allow_internal: boolean;
  last_connected_at?: string;
  last_error?: string;
  discovered_tool_count: number;
  created_at: string;
  updated_at: string;
}

export interface MCPServerRegisterPayload {
  server_id: string;
  name: string;
  description?: string;
  transport_type: 'streamable_http' | 'sse' | 'stdio' | string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  timeout_seconds?: number;
  enabled?: boolean;
  allow_internal?: boolean;
}

export interface MCPDiscoveryResult {
  server_id: string;
  tools_discovered: number;
  tools_registered: number;
  tools_updated: number;
  tools: any[];
}

// User & Authentication Types
export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: 'ADMIN' | 'HR' | 'MANAGER' | 'EMPLOYEE' | string;
  department?: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  department?: string;
  role?: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface ForgotPasswordPayload {
  email: string;
}

export interface VerifyResetCodePayload {
  email: string;
  code: string;
}

export interface ResetPasswordPayload {
  email: string;
  code: string;
  new_password: string;
}

export interface AuthMessageResponse {
  message: string;
  success?: boolean;
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

// Real-Time Notification Types
export interface NotificationItem {
  id: string;
  type: 'APPROVAL_REQUIRED' | 'ACTION_EXECUTED' | 'ACTION_CANCELLED' | 'ACTION_FAILED' | 'INFO' | 'DEADLINE_REMINDER';
  title: string;
  message: string;
  created_at: string;
  is_read: boolean;
  action_id?: string;
  action_type?: string;
  card_url?: string;
  target_tab?: string;
  priority?: string;
  stage?: string;
  stage_label?: string;
  urgency?: string;
  due_date?: string;
}

export interface NotificationsResponse {
  status: string;
  unread_count: number;
  total: number;
  notifications: NotificationItem[];
}
