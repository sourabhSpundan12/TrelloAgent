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
} from 'lucide-react';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { DemoBanner } from '../components/common/DemoBanner';
import { ChatMessage, ActionApprovalPreview, ApprovalEditPayload, ChatSession } from '../types';
import { useAuth } from '../context/AuthContext';
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
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isSessionsLoading, setIsSessionsLoading] = useState<boolean>(false);
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
      const res = await fetchChatSessions();
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

  // Load chat sessions from MongoDB Atlas on mount or when user authenticates
  useEffect(() => {
    loadSessionsAndSelect();
  }, [isAuthenticated]);

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
      const res = await interpretCommand(query, activeActionId || undefined, effectiveSessionId);
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
    'Create a task card Login API',
    'Create a high-priority task for JWT authentication',
    'Move Login API card to Doing',
    'Show cards in the To Do list',
    'Find the task related to Login API',
    'Show my Trello boards',
  ];

  return (
    <div className="h-[calc(100vh-8.5rem)] flex flex-col space-y-4">
      <DemoBanner
        mode="live"
        message="Phase 7A Live: Conversational AI Agent with Human-in-the-Loop. Natural conversation is the primary interface. Read operations execute immediately; mutations create live draft previews requiring user confirmation before executing via Trello MCP."
      />

      {/* Main Dual-Panel Area */}
      <div className="flex-1 flex gap-6 min-h-0">
        {/* Left: Chat Overview & Status */}
        <Card className="w-72 hidden lg:flex flex-col justify-between shrink-0 overflow-hidden">
          <div className="p-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-800 dark:text-slate-100 uppercase tracking-wider flex items-center space-x-1.5">
              <MessageSquare className="w-4 h-4 text-brand-600 dark:text-brand-400" />
              <span>Chats</span>
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={handleNewConversation}
              icon={<Plus className="w-3.5 h-3.5" />}
              className="text-xs py-1 px-2.5 h-7"
            >
              New Chat
            </Button>
          </div>

          <div className="p-2 flex-1 overflow-y-auto space-y-1 text-xs">
            {isSessionsLoading ? (
              <div className="p-6 text-center text-slate-400 flex items-center justify-center space-x-2">
                <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
                <span className="text-xs">Loading chats...</span>
              </div>
            ) : sessions.length === 0 ? (
              <div className="p-6 text-center space-y-2">
                <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
                  <Bot className="w-4 h-4" />
                </div>
                <p className="text-[11px] text-slate-400">
                  No previous chats yet. Type a command to start a new conversation!
                </p>
              </div>
            ) : (
              sessions.map((sess) => {
                const isActive = sess.id === currentSessionId;
                return (
                  <div
                    key={sess.id}
                    onClick={() => handleSelectSession(sess)}
                    className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition-all text-xs ${
                      isActive
                        ? 'bg-brand-500/10 dark:bg-brand-500/20 text-brand-700 dark:text-brand-300 font-medium border border-brand-500/30'
                        : 'hover:bg-slate-100 dark:hover:bg-slate-800/60 text-slate-700 dark:text-slate-300 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center space-x-2 min-w-0 pr-6">
                      <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-brand-600 dark:text-brand-400' : 'text-slate-400'}`} />
                      <div className="min-w-0">
                        <span className="block truncate text-xs font-medium" title={sess.title}>
                          {sess.title || 'Conversation'}
                        </span>
                        <span className="block text-[10px] text-slate-400 font-normal">
                          {formatSessionTime(sess.updated_at || sess.created_at)}
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={(e) => handleDeleteSession(e, sess.id)}
                      title="Delete Chat"
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-md text-slate-400 hover:text-red-500 hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-opacity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>

          <div className="p-3 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 text-xs space-y-1.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">Atlas Synced</span>
              </div>
              <button
                onClick={handleClearAllHistory}
                className="text-[10px] text-slate-400 hover:text-red-500 transition-colors"
                title="Clear all conversations"
              >
                Clear All
              </button>
            </div>
            <span className="text-[10px] text-slate-400 block font-mono truncate">
              User: {user?.email || 'Authenticated'}
            </span>
          </div>
        </Card>

        {/* Right: Active Chat Window */}
        <Card className="flex-1 flex flex-col justify-between overflow-hidden">
          {/* Top Thread Info */}
          <div className="h-14 px-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                  Agentic Task Assistant
                </h3>
                <p className="text-[10px] text-slate-400 flex items-center space-x-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${isAuthenticated ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'}`}></span>
                  <span>{isAuthenticated ? 'Authenticated • Gemini 3.5 Flash Lite + Trello MCP' : 'Sign In Required for Live AI Commands'}</span>
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              {!isAuthenticated && (
                <Button variant="primary" size="sm" onClick={openLoginModal}>
                  Sign In
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={handleNewConversation} icon={<Plus className="w-3.5 h-3.5" />}>
                New Chat
              </Button>
            </div>
          </div>

          {/* Messages Stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 text-xs ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.sender === 'assistant' && (
                  <div className="w-8 h-8 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div className={`space-y-2 max-w-2xl ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                  {/* Bubble */}
                  <div
                    className={`p-4 rounded-2xl ${
                      msg.sender === 'user'
                        ? 'bg-brand-600 text-white shadow-xs rounded-tr-xs'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 border border-slate-200/60 dark:border-slate-700/60 rounded-tl-xs'
                    }`}
                  >
                    <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  </div>

                  {/* Read Operation Results: Structured Card List */}
                  {msg.executionResult && msg.executionResult.cards && Array.isArray(msg.executionResult.cards) && (
                    <div className="p-3 bg-white dark:bg-slate-850 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2 shadow-xs">
                      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                        <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 flex items-center space-x-1.5">
                          <ListTodo className="w-3.5 h-3.5 text-brand-600" />
                          <span>Trello Cards ({msg.executionResult.cards.length})</span>
                        </span>
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">Live from MCP</span>
                      </div>
                      <div className="space-y-1.5 max-h-56 overflow-y-auto">
                        {msg.executionResult.cards.length === 0 ? (
                          <p className="text-[11px] text-slate-400 italic">No matching cards found on board.</p>
                        ) : (
                          msg.executionResult.cards.map((card: any, cIdx: number) => (
                            <div
                              key={card.id || cIdx}
                              className="p-2 rounded-lg bg-slate-50 dark:bg-slate-800 flex items-center justify-between text-xs hover:bg-slate-100 dark:hover:bg-slate-750 transition"
                            >
                              <div className="min-w-0 pr-2">
                                <span className="font-medium text-slate-800 dark:text-slate-200 block truncate">
                                  {card.name || card.title}
                                </span>
                                {card.desc && (
                                  <span className="text-[10px] text-slate-500 block truncate">{card.desc}</span>
                                )}
                              </div>
                              <div className="flex items-center space-x-2 shrink-0">
                                <Badge variant="neutral">{card.list_name || 'Card'}</Badge>
                                {card.url && (
                                  <a
                                    href={card.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1 rounded text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition"
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
                    <div className="p-3 bg-white dark:bg-slate-850 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2">
                      <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 block">
                        Trello Boards ({msg.executionResult.boards.length})
                      </span>
                      <div className="space-y-1">
                        {msg.executionResult.boards.map((b: any, bIdx: number) => (
                          <div key={b.id || bIdx} className="p-2 rounded-lg bg-slate-50 dark:bg-slate-800 flex items-center justify-between">
                            <span className="font-medium text-slate-800 dark:text-slate-200 text-xs">{b.name}</span>
                            {b.url && (
                              <a
                                href={b.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[11px] text-brand-600 hover:underline flex items-center space-x-1"
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

                  {/* Extracted Parameters Box */}
                  {msg.parameters && Object.keys(msg.parameters).length > 0 && (
                    <div className="p-2.5 bg-slate-50 dark:bg-slate-850 border border-slate-200/60 dark:border-slate-800 rounded-xl space-y-1 text-xs">
                      <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
                        Extracted Parameters
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(msg.parameters).map(([key, value]) => (
                          <span
                            key={key}
                            className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-200/80 dark:bg-slate-700 text-slate-800 dark:text-slate-200 text-[11px] font-mono"
                          >
                            <span className="text-slate-500 dark:text-slate-400 mr-1">{key}:</span>
                            {String(value)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tool Selection Explanation Display */}
                  {msg.discoveredTool && (
                    <div className="p-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200/80 dark:border-slate-700/80 rounded-xl space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center space-x-1.5 font-semibold text-slate-700 dark:text-slate-300">
                          <Wrench className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                          <span>Tool Discovered:</span>
                          <code className="px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-brand-700 dark:text-brand-300 font-mono text-[11px]">
                            {msg.discoveredTool.name}
                          </code>
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          Relevance: {Math.round(msg.discoveredTool.relevanceScore * 100)}%
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        {msg.discoveredTool.explanation}
                      </p>
                    </div>
                  )}

                  {/* Human-in-the-Loop Task Preview Card */}
                  {msg.approvalPreview && (
                    <div className="p-5 bg-white dark:bg-slate-900 border-2 border-brand-500/40 rounded-2xl shadow-sm space-y-4">
                      {/* Header */}
                      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                        <div className="flex items-center space-x-2.5">
                          <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                            <ShieldAlert className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="font-semibold text-slate-900 dark:text-white block">
                              Task Draft Preview
                            </span>
                            <span className="text-[10px] text-slate-400">
                              Requires explicit user confirmation before writing to Trello
                            </span>
                          </div>
                        </div>

                        <div>
                          {msg.approvalPreview.status === 'EXECUTED' ? (
                            <Badge variant="success">Executed in Trello</Badge>
                          ) : msg.approvalPreview.status === 'EXECUTING' || actionLoading[msg.approvalPreview.actionId] ? (
                            <Badge variant="info">Executing via MCP...</Badge>
                          ) : msg.approvalPreview.status === 'REJECTED' ? (
                            <Badge variant="danger">Cancelled</Badge>
                          ) : msg.approvalPreview.status === 'FAILED' ? (
                            <Badge variant="danger">Failed</Badge>
                          ) : (
                            <Badge variant="warning">Awaiting Confirmation</Badge>
                          )}
                        </div>
                      </div>

                      {/* Editing Mode */}
                      {editingActionId === msg.approvalPreview.actionId ? (
                        <div className="space-y-3 bg-slate-50/70 dark:bg-slate-850 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center space-x-1.5">
                              <Edit3 className="w-3.5 h-3.5 text-brand-600" />
                              <span>Edit Task Draft</span>
                            </span>
                            <span className="text-[10px] text-slate-400">Action ID: {msg.approvalPreview.actionId}</span>
                          </div>

                          <div className="space-y-2">
                            <div>
                              <label className="text-[10px] font-medium text-slate-500 uppercase">Title</label>
                              <input
                                type="text"
                                value={editFormData.title}
                                onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                                className="w-full mt-0.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
                              />
                            </div>
                            <div>
                              <label className="text-[10px] font-medium text-slate-500 uppercase">Description</label>
                              <textarea
                                rows={3}
                                value={editFormData.description}
                                onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                                className="w-full mt-0.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
                              />
                            </div>
                            <div className="grid grid-cols-3 gap-2">
                              <div>
                                <label className="text-[10px] font-medium text-slate-500 uppercase">List</label>
                                <select
                                  value={editFormData.listName}
                                  onChange={(e) => setEditFormData({ ...editFormData, listName: e.target.value })}
                                  className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
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
                                  className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
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
                                  placeholder="e.g. next Friday or 2026-11-20"
                                  value={editFormData.dueDate}
                                  onChange={(e) => setEditFormData({ ...editFormData, dueDate: e.target.value })}
                                  className="w-full mt-0.5 px-2 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
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
                          <div className="p-3 bg-slate-50 dark:bg-slate-800/70 rounded-xl space-y-2.5 border border-slate-100 dark:border-slate-800">
                            <div>
                              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
                                Task Title
                              </span>
                              <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
                                {msg.approvalPreview.cardName}
                              </p>
                            </div>

                            <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/60">
                              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block flex items-center justify-between">
                                <span>Description</span>
                                <span className="text-[9px] text-brand-600 dark:text-brand-400 font-normal">Preview before confirm</span>
                              </span>
                              <p className="text-xs text-slate-700 dark:text-slate-300 mt-1 leading-relaxed bg-white/70 dark:bg-slate-900/50 p-2.5 rounded-lg border border-slate-200/50 dark:border-slate-700/50">
                                {msg.approvalPreview.description || 'No description provided.'}
                              </p>
                            </div>
                          </div>

                          {/* Metadata Grid: Board, List, Priority, Due Date */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                            <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                              <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1">
                                <Layers className="w-3 h-3 text-slate-400" />
                                <span>Board</span>
                              </span>
                              <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                                {msg.approvalPreview.boardName}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                              <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1">
                                <Clock className="w-3 h-3 text-slate-400" />
                                <span>List</span>
                              </span>
                              <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                                {msg.approvalPreview.listName}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                              <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1">
                                <Flag className="w-3 h-3 text-slate-400" />
                                <span>Priority</span>
                              </span>
                              <span
                                className={`font-semibold truncate block mt-0.5 ${
                                  msg.approvalPreview.priority === 'HIGH' || msg.approvalPreview.priority === 'URGENT'
                                    ? 'text-rose-600 dark:text-rose-400'
                                    : 'text-slate-800 dark:text-slate-200'
                                }`}
                              >
                                {msg.approvalPreview.priority || 'MEDIUM'}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                              <span className="text-[10px] text-slate-400 block uppercase font-medium flex items-center space-x-1">
                                <Calendar className="w-3 h-3 text-slate-400" />
                                <span>Due Date</span>
                              </span>
                              <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                                {formatDueDateDisplay(msg.approvalPreview.dueDate)}
                              </span>
                            </div>
                          </div>

                          {/* Member / Assignee if specified */}
                          {msg.approvalPreview.parameters?.member_name && (
                            <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
                              <span className="text-[10px] text-slate-400 uppercase font-medium flex items-center space-x-1.5">
                                <User className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
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
                        <div className="p-3 bg-emerald-50/80 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-xl space-y-2">
                          <div className="flex items-center space-x-2 text-emerald-800 dark:text-emerald-300 font-semibold text-xs">
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                            <span>Action Executed Successfully via Trello MCP!</span>
                          </div>
                          {msg.approvalPreview.cardUrl ? (
                            <div className="pt-1">
                              <a
                                href={msg.approvalPreview.cardUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-xs transition"
                              >
                                <span>View Card in Trello</span>
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            </div>
                          ) : (
                            <p className="text-[11px] text-emerald-700/80 dark:text-emerald-400/80">
                              Target ID: {msg.approvalPreview.cardId || 'updated'}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Error state */}
                      {msg.approvalPreview.status === 'FAILED' && (
                        <div className="p-3 bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-xl space-y-1">
                          <div className="flex items-center space-x-1.5 text-rose-700 dark:text-rose-400 font-semibold text-xs">
                            <AlertTriangle className="w-4 h-4" />
                            <span>Execution Failed</span>
                          </div>
                          <p className="text-[11px] text-rose-600 dark:text-rose-400">
                            {msg.approvalPreview.errorMessage || 'An error occurred while executing action in Trello.'}
                          </p>
                        </div>
                      )}

                      {/* Rejected state */}
                      {msg.approvalPreview.status === 'REJECTED' && (
                        <div className="p-3 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400">
                          <XCircle className="w-4 h-4 text-slate-400" />
                          <span>Action cancelled and draft discarded.</span>
                        </div>
                      )}

                      {/* Action Control Buttons (Only when PENDING and not in edit mode) */}
                      {msg.approvalPreview.status === 'PENDING' && editingActionId !== msg.approvalPreview.actionId && (
                        <div className="pt-2 flex items-center justify-between border-t border-slate-100 dark:border-slate-800">
                          <span className="text-[10px] text-slate-400 font-mono">
                            ID: {msg.approvalPreview.actionId}
                          </span>

                          <div className="flex items-center space-x-2">
                            {/* Cancel Button */}
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleActionCancel(msg.approvalPreview!.actionId)}
                              disabled={actionLoading[msg.approvalPreview.actionId]}
                              icon={<XCircle className="w-3.5 h-3.5 text-rose-500" />}
                            >
                              Cancel
                            </Button>

                            {/* Edit Button */}
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleStartEdit(msg.approvalPreview!)}
                              disabled={actionLoading[msg.approvalPreview.actionId]}
                              icon={<Edit3 className="w-3.5 h-3.5 text-brand-600" />}
                            >
                              Edit
                            </Button>

                            {/* Confirm Button */}
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleActionConfirm(msg.approvalPreview!.actionId)}
                              disabled={actionLoading[msg.approvalPreview.actionId]}
                              icon={
                                actionLoading[msg.approvalPreview.actionId] ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <CheckCircle className="w-3.5 h-3.5" />
                                )
                              }
                            >
                              {actionLoading[msg.approvalPreview.actionId] ? 'Executing...' : 'Confirm'}
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <span className="text-[10px] text-slate-400 block px-1">{msg.timestamp}</span>
                </div>

                {msg.sender === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-slate-600 dark:text-slate-300" />
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="flex items-center space-x-3 text-xs text-slate-400 animate-pulse">
                <div className="w-8 h-8 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <span>Interpreting intent with Gemini & executing via MCP...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Suggestion Prompts */}
          <div className="px-4 py-2 bg-slate-50/60 dark:bg-slate-850/50 border-t border-slate-100 dark:border-slate-800 flex items-center space-x-1.5 overflow-x-auto text-[11px]">
            <span className="text-slate-400 font-medium shrink-0 mr-1 flex items-center space-x-1">
              <Sparkles className="w-3 h-3 text-amber-500" />
              <span>Try:</span>
            </span>
            {samplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSendMessage(undefined, prompt)}
                className="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-800 hover:bg-brand-50 dark:hover:bg-brand-900/30 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/80 truncate shrink-0 transition"
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Chat Input Bar */}
          <form onSubmit={handleSendMessage} className="p-4 border-t border-slate-100 dark:border-slate-800 shrink-0">
            <div className="relative flex items-center">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder='Ask the AI Agent naturally: e.g. "Create a task card Login API", "Move Login API to Doing", or "Confirm"...'
                className="w-full bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-xl pl-4 pr-12 py-3 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:bg-white dark:focus:bg-slate-850 transition"
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || isLoading}
                className="absolute right-2 p-2 rounded-lg bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white transition shadow-sm"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
};
