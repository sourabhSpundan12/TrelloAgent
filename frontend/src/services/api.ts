import axios from 'axios';
import {
  AIInterpretResponse,
  ApprovalConfirmResult,
  ApprovalEditPayload,
  AuthMessageResponse,
  AuthTokenResponse,
  AuthUser,
  Board,
  ChangePasswordPayload,
  ChatSession,
  EmployeeLevelHistoryItem,
  EmployeeTaskReportSummary,
  ForgotPasswordPayload,
  HealthResponse,
  LoginCredentials,
  MCPDiscoveryResult,
  MCPServer,
  MCPServerRegisterPayload,
  NotificationsResponse,
  ResetPasswordPayload,
  TaskAssignment,
  TaskAssignmentHistoryItem,
  TaskTemplate,
  TaskTemplatesResponse,
  VerifyResetCodePayload,
} from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Robust token getter:
 * - Checks localStorage keys: 'access_token', 'token', 'atm_token'
 * - Handles JSON stringified objects if present
 * - Strips leading 'Bearer ' prefix if accidentally stored
 */
export const getStoredToken = (): string | null => {
  const raw =
    localStorage.getItem('access_token') ||
    localStorage.getItem('token') ||
    localStorage.getItem('atm_token');
  if (!raw) return null;
  let token = raw.trim();
  if (token.startsWith('{') && token.endsWith('}')) {
    try {
      const parsed = JSON.parse(token);
      token = parsed.access_token || parsed.token || '';
    } catch {
      // ignore
    }
  }
  if (token.toLowerCase().startsWith('bearer ')) {
    token = token.slice(7).trim();
  }
  return token || null;
};

/**
 * Stores tokens consistently under both 'access_token' and 'token'.
 */
export const setStoredTokens = (accessToken: string, refreshToken?: string): void => {
  let cleanAccess = accessToken.trim();
  if (cleanAccess.toLowerCase().startsWith('bearer ')) {
    cleanAccess = cleanAccess.slice(7).trim();
  }
  localStorage.setItem('access_token', cleanAccess);
  localStorage.setItem('token', cleanAccess);
  if (refreshToken) {
    localStorage.setItem('refresh_token', refreshToken.trim());
  }
};

/**
 * Clears all authentication tokens from localStorage.
 */
export const clearStoredTokens = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('atm_token');
};

/**
 * Helper to build auth headers, backwards compatible with manual calls.
 */
export const getAuthHeaders = (token?: string) => {
  const rawToken = token || getStoredToken();
  if (!rawToken) return {};
  let clean = rawToken.trim();
  if (clean.toLowerCase().startsWith('bearer ')) {
    clean = clean.slice(7).trim();
  }
  return clean ? { Authorization: `Bearer ${clean}` } : {};
};

/**
 * Axios Request Interceptor:
 * Guarantees every protected outgoing request carries the sanitized Authorization Bearer header.
 */
api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    const existing = config.headers?.Authorization;
    if (!existing) {
      config.headers.Authorization = `Bearer ${token}`;
    } else if (typeof existing === 'string') {
      let clean = existing.trim();
      while (clean.toLowerCase().startsWith('bearer ')) {
        clean = clean.slice(7).trim();
      }
      config.headers.Authorization = `Bearer ${clean || token}`;
    }
  }
  return config;
});

/**
 * Silent token refresher helper:
 * Exchanges rotating refresh token for a new access token.
 */
export const silentRefreshToken = async (): Promise<string | null> => {
  const rToken = localStorage.getItem('refresh_token');
  if (!rToken) return null;
  try {
    const baseURL = import.meta.env.VITE_API_BASE_URL || '';
    const res = await axios.post<AuthTokenResponse>(
      `${baseURL}/api/v1/auth/refresh`,
      { refresh_token: rToken },
      { headers: { 'Content-Type': 'application/json' } }
    );
    if (res.data?.access_token) {
      setStoredTokens(res.data.access_token, res.data.refresh_token);
      return res.data.access_token;
    }
  } catch (err) {
    console.warn('Silent token refresh failed:', err);
  }
  return null;
};

