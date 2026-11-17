import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Plus,
  Bot,
  User,
  ShieldAlert,
  CheckCircle,
  XCircle,
  Wrench,
  RefreshCw,
  Edit3,
  ExternalLink,
  Calendar,
  Flag,
  Layers,
  Sparkles,
  AlertTriangle,
  Loader2,
  Check,
  Clock,
  ListTodo,
  Search,
  CheckCircle2,
  MessageSquare,
  Trash2,
  Terminal,
  Cpu,
  ShieldCheck,
  Zap,
  SlidersHorizontal,
  CornerDownLeft,
  X,
} from 'lucide-react';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { ChatMessage, ActionApprovalPreview, ApprovalEditPayload, ChatSession } from '../types';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import {
  interpretCommand,
  confirmApproval,
  editApproval,
  cancelApproval,
  fetchChatHistory,
  clearChatHistory,
  fetchChatSessions,
  fetchSessionChatHistory,
  deleteChatSession,
} from '../services/api';

const WELCOME_MESSAGE: ChatMessage = {
  id: 'MSG-WELCOME',
  sender: 'assistant',
  content: `Hello! I am your Agentic Task Assistant. You can manage tasks naturally through conversation:

• Create tasks: "Create a task card Login API" or "Create a high-priority task for JWT authentication"
• Move cards: "Move Login API to Doing"
• Search & query: "Show cards in To Do" or "Find task Login API"
• Update tasks: "Update description of Login API"
• Archive cards: "Mark Login API as completed"
• Conversational approval: You can simply reply "Confirm", "Cancel", or "Change priority to High"

All write operations present a live preview draft for your confirmation before executing via Trello MCP.`,
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  executionStatus: 'EXECUTED',
};

