import axios from 'axios';
import {
  AIInterpretResponse,
  ApprovalConfirmResult,
  ApprovalEditPayload,
  AuthTokenResponse,
  AuthUser,
  Board,
  ChatSession,
  HealthResponse,
  LoginCredentials,
  MCPDiscoveryResult,
  MCPServer,
  MCPServerRegisterPayload,
  NotificationsResponse,
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
 * Axios Response Interceptor:
 * Broadcasts an event when 401 Unauthorized occurs so UI can update state cleanly.
 */
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
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
  boardId?: string
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
export const fetchTrelloTasks = async (token?: string, boardId?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = boardId ? { board_id: boardId } : undefined;
  const response = await api.get('/api/v1/tasks/trello', {
    headers: headers ? headers : undefined,
    params,
  });
  return response.data;
};

export const fetchOverviewStats = async (token?: string, boardId?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = boardId ? { board_id: boardId } : undefined;
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

export const fetchWorkloadReport = async (token?: string, boardId?: string): Promise<any> => {
  const headers = token ? getAuthHeaders(token) : undefined;
  const params = boardId ? { board_id: boardId } : undefined;
  const response = await api.get('/api/v1/reports/workload', {
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

export default api;