// Queue for holding requests while token refresh is in flight
let isRefreshingToken = false;
let refreshSubscribers: Array<(token: string) => void> = [];

const subscribeTokenRefresh = (cb: (token: string) => void) => {
  refreshSubscribers.push(cb);
};

const onTokenRefreshed = (token: string) => {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
};

/**
 * Axios Response Interceptor:
 * Automatically refreshes expired access tokens using the refresh token so
 * employees are never logged out unexpectedly during their workday.
 * Only logs out when credentials are completely invalid or employee explicitly logs out.
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isExcluded =
      !originalRequest ||
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/refresh') ||
      originalRequest.url?.includes('/auth/register') ||
      originalRequest.url?.includes('/auth/forgot-password') ||
      originalRequest.url?.includes('/auth/reset-password');

    if (error.response?.status === 401 && !isExcluded && !originalRequest._retry) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        if (isRefreshingToken) {
          return new Promise((resolve) => {
            subscribeTokenRefresh((newToken: string) => {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
              resolve(api(originalRequest));
            });
          });
        }

        originalRequest._retry = true;
        isRefreshingToken = true;

        try {
          const newToken = await silentRefreshToken();
          isRefreshingToken = false;
          if (newToken) {
            onTokenRefreshed(newToken);
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return api(originalRequest);
          }
        } catch (refreshErr) {
          isRefreshingToken = false;
          refreshSubscribers = [];
        }
      }

      // If token refresh wasn't possible or failed, broadcast auth expired
      clearStoredTokens();
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('atm:auth-expired', { detail: error.response?.data }));
      }
    }
    return Promise.reject(error);
  }
);

// --- Authentication Endpoints ---
export const loginUser = async (credentials: LoginCredentials): Promise<AuthTokenResponse> => {
  const response = await api.post<AuthTokenResponse>('/api/v1/auth/login', credentials);
  if (response.data?.access_token) {
    setStoredTokens(response.data.access_token, response.data.refresh_token);
  }
  return response.data;
};

export const fetchCurrentUser = async (): Promise<AuthUser> => {
  const response = await api.get<AuthUser>('/api/v1/auth/me');
  return response.data;
};

export const registerUser = async (payload: any): Promise<AuthUser> => {
  const response = await api.post<AuthUser>('/api/v1/auth/register', payload);
  return response.data;
};

export const changePassword = async (payload: ChangePasswordPayload): Promise<AuthMessageResponse> => {
  const response = await api.post<AuthMessageResponse>('/api/v1/auth/change-password', payload);
  if (response.data?.access_token) {
    setStoredTokens(response.data.access_token, response.data.refresh_token);
  }
  return response.data;
};

export const requestForgotPassword = async (payload: ForgotPasswordPayload): Promise<AuthMessageResponse> => {
  const response = await api.post<AuthMessageResponse>('/api/v1/auth/forgot-password', payload);
  return response.data;
};

export const verifyResetCode = async (payload: VerifyResetCodePayload): Promise<AuthMessageResponse> => {
  const response = await api.post<AuthMessageResponse>('/api/v1/auth/verify-reset-code', payload);
  return response.data;
};

export const resetPassword = async (payload: ResetPasswordPayload): Promise<AuthMessageResponse> => {
  const response = await api.post<AuthMessageResponse>('/api/v1/auth/reset-password', payload);
  return response.data;
};

export const logoutUser = (): void => {
  clearStoredTokens();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('atm:auth-expired'));
  }
};

// --- General Platform Endpoints ---
export const fetchHealth = async (): Promise<HealthResponse> => {
  const response = await api.get<HealthResponse>('/api/v1/health');
  return response.data;
};

export const interpretCommand = async (
  command: string,
  activeActionId?: string,
  conversationId?: string,
  token?: string,
  boardId?: string,
  modelId?: string
): Promise<AIInterpretResponse> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const payload: any = { command };
  if (activeActionId) {
    payload.active_action_id = activeActionId;
  }
  if (conversationId) {
    payload.conversation_id = conversationId;
  }
  if (boardId) {
    payload.board_id = boardId;
  }
  if (modelId) {
    payload.model_id = modelId;
  }
  const response = await api.post<AIInterpretResponse>(
    '/api/v1/ai/interpret',
    payload,
    headers ? { headers } : undefined
  );
  return response.data;
};

// --- Phase 7A: Persistent Chat History & ChatGPT-style Sessions ---
export const fetchChatSessions = async (
  token?: string,
  boardId?: string
): Promise<{ sessions: ChatSession[]; total: number }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = boardId ? { board_id: boardId } : undefined;
  const response = await api.get<{ sessions: ChatSession[]; total: number }>(
    '/api/v1/ai/sessions',
    {
      headers: headers ? headers : undefined,
      params,
    }
  );
  return response.data;
};

export const fetchSessionChatHistory = async (
  sessionId: string,
  token?: string
): Promise<{ messages: any[]; total: number; conversation_id?: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<{ messages: any[]; total: number; conversation_id?: string }>(
    `/api/v1/ai/sessions/${sessionId}/history`,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const deleteChatSession = async (
  sessionId: string,
  token?: string
): Promise<{ status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.delete<{ status: string; message: string }>(
    `/api/v1/ai/sessions/${sessionId}`,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const renameChatSession = async (
  sessionId: string,
  title: string,
  token?: string
): Promise<{ status: string; message: string; title: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.patch<{ status: string; message: string; title: string }>(
    `/api/v1/ai/sessions/${sessionId}`,
    { title },
    headers ? { headers } : undefined
  );
  return response.data;
};

export const fetchChatHistory = async (
  conversationId?: string,
  token?: string
): Promise<{ messages: any[]; total: number; conversation_id?: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = conversationId ? { conversation_id: conversationId } : undefined;
  const response = await api.get<{ messages: any[]; total: number; conversation_id?: string }>(
    '/api/v1/ai/history',
    {
      headers: headers ? headers : undefined,
      params,
    }
  );
  return response.data;
};

export const clearChatHistory = async (token?: string): Promise<{ status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.delete<{ status: string; message: string }>(
    '/api/v1/ai/history',
    headers ? { headers } : undefined
  );
  return response.data;
};

// --- Phase 7A: Live Trello Tasks, Overview, Activities, and Workload Reports ---
export const fetchTrelloTasks = async (token?: string, boardId?: string, refresh?: boolean): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params: Record<string, any> = {};
  if (boardId) params.board_id = boardId;
  if (refresh) params.refresh = 'true';
  const response = await api.get('/api/v1/tasks/trello', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

export const fetchOverviewStats = async (token?: string, boardId?: string, refresh?: boolean): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params: Record<string, any> = {};
  if (boardId) params.board_id = boardId;
  if (refresh) params.refresh = 'true';
  const response = await api.get('/api/v1/overview/stats', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

export const fetchLiveActivities = async (token?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get('/api/v1/activities', headers ? { headers } : undefined);
  return response.data;
};

export const fetchWorkloadReport = async (token?: string, boardId?: string, refresh?: boolean): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params: Record<string, any> = {};
  if (boardId) params.board_id = boardId;
  if (refresh) params.refresh = 'true';
  const response = await api.get('/api/v1/reports/workload', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

export const fetchBoardTaskReport = async (
  token?: string,
  boardId?: string,
  fromDate?: string,
  toDate?: string,
  refresh?: boolean
): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params: Record<string, string> = {};
  if (boardId) params.board_id = boardId;
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;
  if (refresh) params.refresh = 'true';
  const response = await api.get('/api/v1/reports/board-tasks', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

export const fetchTeamWorkload = async (token?: string, boardId?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = boardId ? { board_id: boardId } : undefined;
  const response = await api.get('/api/v1/tasks/team', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

// --- Dynamic Trello Board Management ---
export const fetchBoards = async (token?: string): Promise<{ boards: Board[]; active_board_id: string; total: number }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<{ status: string; active_board_id: string; total: number; boards: Board[] }>(
    '/api/v1/boards',
    headers ? { headers } : undefined
  );
  return response.data;
};

export const fetchActiveBoard = async (token?: string): Promise<Board> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<Board>('/api/v1/boards/active', headers ? { headers } : undefined);
  return response.data;
};

export const addBoard = async (
  payload: { board_id: string; name?: string; desc?: string; url?: string },
  token?: string
): Promise<Board> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<Board>('/api/v1/boards', payload, headers ? { headers } : undefined);
  return response.data;
};

export const activateBoard = async (boardId: string, token?: string): Promise<Board> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<Board>(`/api/v1/boards/${boardId}/activate`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const deactivateBoard = async (boardId: string, token?: string): Promise<Board> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<Board>(`/api/v1/boards/${boardId}/deactivate`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const toggleBoardStatus = async (boardId: string, token?: string): Promise<Board> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<Board>(`/api/v1/boards/${boardId}/toggle`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const deleteBoard = async (boardId: string, token?: string): Promise<{ status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.delete<{ status: string; message: string }>(`/api/v1/boards/${boardId}`, headers ? { headers } : undefined);
  return response.data;
};

// --- Phase 4B: MCP Endpoints ---
export const fetchMcpServers = async (token?: string): Promise<MCPServer[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<{ servers: MCPServer[]; total: number }>('/api/v1/mcp/servers', headers ? { headers } : undefined);
  return response.data.servers;
};

export const registerMcpServer = async (payload: MCPServerRegisterPayload, token?: string): Promise<MCPServer> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<MCPServer>('/api/v1/mcp/servers', payload, headers ? { headers } : undefined);
  return response.data;
};

export const connectMcpServer = async (serverId: string, token?: string): Promise<{ status: string; latency_ms?: number }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post(`/api/v1/mcp/servers/${serverId}/connect`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const disconnectMcpServer = async (serverId: string, token?: string): Promise<{ status: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post(`/api/v1/mcp/servers/${serverId}/disconnect`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const discoverMcpTools = async (serverId: string, token?: string): Promise<MCPDiscoveryResult> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<MCPDiscoveryResult>(`/api/v1/mcp/servers/${serverId}/discover`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const deleteMcpServer = async (serverId: string, token?: string): Promise<void> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  await api.delete(`/api/v1/mcp/servers/${serverId}`, headers ? { headers } : undefined);
};

export const fetchRegisteredTools = async (token?: string): Promise<any[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<{ tools: any[]; total: number }>('/api/v1/tools', headers ? { headers } : undefined);
  return response.data.tools;
};

// --- Phase 6: Human-in-the-Loop Approvals ---
export const getApprovalPreview = async (actionId: string, token?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get(`/api/v1/approvals/${actionId}`, headers ? { headers } : undefined);
  return response.data;
};

export const confirmApproval = async (actionId: string, token?: string): Promise<ApprovalConfirmResult> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<ApprovalConfirmResult>(`/api/v1/approvals/${actionId}/confirm`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const editApproval = async (
  actionId: string,
  payload: ApprovalEditPayload,
  token?: string
): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.patch(`/api/v1/approvals/${actionId}`, payload, headers ? { headers } : undefined);
  return response.data;
};

export const cancelApproval = async (
  actionId: string,
  token?: string
): Promise<{ action_id: string; status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post(`/api/v1/approvals/${actionId}/cancel`, {}, headers ? { headers } : undefined);
  return response.data;
};

// --- Real-time Notifications ---
export const fetchNotifications = async (limit: number = 20, token?: string): Promise<NotificationsResponse> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<NotificationsResponse>(`/api/v1/notifications?limit=${limit}`, headers ? { headers } : undefined);
  return response.data;
};

export const markNotificationsRead = async (
  notificationId?: string,
  markAll: boolean = false,
  token?: string
): Promise<{ status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<{ status: string; message: string }>(
    '/api/v1/notifications/mark-read',
    { notification_id: notificationId, mark_all: markAll },
    headers ? { headers } : undefined
  );
  return response.data;
};

export const deleteNotificationApi = async (
  notificationId?: string,
  deleteAll: boolean = false,
  token?: string
): Promise<{ status: string; message: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<{ status: string; message: string }>(
    '/api/v1/notifications/delete',
    { notification_id: notificationId, delete_all: deleteAll },
    headers ? { headers } : undefined
  );
  return response.data;
};

// --- Employee Task Tracking & Performance (Modules 1, 2, 3, 4, 7) ---
export const fetchEmployeeSummaries = async (
  boardId?: string,
  token?: string
): Promise<EmployeeTaskReportSummary[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const url = boardId && boardId !== 'all'
    ? `/api/v1/employees/reports/summary?board_id=${encodeURIComponent(boardId)}`
    : '/api/v1/employees/reports/summary';
  const response = await api.get<EmployeeTaskReportSummary[]>(url, headers ? { headers } : undefined);
  return response.data;
};

export const fetchEmployeeReport = async (
  employeeId: string,
  params?: { boardId?: string; status?: string; fromDate?: string; toDate?: string },
  token?: string
): Promise<EmployeeTaskReportSummary> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const query = new URLSearchParams();
  if (params?.boardId && params.boardId !== 'all') query.append('board_id', params.boardId);
  if (params?.status && params.status !== 'all') query.append('status', params.status);
  if (params?.fromDate) query.append('from_date', params.fromDate);
  if (params?.toDate) query.append('to_date', params.toDate);
  const qStr = query.toString() ? `?${query.toString()}` : '';
  const response = await api.get<EmployeeTaskReportSummary>(`/api/v1/employees/${employeeId}/report${qStr}`, headers ? { headers } : undefined);
  return response.data;
};

export const fetchEmployeePerformance = async (
  employeeId: string,
  token?: string
): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get(`/api/v1/employees/${employeeId}/performance`, headers ? { headers } : undefined);
  return response.data;
};

export const fetchEmployeeLevelHistory = async (
  employeeId: string,
  token?: string
): Promise<EmployeeLevelHistoryItem[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<EmployeeLevelHistoryItem[]>(`/api/v1/employees/${employeeId}/performance/history`, headers ? { headers } : undefined);
  return response.data;
};

export const recalculateEmployeePerformance = async (
  employeeId: string,
  token?: string
): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post(`/api/v1/employees/${employeeId}/performance/recalculate`, {}, headers ? { headers } : undefined);
  return response.data;
};

export const fetchEmployeeAssignments = async (
  employeeId: string,
  params?: { boardId?: string; status?: string; fromDate?: string; toDate?: string },
  token?: string
): Promise<TaskAssignment[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const query = new URLSearchParams();
  if (params?.boardId && params.boardId !== 'all') query.append('board_id', params.boardId);
  if (params?.status && params.status !== 'all') query.append('status', params.status);
  if (params?.fromDate) query.append('from_date', params.fromDate);
  if (params?.toDate) query.append('to_date', params.toDate);
  const qStr = query.toString() ? `?${query.toString()}` : '';
  const response = await api.get<TaskAssignment[]>(`/api/v1/task-assignments/employee/${employeeId}${qStr}`, headers ? { headers } : undefined);
  return response.data;
};

export const createTaskAssignment = async (
  payload: {
    employee_id: string;
    board_id: string;
    trello_card_id: string;
    task_title: string;
    task_description?: string;
    due_date?: string;
    board_name?: string;
    trello_card_url?: string;
  },
  token?: string
): Promise<TaskAssignment> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<TaskAssignment>('/api/v1/task-assignments', payload, headers ? { headers } : undefined);
  return response.data;
};

export const updateAssignmentDueDate = async (
  assignmentId: string,
  dueDate: string,
  reason?: string,
  token?: string
): Promise<TaskAssignment> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.patch<TaskAssignment>(
    `/api/v1/task-assignments/${assignmentId}/due-date`,
    { due_date: dueDate, reason },
    headers ? { headers } : undefined
  );
  return response.data;
};

export const startAssignmentTask = async (
  assignmentId: string,
  token?: string
): Promise<TaskAssignment> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<TaskAssignment>(
    `/api/v1/task-assignments/${assignmentId}/start`,
    {},
    headers ? { headers } : undefined
  );
  return response.data;
};

export const completeAssignmentTask = async (
  assignmentId: string,
  token?: string
): Promise<TaskAssignment> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<TaskAssignment>(
    `/api/v1/task-assignments/${assignmentId}/complete`,
    {},
    headers ? { headers } : undefined
  );
  return response.data;
};

export const fetchAssignmentHistory = async (
  assignmentId: string,
  token?: string
): Promise<TaskAssignmentHistoryItem[]> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<TaskAssignmentHistoryItem[]>(
    `/api/v1/task-assignments/${assignmentId}/history`,
    headers ? { headers } : undefined
  );
  return response.data;
};

// ==========================================
// Task Description Templates Management APIs
// ==========================================

export const fetchTaskTemplates = async (
  token?: string
): Promise<TaskTemplatesResponse> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<TaskTemplatesResponse>(
    '/api/v1/templates',
    headers ? { headers } : undefined
  );
  return response.data;
};

export const createTaskTemplate = async (
  payload: {
    name: string;
    category?: string;
    keywords: string[];
    description_template: string;
  },
  token?: string
): Promise<{ status: string; message: string; template: TaskTemplate }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<{ status: string; message: string; template: TaskTemplate }>(
    '/api/v1/templates',
    payload,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const updateTaskTemplate = async (
  templateId: string,
  payload: {
    name?: string;
    category?: string;
    keywords?: string[];
    description_template?: string;
  },
  token?: string
): Promise<{ status: string; message: string; template: TaskTemplate }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.put<{ status: string; message: string; template: TaskTemplate }>(
    `/api/v1/templates/${templateId}`,
    payload,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const deleteTaskTemplate = async (
  templateId: string,
  token?: string
): Promise<{ status: string; message: string; deleted_id: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.delete<{ status: string; message: string; deleted_id: string }>(
    `/api/v1/templates/${templateId}`,
    headers ? { headers } : undefined
  );
  return response.data;
};

// ==========================================
// Executive PDF Reports & Email APIs
// ==========================================

export const downloadBoardWeeklyPdf = async (
  boardId?: string,
  token?: string
): Promise<Blob> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get('/api/v1/reports/pdf/board/download', {
    params: boardId ? { board_id: boardId } : {},
    responseType: 'blob',
    headers,
  });
  return response.data;
};

export const sendBoardWeeklyPdfEmail = async (
  payload: { board_id?: string; admin_email?: string },
  token?: string
): Promise<{ status: string; message: string; recipient: string; filename: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<{ status: string; message: string; recipient: string; filename: string }>(
    '/api/v1/reports/pdf/board/send-email',
    payload,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const downloadEmployeeWeeklyPdf = async (
  employeeId: string,
  employeeName?: string,
  boardId?: string,
  fromDate?: string,
  toDate?: string,
  token?: string
): Promise<Blob> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get('/api/v1/reports/pdf/employee/download', {
    params: {
      employee_id: employeeId,
      ...(employeeName ? { employee_name: employeeName } : {}),
      ...(boardId ? { board_id: boardId } : {}),
      ...(fromDate ? { from_date: fromDate } : {}),
      ...(toDate ? { to_date: toDate } : {}),
    },
    responseType: 'blob',
    headers,
  });
  return response.data;
};

export const sendEmployeeWeeklyPdfEmail = async (
  payload: {
    employee_id: string;
    employee_name?: string;
    board_id?: string;
    admin_email?: string;
    from_date?: string;
    to_date?: string;
  },
  token?: string
): Promise<{ status: string; message: string; recipient: string; filename: string }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.post<{ status: string; message: string; recipient: string; filename: string }>(
    '/api/v1/reports/pdf/employee/send-email',
    payload,
    headers ? { headers } : undefined
  );
  return response.data;
};

export const fetchReportPreviewSummary = async (
  context: 'board' | 'employee',
  params?: {
    employee_id?: string;
    employee_name?: string;
    board_id?: string;
    from_date?: string;
    to_date?: string;
  },
  token?: string
): Promise<{ status: string; context: string; summary: any }> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const response = await api.get<{ status: string; context: string; summary: any }>(
    '/api/v1/reports/pdf/preview-summary',
    {
      params: { context, ...params },
      headers,
    }
  );
  return response.data;
};

export default api;