export const AIAssistantPage: React.FC = () => {
  const { isAuthenticated, openLoginModal, user } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isSessionsLoading, setIsSessionsLoading] = useState<boolean>(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<{
    title: string;
    description: string;
    listName: string;
    priority: string;
    dueDate: string;
  }>({
    title: '',
    description: '',
    listName: 'To Do',
    priority: 'MEDIUM',
    dueDate: '',
  });

  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const createNewSessionId = () =>
    `SES-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 7)}`;

  // Robust UTC parser ensuring ISO dates without 'Z' are treated as UTC
  const parseAsUtcDate = (dateVal?: string | Date): Date | null => {
    if (!dateVal) return null;
    if (dateVal instanceof Date) return isNaN(dateVal.getTime()) ? null : dateVal;
    let str = String(dateVal).trim();
    if (!str) return null;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(str) && !str.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(str)) {
      str += 'Z';
    }
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  };

  const formatSessionTime = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const d = parseAsUtcDate(dateStr);
      if (!d) return '';
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      if (diffMs < 0) return 'Just now';
      const diffSecs = Math.floor(diffMs / 1000);
      if (diffSecs < 60) return 'Just now';
      const diffMins = Math.floor(diffSecs / 60);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays === 1) return 'Yesterday';
      if (diffDays < 7) return `${diffDays}d ago`;
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  // Format due date for presentation (e.g. 2026-11-26 -> Nov 26, 2026)
  const formatDueDateDisplay = (dateStr?: string) => {
    if (!dateStr || dateStr === 'No due date') return 'No due date';
    try {
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        const year = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        const d = new Date(year, month, day);
        if (!isNaN(d.getTime())) {
          return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }
      }
      const d = new Date(dateStr);
      if (!isNaN(d.getTime())) {
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
      }
    } catch {
      // fallback
    }
    return dateStr;
  };

  // Convert backend ChatMessage to frontend ChatMessage
  const mapBackendMessage = (m: any): ChatMessage => {
    let approvalPreview: ActionApprovalPreview | undefined = undefined;
    const rawPreview = m.approval_preview || m.approvalPreview;
    if (rawPreview) {
      const draft = rawPreview.draft || rawPreview;
      const rawParams = rawPreview.parameters || draft.parameters || m.parameters || {};
      const resolvedDue =
        draft.due_date ||
        rawPreview.dueDate ||
        rawPreview.due_date ||
        rawParams.new_due_date ||
        rawParams.due_date ||
        rawParams.due ||
        rawParams.date ||
        undefined;

      approvalPreview = {
        actionId: rawPreview.action_id || rawPreview.actionId || m.parameters?.action_id || 'ACT-LIVE',
        actionType: rawPreview.action_type || rawPreview.actionType || 'MUTATION',
        targetEntity: rawPreview.target_entity || rawPreview.tool_name || 'Trello Card',
        cardName: draft.title || rawPreview.cardName || draft.card_name || 'Task',
        description: draft.description || rawPreview.description || '',
        boardName: draft.board_name || rawPreview.boardName || 'Configured Trello Board',
        boardId: draft.board_id || rawPreview.boardId,
        listName: draft.list_name || rawPreview.listName || 'To Do',
        listId: draft.list_id || rawPreview.listId,
        priority: draft.priority || rawPreview.priority || 'MEDIUM',
        dueDate: resolvedDue,
        parameters: rawPreview.parameters || draft.parameters || {},
        status: (rawPreview.status || 'PENDING') as any,
        createdAt: rawPreview.created_at || rawPreview.createdAt || new Date().toISOString(),
        cardUrl: rawPreview.card_url || rawPreview.cardUrl,
        cardId: rawPreview.card_id || rawPreview.cardId,
        errorMessage: rawPreview.error_message || rawPreview.errorMessage,
        executionResult: rawPreview.execution_result || rawPreview.executionResult,
      };
    }

    // Resolve clean local timestamp in user's local timezone
    let resolvedTime = '';
    const utcDate = parseAsUtcDate(m.created_at);
    if (utcDate) {
      resolvedTime = utcDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (m.timestamp && /^\d{4}-\d{2}-\d{2}T/.test(m.timestamp)) {
      const d = parseAsUtcDate(m.timestamp);
      if (d) resolvedTime = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    if (!resolvedTime) {
      resolvedTime = m.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    return {
      id: m.id || `MSG-${Date.now()}-${Math.random()}`,
      conversation_id: m.conversation_id,
      sender: m.sender || 'assistant',
      content: m.content || '',
      timestamp: resolvedTime,
      created_at: m.created_at,
      intent: m.intent,
      parameters: m.parameters,
      isLiveApiResult: true,
      executionStatus: (m.execution_status || (approvalPreview ? 'AWAITING_APPROVAL' : 'EXECUTED')) as any,
      approvalPreview,
      executionResult: m.execution_result || m.executionResult,
    };
  };

  const loadSessionMessages = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setActiveActionId(null);
    setEditingActionId(null);
    try {
      setIsLoading(true);
      const data = await fetchSessionChatHistory(sessionId);
      if (data && data.messages && data.messages.length > 0) {
        const mapped = data.messages.map(mapBackendMessage);
        setMessages(mapped);

        const pendingMsg = [...mapped].reverse().find(
          (msg) => msg.approvalPreview && msg.approvalPreview.status === 'PENDING'
        );
        if (pendingMsg?.approvalPreview?.actionId) {
          setActiveActionId(pendingMsg.approvalPreview.actionId);
        }
      } else {
        setMessages([WELCOME_MESSAGE]);
      }
    } catch (err) {
      console.error('Failed to load session messages:', err);
      setMessages([WELCOME_MESSAGE]);
    } finally {
      setIsLoading(false);
    }
  };

  const loadSessionsAndSelect = async (preferredSessionId?: string) => {
    if (!isAuthenticated) return;
    try {
      setIsSessionsLoading(true);
      const res = await fetchChatSessions(undefined, activeBoardId || undefined);
      const sessionList = res.sessions || [];
      setSessions(sessionList);

      const targetId = preferredSessionId || (sessionList.length > 0 ? sessionList[0].id : null);
      if (targetId) {
        await loadSessionMessages(targetId);
      } else {
        const freshId = createNewSessionId();
        setCurrentSessionId(freshId);
        setMessages([WELCOME_MESSAGE]);
        setActiveActionId(null);
      }
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
    } finally {
      setIsSessionsLoading(false);
    }
  };

  // Load chat sessions from MongoDB Atlas on mount, auth change, or active board change
  useEffect(() => {
    loadSessionsAndSelect();
  }, [isAuthenticated, activeBoardId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSendMessage = async (e?: React.FormEvent, directText?: string) => {
    if (e) e.preventDefault();
    const query = (directText || inputValue).trim();
    if (!query || isLoading) return;

    if (!isAuthenticated) {
      openLoginModal();
      return;
    }

    setInputValue('');

    const effectiveSessionId = currentSessionId || createNewSessionId();
    if (!currentSessionId) {
      setCurrentSessionId(effectiveSessionId);
    }

    const newUserMsg: ChatMessage = {
      id: `MSG-${Date.now()}`,
      conversation_id: effectiveSessionId,
      sender: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      const res = await interpretCommand(
        query,
        activeActionId || undefined,
        effectiveSessionId,
        undefined,
        activeBoardId || undefined
      );
      setIsLoading(false);

      if (res.conversation_id && res.conversation_id !== currentSessionId) {
        setCurrentSessionId(res.conversation_id);
      }

      let content = res.conversational_message || '';
      if (!content) {
        if (res.requires_clarification) {
          content = res.clarification_message || 'I could not determine the exact tool or required parameters. Could you please clarify your request?';
        } else if (res.approval_required) {
          content = `I have parsed your request: intent is "${res.intent}". A structured draft has been prepared below. Please review the details and confirm to create it in Trello.`;
        } else {
          content = `I have executed your request: intent is "${res.intent}".`;
        }
      }

      // Handle conversational confirmation or cancellation updates on prior messages
      if (res.intent === 'confirm_action' && res.action_id) {
        setActiveActionId(null);
        setMessages((prev) =>
          prev.map((m) => {
            if (m.approvalPreview && m.approvalPreview.actionId === res.action_id) {
              const execRes = res.execution_result || {};
              const cardObj = execRes.result?.card || {};
              return {
                ...m,
                approvalPreview: {
                  ...m.approvalPreview,
                  status: 'EXECUTED',
                  cardUrl: cardObj.url || m.approvalPreview.cardUrl,
                  cardId: cardObj.id || m.approvalPreview.cardId,
                  executionResult: execRes,
                },
                executionStatus: 'EXECUTED',
              };
            }
            return m;
          })
        );
      } else if (res.intent === 'cancel_action' && res.action_id) {
        setActiveActionId(null);
        setMessages((prev) =>
          prev.map((m) => {
            if (m.approvalPreview && m.approvalPreview.actionId === res.action_id) {
              return {
                ...m,
                approvalPreview: {
                  ...m.approvalPreview,
                  status: 'REJECTED',
                },
                executionStatus: 'REJECTED',
              };
            }
            return m;
          })
        );
      }

      let approvalPreview: ActionApprovalPreview | undefined = undefined;
      if (res.execution_preview) {
        const p = res.execution_preview;
        const draft = p.draft || ({} as any);
        const resolvedActionId = res.action_id || p.action_id;
        setActiveActionId(resolvedActionId);

        const rawParams = p.parameters || draft.parameters || res.parameters || {};
        const resolvedDue =
          draft.due_date ||
          (p.parameters?.due_date as string) ||
          (rawParams.new_due_date as string) ||
          (rawParams.due_date as string) ||
          (rawParams.due as string) ||
          (rawParams.date as string) ||
          undefined;

        approvalPreview = {
          actionId: resolvedActionId,
          actionType: (p.action_type || res.intent.toUpperCase() || 'CREATE_CARD') as any,
          targetEntity: p.tool_name || 'Trello Card',
          cardName: draft.title || (p.parameters?.name || p.parameters?.card_name || 'Sprint Task') as string,
          description: draft.description || (p.parameters?.desc || ''),
          boardName: draft.board_name || 'Configured Trello Board',
          boardId: draft.board_id || undefined,
          listName: draft.list_name || (p.parameters?.list_name || p.parameters?.target_status || 'To Do') as string,
          listId: draft.list_id || undefined,
          priority: draft.priority || (p.parameters?.priority as string) || 'MEDIUM',
          dueDate: resolvedDue,
          parameters: draft.parameters || p.parameters || {},
          status: (p.status || 'PENDING') as any,
          createdAt: new Date().toISOString(),
        };
      }

      const assistantMsg: ChatMessage = {
        id: `MSG-${Date.now() + 1}`,
        sender: 'assistant',
        content,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        intent: res.intent,
        parameters: res.parameters,
        isLiveApiResult: true,
        discoveredTool: res.selected_tool_id
          ? {
              name: res.selected_tool_id,
              category: res.execution_preview?.category || 'TRELLO',
              relevanceScore: res.confidence,
              explanation: `Discovered from MongoDB Atlas tool registry. Intent: ${res.intent}.`,
            }
          : undefined,
        executionStatus: res.approval_required ? 'AWAITING_APPROVAL' : 'EXECUTED',
        approvalPreview,
        executionResult: res.execution_result,
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Refresh session list so updated title & timestamps appear in sidebar
      fetchChatSessions().then((sRes) => {
        if (sRes?.sessions) {
          setSessions(sRes.sessions);
        }
      }).catch(() => {});
    } catch (err: any) {
      setIsLoading(false);
      const isAuthError = err.response?.status === 401;
      const errorDetail = err.response?.data?.error?.message || err.message || 'Error communicating with AI interpretation API.';

      const errorMsg: ChatMessage = {
        id: `MSG-ERR-${Date.now()}`,
        sender: 'assistant',
        content: isAuthError
          ? 'Authentication required or token expired. Please login to authenticate AI requests.'
          : `API Error: ${errorDetail}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
      if (isAuthError) {
        openLoginModal();
      }
    }
  };

  const handleActionConfirm = async (actionId: string) => {
    setActionLoading((prev) => ({ ...prev, [actionId]: true }));
    try {
      const res = await confirmApproval(actionId);
      setActiveActionId(null);
      setMessages((prev) =>
        prev.map((m) => {
          if (m.approvalPreview?.actionId === actionId) {
            return {
              ...m,
              approvalPreview: {
                ...m.approvalPreview,
                status: 'EXECUTED',
                cardUrl: res.card_url,
                cardId: res.card_id,
                executionResult: res.execution_result,
              },
              executionStatus: 'EXECUTED',
            };
          }
          return m;
        })
      );
    } catch (err: any) {
      const errMsg = err.response?.data?.error?.message || err.message || 'Execution failed';
      setMessages((prev) =>
        prev.map((m) => {
          if (m.approvalPreview?.actionId === actionId) {
            return {
              ...m,
              approvalPreview: {
                ...m.approvalPreview,
                status: 'FAILED',
                errorMessage: errMsg,
              },
            };
          }
          return m;
        })
      );
    } finally {
      setActionLoading((prev) => ({ ...prev, [actionId]: false }));
    }
  };

  const handleActionCancel = async (actionId: string) => {
    setActionLoading((prev) => ({ ...prev, [actionId]: true }));
    try {
      await cancelApproval(actionId);
      setActiveActionId(null);
      setMessages((prev) =>
        prev.map((m) => {
          if (m.approvalPreview?.actionId === actionId) {
            return {
              ...m,
              approvalPreview: {
                ...m.approvalPreview,
                status: 'REJECTED',
              },
              executionStatus: 'REJECTED',
            };
          }
          return m;
        })
      );
    } catch (err: any) {
      console.error('Cancel failed', err);
    } finally {
      setActionLoading((prev) => ({ ...prev, [actionId]: false }));
    }
  };

  const handleStartEdit = (preview: ActionApprovalPreview) => {
    setEditingActionId(preview.actionId);
    setEditFormData({
      title: preview.cardName || '',
      description: preview.description || '',
      listName: preview.listName || 'To Do',
      priority: preview.priority || 'MEDIUM',
      dueDate: preview.dueDate || '',
    });
  };

  const handleSaveEdit = async (actionId: string) => {
    setActionLoading((prev) => ({ ...prev, [actionId]: true }));
    try {
      const payload: ApprovalEditPayload = {
        title: editFormData.title,
        description: editFormData.description,
        list_name: editFormData.listName,
        priority: editFormData.priority,
        due_date: editFormData.dueDate || undefined,
      };
      const updated = await editApproval(actionId, payload);
      setMessages((prev) =>
        prev.map((m) => {
          if (m.approvalPreview?.actionId === actionId) {
            return {
              ...m,
              approvalPreview: {
                ...m.approvalPreview,
                cardName: updated.draft?.title || editFormData.title,
                description: updated.draft?.description || editFormData.description,
                listName: updated.draft?.list_name || editFormData.listName,
                priority: updated.draft?.priority || editFormData.priority,
                dueDate: updated.draft?.due_date || editFormData.dueDate,
                parameters: updated.draft?.parameters || m.approvalPreview.parameters,
              },
            };
          }
          return m;
        })
      );
      setEditingActionId(null);
    } catch (err: any) {
      alert(err.response?.data?.error?.message || 'Failed to update action draft.');
    } finally {
      setActionLoading((prev) => ({ ...prev, [actionId]: false }));
    }
  };

  const handleNewConversation = () => {
    const freshId = createNewSessionId();
    setCurrentSessionId(freshId);
    setMessages([WELCOME_MESSAGE]);
    setActiveActionId(null);
    setEditingActionId(null);
    setInputValue('');
  };

  const handleSelectSession = async (session: ChatSession) => {
    if (session.id === currentSessionId && messages.length > 1) return;
    await loadSessionMessages(session.id);
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!window.confirm('Delete this chat conversation?')) return;
    try {
      await deleteChatSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      if (currentSessionId === sessionId) {
        if (remaining.length > 0) {
          await loadSessionMessages(remaining[0].id);
        } else {
          handleNewConversation();
        }
      }
    } catch (err) {
      console.error('Failed to delete chat session:', err);
    }
  };

  const handleClearAllHistory = async () => {
    if (!window.confirm('Clear all conversation history? This cannot be undone.')) return;
    try {
      if (isAuthenticated) {
        await clearChatHistory();
      }
      setSessions([]);
      handleNewConversation();
    } catch (err) {
      console.error('Failed to clear chat history:', err);
    }
  };

  const samplePrompts = [
    { label: 'Create Task Card', icon: '✦', prompt: 'Create a task card Login API' },
    { label: 'Set High Priority', icon: '⚡', prompt: 'Create a high-priority task for JWT authentication' },
    { label: 'Update Due Date', icon: '📅', prompt: 'add due date on the JWT authentication card date is 26 november 2026' },
    { label: 'Assign Member', icon: '👤', prompt: 'assign member sourabh mishra to JWT authentication card' },
    { label: 'Move to Doing', icon: '➔', prompt: 'Move Login API card to Doing' },
    { label: 'Show To Do Tasks', icon: '📋', prompt: 'Show cards in the To Do list' },
  ];

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentSessionTitle = currentSession?.title || 'Active Mission';

  const renderMissionLogs = (isMobile = false) => (
    <>
      <div className="p-3 border-b border-slate-100 dark:border-slate-800/80 flex items-center justify-between shrink-0">
        <button
          type="button"
          onClick={handleNewConversation}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-xs transition"
          title="New Chat"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Chat</span>
        </button>

        <button
          type="button"
          onClick={() => setIsSidebarOpen(false)}
          className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-800 transition"
          title="Hide Chats"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>Hide</span>
        </button>
      </div>

      <div className="p-2 flex-1 overflow-y-auto space-y-1.5 text-xs min-h-0">
        {isSessionsLoading ? (
          <div className="p-8 text-center text-slate-400 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-4 h-4 animate-spin text-emerald-500" />
            <span className="text-xs font-mono">Syncing Atlas logs...</span>
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-8 text-center space-y-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center justify-center mx-auto">
              <Terminal className="w-4 h-4" />
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              No active mission logs. Start typing a command to initialize a new thread!
            </p>
          </div>
        ) : (
          sessions.map((sess) => {
            const isActive = sess.id === currentSessionId;
            return (
              <div
                key={sess.id}
                onClick={() => {
                  handleSelectSession(sess);
                  if (isMobile) setIsSidebarOpen(false);
                }}
                className={`group relative flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all text-xs ${
                  isActive
                    ? 'bg-gradient-to-r from-emerald-500/15 via-emerald-500/5 to-transparent text-emerald-400 font-medium border border-emerald-500/40 shadow-xs'
                    : 'hover:bg-slate-100 dark:hover:bg-slate-800/60 text-slate-700 dark:text-slate-300 border border-transparent'
                }`}
              >
                {isActive && (
                  <div className="absolute left-0 top-2 bottom-2 w-1 bg-emerald-500 rounded-r-full"></div>
                )}
                <div className="flex items-center space-x-2.5 min-w-0 pr-6 pl-1">
                  <MessageSquare
                    className={`w-3.5 h-3.5 shrink-0 ${
                      isActive ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  />
                  <div className="min-w-0">
                    <span className="block truncate text-xs font-medium" title={sess.title}>
                      {sess.title || 'Conversation'}
                    </span>
                    <span className="block text-[10px] text-slate-400 font-mono mt-0.5">
                      {formatSessionTime(sess.updated_at || sess.created_at)}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(e, sess.id);
                  }}
                  title="Delete Mission"
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      <div className="p-3 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/50 text-xs space-y-2 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium font-mono">
              Atlas Persistent
            </span>
          </div>
          <button
            type="button"
            onClick={handleClearAllHistory}
            className="text-[10px] text-slate-400 hover:text-rose-400 transition-colors font-medium"
          >
            Clear All
          </button>
        </div>
        <span className="text-[10px] text-slate-400 block font-mono truncate">
          User: {user?.email || 'Authenticated'}
        </span>
      </div>
    </>
  );

  return (
    <div className="h-full flex-1 min-h-0 flex flex-col">
      {/* Main Studio Dual-Panel */}
      <div className="flex-1 flex gap-4 min-h-0 relative">
        {/* Mobile/Tablet Slide-over Drawer for Mission Logs */}
        {isSidebarOpen && (
          <div className="fixed inset-0 z-50 lg:hidden flex">
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
              onClick={() => setIsSidebarOpen(false)}
            />
            <div className="relative z-10 w-72 max-w-[85vw] h-full bg-white dark:bg-[#0c121e] border-r border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col justify-between animate-in slide-in-from-left duration-200">
              {renderMissionLogs(true)}
            </div>
          </div>
        )}

        {/* Desktop Left: Mission Logs & Session Hub */}
        {isSidebarOpen && (
          <div className="w-72 hidden lg:flex flex-col justify-between shrink-0 bg-white/90 dark:bg-[#0c121e]/90 border border-slate-200/80 dark:border-slate-800/80 rounded-2xl overflow-hidden shadow-sm transition-all">
            {renderMissionLogs(false)}
          </div>
        )}

        {/* Right: Active Command & Execution Deck */}
        <div className="flex-1 flex flex-col justify-between overflow-hidden bg-white/95 dark:bg-[#0c121e]/95 border border-slate-200/80 dark:border-slate-800/80 rounded-2xl shadow-sm">
          {/* Thread Header Bar */}
          <div className="h-14 px-3 sm:px-6 border-b border-slate-100 dark:border-slate-800/80 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/30">
            <div className="flex items-center space-x-2.5 sm:space-x-3 min-w-0">
              {!isSidebarOpen && (
                <button
                  type="button"
                  onClick={() => setIsSidebarOpen(true)}
                  className="p-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-800 transition flex items-center space-x-1.5 text-xs shrink-0"
                  title="Show Chats"
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Chats</span>
                </button>
              )}
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-emerald-500/20 via-teal-500/20 to-violet-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center space-x-2">
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide truncate">
                    {currentSessionTitle}
                  </h3>
                  {activeBoard && (
                    <span
                      title={`Active Board: ${activeBoard.name} (${activeBoard.board_id})`}
                      className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 truncate max-w-[160px]"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1 shrink-0" />
                      <span className="truncate">{activeBoard.name}</span>
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-slate-400 font-mono flex items-center space-x-1.5 truncate">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      isAuthenticated ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
                    }`}
                  ></span>
                  <span className="hidden sm:inline truncate">
                    {isAuthenticated
                      ? 'Live Safe Mutation Gate • Human-in-the-Loop Active'
                      : 'Sign In Required for Live AI Commands'}
                  </span>
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              {!isAuthenticated && (
                <Button variant="primary" size="sm" onClick={openLoginModal}>
                  Sign In
                </Button>
              )}
            </div>
          </div>

          {/* Interactive Messages Stream */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-5 md:p-6 space-y-4 sm:space-y-6">
            {messages.map((msg) => (
              <div key={msg.id} className="w-full">
                {msg.sender === 'user' ? (
                  /* Operator (User) Command Card */
                  <div className="flex justify-end">
                    <div className="max-w-2xl w-full bg-slate-900/90 dark:bg-[#0a0f18] border border-emerald-500/30 rounded-2xl p-3.5 sm:p-4 shadow-md space-y-2">
                      <div className="flex items-center justify-between text-[10px] pb-2 border-b border-slate-800/80">
                        <div className="flex items-center space-x-1.5 text-emerald-400 font-mono">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                          <span className="uppercase tracking-wider font-semibold">Operator Command</span>
                        </div>
                        <span className="text-slate-400 font-mono flex items-center space-x-1">
                          <Clock className="w-3 h-3 text-slate-500" />
                          <span>{msg.timestamp}</span>
                        </span>
                      </div>
                      <div className="flex items-start space-x-2 pt-1">
                        <span className="text-emerald-400 font-mono font-bold text-sm leading-none mt-0.5 select-none">
                          &gt;
                        </span>
                        <p className="text-xs font-medium text-slate-100 leading-relaxed font-sans">
                          {msg.content}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Agent Mission Execution Card */
                  <div className="flex justify-start">
                    <div className="max-w-3xl w-full bg-white/90 dark:bg-[#0d1424]/90 border border-slate-200/80 dark:border-slate-800/80 rounded-2xl p-3.5 sm:p-5 shadow-md space-y-3 sm:space-y-4">
                      {/* Agent Header */}
                      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 pb-3">
                        <div className="flex items-center space-x-2.5">
                          <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-emerald-500/20 via-teal-500/20 to-violet-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
                            <Bot className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="text-xs font-bold text-slate-900 dark:text-slate-100 tracking-wide block">
                              Agentic Orchestrator Node
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              Intent Pipeline & Trello MCP Integration
                            </span>
                          </div>
                        </div>
                        <span className="text-[10px] text-slate-400 font-mono flex items-center space-x-1">
                          <Clock className="w-3 h-3 text-slate-500" />
                          <span>{msg.timestamp}</span>
                        </span>
                      </div>

                      {/* Main Message Content */}
                      <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
                        {msg.content}
                      </p>

                      {/* Tool Selection Badge */}
                      {msg.discoveredTool && (
                        <div className="p-3 bg-violet-500/5 border border-violet-500/20 rounded-xl space-y-1.5 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="flex items-center space-x-1.5 font-semibold text-violet-300">
                              <Wrench className="w-3.5 h-3.5 text-violet-400" />
                              <span>Tool Discovered:</span>
                              <code className="px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300 font-mono text-[11px] border border-violet-500/30">
                                {msg.discoveredTool.name}
                              </code>
                            </span>
                            <span className="text-[10px] text-emerald-400 font-mono font-semibold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                              {Math.round(msg.discoveredTool.relevanceScore * 100)}% Match
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 leading-relaxed">
                            {msg.discoveredTool.explanation}
                          </p>
                        </div>
                      )}

                      {/* Extracted Parameters Matrix */}
                      {msg.parameters && Object.keys(msg.parameters).length > 0 && (
                        <div className="p-3 bg-slate-50 dark:bg-slate-900/60 border border-slate-200/80 dark:border-slate-800/80 rounded-xl space-y-1.5 text-xs">
                          <span className="text-[10px] text-slate-400 font-mono font-semibold uppercase tracking-wider block">
                            Extracted Parameters Matrix
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(msg.parameters).map(([key, value]) => (
                              <span
                                key={key}
                                className="inline-flex items-center px-2.5 py-1 rounded-lg bg-slate-200/70 dark:bg-slate-800 text-slate-800 dark:text-slate-200 text-[11px] font-mono border border-slate-300/40 dark:border-slate-700/60"
                              >
                                <span className="text-slate-400 mr-1.5">{key}:</span>
                                <span className="text-emerald-400 font-semibold">{String(value)}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Read Operation Results: Structured Card List */}
                      {msg.executionResult && msg.executionResult.cards && Array.isArray(msg.executionResult.cards) && (
                        <div className="p-3.5 bg-slate-100/70 dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-xl space-y-2.5 shadow-xs">
                          <div className="flex items-center justify-between border-b border-slate-200/60 dark:border-slate-800 pb-2">
                            <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 flex items-center space-x-1.5">
                              <ListTodo className="w-3.5 h-3.5 text-emerald-500" />
                              <span>Live Trello Cards ({msg.executionResult.cards.length})</span>
                            </span>
                            <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                              Synced via MCP
                            </span>
                          </div>
                          <div className="space-y-1.5 max-h-56 overflow-y-auto">
                            {msg.executionResult.cards.length === 0 ? (
                              <p className="text-[11px] text-slate-400 italic">No matching cards found on board.</p>
                            ) : (
                              msg.executionResult.cards.map((card: any, cIdx: number) => (
                                <div
                                  key={card.id || cIdx}
                                  className="p-2.5 rounded-lg bg-white dark:bg-[#111827] border border-slate-200/80 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800/80 transition"
                                >
                                  <div className="min-w-0 pr-2">
                                    <span className="font-semibold text-slate-800 dark:text-slate-100 block truncate">
                                      {card.name || card.title}
                                    </span>
                                    {card.desc && (
                                      <span className="text-[10px] text-slate-500 dark:text-slate-400 block truncate">{card.desc}</span>
                                    )}
                                  </div>
                                  <div className="flex items-center space-x-2 shrink-0 self-end sm:self-center">
                                    <Badge variant="neutral">{card.list_name || 'Card'}</Badge>
                                    {card.url && (
                                      <a
                                        href={card.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="p-1 rounded text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition"
                                        title="View in Trello"
                                      >
                                        <ExternalLink className="w-3.5 h-3.5" />
                                      </a>
                                    )}
                                  </div>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      )}

                      {/* Read Operation Results: Board List */}
                      {msg.executionResult && msg.executionResult.boards && Array.isArray(msg.executionResult.boards) && (
                        <div className="p-3 bg-slate-100/80 dark:bg-[#111827] border border-slate-200 dark:border-slate-800 rounded-xl space-y-2">
                          <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 block">
                            Trello Boards ({msg.executionResult.boards.length})
                          </span>
                          <div className="space-y-1">
                            {msg.executionResult.boards.map((b: any, bIdx: number) => (
                              <div
                                key={b.id || bIdx}
                                className="p-2.5 rounded-lg bg-white dark:bg-slate-800/80 border border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between"
                              >
                                <span className="font-medium text-slate-800 dark:text-slate-200 text-xs truncate mr-2">{b.name}</span>
                                {b.url && (
                                  <a
                                    href={b.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-[11px] text-emerald-400 hover:underline flex items-center space-x-1 shrink-0"
                                  >
                                    <span>Open</span>
                                    <ExternalLink className="w-3 h-3" />
                                  </a>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Human-in-the-Loop Task Preview Card (The Hero Component) */}
                      {msg.approvalPreview && (
                        <div className="p-5 bg-slate-50/80 dark:bg-[#0a0f1a] border-2 border-emerald-500/40 rounded-2xl shadow-lg space-y-4">
                          {/* Banner Header */}
                          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
                            <div className="flex items-center space-x-2.5">
                              {msg.approvalPreview.status === 'PENDING' ? (
                                <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                                  <ShieldAlert className="w-4 h-4" />
                                </div>
                              ) : msg.approvalPreview.status === 'EXECUTED' ? (
                                <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                  <CheckCircle2 className="w-4 h-4" />
                                </div>
                              ) : (
                                <div className="p-2 rounded-xl bg-slate-500/10 text-slate-400 border border-slate-500/30">
                                  <Clock className="w-4 h-4" />
                                </div>
                              )}
                              <div>
                                <span className="font-bold text-slate-900 dark:text-white block text-xs tracking-wide">
                                  Task Draft Preview
                                </span>
                                <span className="text-[10px] text-slate-400">
                                  {msg.approvalPreview.status === 'PENDING'
                                    ? 'Requires explicit user confirmation before writing to Trello'
                                    : 'Synchronized with Trello MCP backend'}
                                </span>
                              </div>
                            </div>

                            <div>
                              {msg.approvalPreview.status === 'EXECUTED' ? (
                                <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center space-x-1">
                                  <CheckCircle className="w-3 h-3 text-emerald-400" />
                                  <span>Executed in Trello</span>
                                </span>
                              ) : msg.approvalPreview.status === 'EXECUTING' ||
                                actionLoading[msg.approvalPreview.actionId] ? (
                                <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-teal-500/20 text-teal-300 border border-teal-500/40 flex items-center space-x-1 animate-pulse">
                                  <Loader2 className="w-3 h-3 animate-spin text-teal-400" />
                                  <span>Executing via MCP...</span>
                                </span>
                              ) : msg.approvalPreview.status === 'REJECTED' ? (
                                <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center space-x-1">
                                  <XCircle className="w-3 h-3 text-rose-400" />
                                  <span>Cancelled</span>
                                </span>
                              ) : msg.approvalPreview.status === 'FAILED' ? (
                                <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                                  Failed
                                </span>
                              ) : (
                                <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center space-x-1 animate-pulse">
                                  <Clock className="w-3 h-3 text-amber-400" />
                                  <span>Awaiting Confirmation</span>
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Editing Mode */}
                          {editingActionId === msg.approvalPreview.actionId ? (
                            <div className="space-y-3 bg-slate-100/70 dark:bg-[#111827] p-4 rounded-xl border border-slate-200 dark:border-slate-800 text-xs">
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center space-x-1.5">
                                  <Edit3 className="w-3.5 h-3.5 text-emerald-500" />
                                  <span>Edit Task Draft</span>
                                </span>
                                <span className="text-[10px] font-mono text-slate-400">
                                  Action ID: {msg.approvalPreview.actionId}
                                </span>
                              </div>

                              <div className="space-y-2">
                                <div>
                                  <label className="text-[10px] font-medium text-slate-500 uppercase">Title</label>
                                  <input
                                    type="text"
                                    value={editFormData.title}
                                    onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                                    className="w-full mt-0.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] font-medium text-slate-500 uppercase">Description</label>
                                  <textarea
                                    rows={3}
                                    value={editFormData.description}
                                    onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                                    className="w-full mt-0.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                                  />
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                  <div>
                                    <label className="text-[10px] font-medium text-slate-500 uppercase">List</label>
                                    <select
                                      value={editFormData.listName}
                                      onChange={(e) => setEditFormData({ ...editFormData, listName: e.target.value })}
                                      className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                                    >
                                      <option value="To Do">To Do</option>
                                      <option value="Doing">Doing</option>
                                      <option value="In Progress">In Progress</option>
                                      <option value="In Review">In Review</option>
                                      <option value="Done">Done</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="text-[10px] font-medium text-slate-500 uppercase">Priority</label>
                                    <select
                                      value={editFormData.priority}
                                      onChange={(e) => setEditFormData({ ...editFormData, priority: e.target.value })}
                                      className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                                    >
                                      <option value="LOW">Low</option>
                                      <option value="MEDIUM">Medium</option>
                                      <option value="HIGH">High</option>
                                      <option value="URGENT">Urgent</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="text-[10px] font-medium text-slate-500 uppercase">Due Date</label>
                                    <input
                                      type="text"
                                      placeholder="e.g. 2026-11-26"
                                      value={editFormData.dueDate}
                                      onChange={(e) => setEditFormData({ ...editFormData, dueDate: e.target.value })}
                                      className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                                    />
                                  </div>
                                </div>
                              </div>

                              <div className="flex justify-end space-x-2 pt-2 border-t border-slate-200/60 dark:border-slate-800">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setEditingActionId(null)}
                                  disabled={actionLoading[msg.approvalPreview.actionId]}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handleSaveEdit(msg.approvalPreview!.actionId)}
                                  disabled={actionLoading[msg.approvalPreview.actionId]}
                                  icon={<Check className="w-3.5 h-3.5" />}
                                >
                                  Save Draft
                                </Button>
                              </div>
                            </div>
                          ) : (
                            /* Normal Preview Display */
                            <div className="space-y-3">
                              {/* Task Title & Description */}
                              <div className="p-3.5 bg-white dark:bg-slate-900/80 rounded-xl space-y-2 border border-slate-200 dark:border-slate-800/80">
                                <div>
                                  <span className="text-[10px] text-slate-400 font-mono font-semibold uppercase tracking-wider block">
                                    Task Title
                                  </span>
                                  <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
                                    {msg.approvalPreview.cardName}
                                  </p>
                                </div>

                                <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                                  <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block flex items-center justify-between">
                                    <span>Description</span>
                                    <span className="text-[9px] text-emerald-400 font-normal">
                                      Preview before confirm
                                    </span>
                                  </span>
                                  <p className="text-xs text-slate-700 dark:text-slate-300 mt-1 leading-relaxed bg-slate-50 dark:bg-slate-950/70 p-2.5 rounded-lg border border-slate-200/60 dark:border-slate-800/60 font-sans">
                                    {msg.approvalPreview.description || 'No description provided.'}
                                  </p>
                                </div>
                              </div>

                              {/* Metadata HUD Grid: Board, List, Priority, Due Date */}
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                                <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                                  <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1 font-mono">
                                    <Layers className="w-3 h-3 text-slate-400" />
                                    <span>Board</span>
                                  </span>
                                  <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                                    {msg.approvalPreview.boardName}
                                  </span>
                                </div>

                                <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                                  <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1 font-mono">
                                    <Clock className="w-3 h-3 text-slate-400" />
                                    <span>List</span>
                                  </span>
                                  <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                                    {msg.approvalPreview.listName}
                                  </span>
                                </div>

                                <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                                  <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1 font-mono">
                                    <Flag className="w-3 h-3 text-slate-400" />
                                    <span>Priority</span>
                                  </span>
                                  <span
                                    className={`font-semibold truncate block mt-0.5 ${
                                      msg.approvalPreview.priority === 'HIGH' ||
                                      msg.approvalPreview.priority === 'URGENT'
                                        ? 'text-rose-400'
                                        : 'text-slate-800 dark:text-slate-200'
                                    }`}
                                  >
                                    {msg.approvalPreview.priority || 'MEDIUM'}
                                  </span>
                                </div>

                                <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                                  <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1 font-mono">
                                    <Calendar className="w-3 h-3 text-slate-400" />
                                    <span>Due Date</span>
                                  </span>
                                  <span className="font-semibold text-emerald-400 truncate block mt-0.5">
                                    {formatDueDateDisplay(msg.approvalPreview.dueDate)}
                                  </span>
                                </div>
                              </div>

                              {/* Member / Assignee if specified */}
                              {msg.approvalPreview.parameters?.member_name && (
                                <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs">
                                  <span className="text-[10px] text-slate-400 uppercase font-medium flex items-center space-x-1.5 font-mono">
                                    <User className="w-3.5 h-3.5 text-emerald-500" />
                                    <span>Assigned Member</span>
                                  </span>
                                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                                    {msg.approvalPreview.parameters.member_name}
                                  </span>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Post-execution success link */}
                          {msg.approvalPreview.status === 'EXECUTED' && (
                            <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl space-y-2">
                              <div className="flex items-center space-x-2 text-emerald-300 font-semibold text-xs">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                <span>Action Executed Successfully via Trello MCP!</span>
                              </div>
                              {msg.approvalPreview.cardUrl ? (
                                <div className="pt-1">
                                  <a
                                    href={msg.approvalPreview.cardUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-xs transition"
                                  >
                                    <span>View Card in Trello</span>
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </a>
                                </div>
                              ) : (
                                <p className="text-[11px] text-emerald-400/80 font-mono">
                                  Target ID: {msg.approvalPreview.cardId || 'updated'}
                                </p>
                              )}
                            </div>
                          )}

                          {/* Error state */}
                          {msg.approvalPreview.status === 'FAILED' && (
                            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-1">
                              <div className="flex items-center space-x-1.5 text-rose-300 font-semibold text-xs">
                                <AlertTriangle className="w-4 h-4 text-rose-400" />
                                <span>Execution Failed</span>
                              </div>
                              <p className="text-[11px] text-rose-300/80">
                                {msg.approvalPreview.errorMessage || 'An error occurred while executing action in Trello.'}
                              </p>
                            </div>
                          )}

                          {/* Rejected state */}
                          {msg.approvalPreview.status === 'REJECTED' && (
                            <div className="p-3 bg-slate-800/60 border border-slate-700 rounded-xl flex items-center space-x-2 text-xs text-slate-400">
                              <XCircle className="w-4 h-4 text-slate-400" />
                              <span>Action cancelled and draft discarded.</span>
                            </div>
                          )}

                          {/* Action Control Buttons (Only when PENDING and not in edit mode) */}
                          {msg.approvalPreview.status === 'PENDING' &&
                            editingActionId !== msg.approvalPreview.actionId && (
                              <div className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 dark:border-slate-800">
                                <span className="text-[10px] text-slate-400 font-mono">
                                  ID: {msg.approvalPreview.actionId}
                                </span>

                                <div className="flex flex-wrap items-center gap-2">
                                  {/* Cancel Button */}
                                  <button
                                    type="button"
                                    onClick={() => handleActionCancel(msg.approvalPreview!.actionId)}
                                    disabled={actionLoading[msg.approvalPreview.actionId]}
                                    className="px-3 py-1.5 rounded-xl bg-slate-800/60 hover:bg-rose-500/15 hover:text-rose-300 text-slate-400 border border-slate-700 text-xs font-medium flex items-center space-x-1.5 transition disabled:opacity-50"
                                  >
                                    <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                    <span>Reject</span>
                                  </button>

                                  {/* Edit Button */}
                                  <button
                                    type="button"
                                    onClick={() => handleStartEdit(msg.approvalPreview!)}
                                    disabled={actionLoading[msg.approvalPreview.actionId]}
                                    className="px-3 py-1.5 rounded-xl bg-slate-800/60 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium flex items-center space-x-1.5 transition disabled:opacity-50"
                                  >
                                    <Edit3 className="w-3.5 h-3.5 text-emerald-400" />
                                    <span>Edit</span>
                                  </button>

                                  {/* Confirm Button */}
                                  <button
                                    type="button"
                                    onClick={() => handleActionConfirm(msg.approvalPreview!.actionId)}
                                    disabled={actionLoading[msg.approvalPreview.actionId]}
                                    className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-xs shadow-md flex items-center space-x-1.5 transition disabled:opacity-50"
                                  >
                                    {actionLoading[msg.approvalPreview.actionId] ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <CheckCircle2 className="w-3.5 h-3.5" />
                                    )}
                                    <span>
                                      {actionLoading[msg.approvalPreview.actionId] ? 'Executing...' : 'Confirm & Execute'}
                                    </span>
                                  </button>
                                </div>
                              </div>
                            )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="flex items-center space-x-3 text-xs text-slate-400 animate-pulse bg-slate-900/40 p-3 rounded-xl border border-slate-800 w-fit">
                <div className="w-6 h-6 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center shrink-0">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                </div>
                <span className="font-mono text-[11px]">Interpreting intent with Gemini & executing via MCP...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Bottom Command Center */}
          <div className="p-3 sm:p-4 border-t border-slate-100 dark:border-slate-800/80 bg-white/80 dark:bg-[#0c121e]/80 backdrop-blur-md shrink-0 space-y-2.5 sm:space-y-3">
            {/* Quick Suggestion Prompts */}
            <div className="flex items-center space-x-2 overflow-x-auto text-[11px] pb-1 scrollbar-none touch-pan-x">
              <span className="text-slate-400 font-mono text-[10px] uppercase font-semibold shrink-0 flex items-center space-x-1">
                <Sparkles className="w-3 h-3 text-amber-400" />
                <span>Actions:</span>
              </span>
              {samplePrompts.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSendMessage(undefined, item.prompt)}
                  className="px-2.5 sm:px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-emerald-500/15 hover:text-emerald-400 dark:hover:border-emerald-500/40 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700/80 shrink-0 transition flex items-center space-x-1.5 font-medium whitespace-nowrap"
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>

            {/* Floating Command Bar */}
            <form onSubmit={handleSendMessage} className="relative">
              <div className="relative flex items-center bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-2xl pl-3 sm:pl-4 pr-2 sm:pr-3 py-1.5 sm:py-2 shadow-inner focus-within:border-emerald-500/60 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all">
                <div className="shrink-0 mr-2 sm:mr-3 text-emerald-500">
                  <Terminal className="w-4 h-4" />
                </div>

                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder='Enter agent command (e.g. "Create task Login API", "Move to Doing")...'
                  className="w-full bg-transparent border-none text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-0 py-1 sm:py-1.5 min-w-0"
                />

                <div className="flex items-center space-x-1.5 sm:space-x-2 shrink-0 ml-1.5 sm:ml-2">
                  <span className="hidden sm:inline-flex items-center space-x-1 text-[10px] text-slate-400 font-mono bg-white dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
                    <CornerDownLeft className="w-2.5 h-2.5" />
                    <span>Return</span>
                  </span>

                  <button
                    type="submit"
                    disabled={!inputValue.trim() || isLoading}
                    className="p-2 sm:p-2.5 rounded-xl bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 text-white transition shadow-sm shrink-0"
                    title="Execute Command"
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
