import React, { useState } from 'react';
import {
  FolderKanban,
  CheckCircle2,
  Plus,
  ExternalLink,
  Copy,
  Check,
  Trash2,
  RefreshCw,
  Sparkles,
  Info,
  Layers,
  ArrowRight,
  HelpCircle,
  X,
  AlertCircle,
  Power,
} from 'lucide-react';
import { useBoard } from '../context/BoardContext';
import { Board } from '../types';

interface BoardsPageProps {
  onNavigate?: (tab: string) => void;
}

export const BoardsPage: React.FC<BoardsPageProps> = ({ onNavigate }) => {
  const {
    boards,
    activeBoard,
    activeBoardId,
    isLoading,
    error,
    activateBoard,
    deactivateBoard,
    toggleBoardStatus,
    addBoard,
    deleteBoard,
    refreshBoards,
  } = useBoard();

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [boardIdInput, setBoardIdInput] = useState('');
  const [boardNameInput, setBoardNameInput] = useState('');
  const [boardDescInput, setBoardDescInput] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  const handleCopy = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleActivate = async (boardId: string, name: string) => {
    try {
      setSwitchingId(boardId);
      setActionError(null);
      await activateBoard(boardId);
      setActionSuccess(`Board "${name}" is now ACTIVE! Tasks, reports, and AI chat sessions are synced.`);
      setTimeout(() => setActionSuccess(null), 5000);
    } catch (err: any) {
      setActionError(err.message || 'Failed to activate board.');
    } finally {
      setSwitchingId(null);
    }
  };

  const handleDeactivate = async (boardId: string, name: string) => {
    try {
      setSwitchingId(boardId);
      setActionError(null);
      await deactivateBoard(boardId);
      setActionSuccess(`Board "${name}" has been marked INACTIVE.`);
      setTimeout(() => setActionSuccess(null), 5000);
    } catch (err: any) {
      setActionError(err.message || 'Failed to deactivate board.');
    } finally {
      setSwitchingId(null);
    }
  };

  const handleToggle = async (boardId: string, name: string) => {
    try {
      setSwitchingId(boardId);
      setActionError(null);
      const isCurrentlyActive = boardId === activeBoardId;
      await toggleBoardStatus(boardId);
      if (isCurrentlyActive) {
        setActionSuccess(`Board "${name}" is now INACTIVE.`);
      } else {
        setActionSuccess(`Board "${name}" is now ACTIVE! All tasks and chats switched.`);
      }
      setTimeout(() => setActionSuccess(null), 5000);
    } catch (err: any) {
      setActionError(err.message || 'Failed to update board status.');
    } finally {
      setSwitchingId(null);
    }
  };

  const handleDelete = async (board: Board) => {
    if (boards.length <= 1) {
      setActionError('Cannot delete the only configured board.');
      return;
    }
    const confirmed = window.confirm(
      `Are you sure you want to remove "${board.name}" (${board.board_id}) from the platform?`
    );
    if (!confirmed) return;

    try {
      setActionError(null);
      await deleteBoard(board.board_id);
      setActionSuccess(`Board "${board.name}" was removed.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setActionError(err.message || 'Failed to delete board.');
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const rawId = boardIdInput.trim();
    if (!rawId) {
      setActionError('Please enter a valid Trello Board ID or URL.');
      return;
    }

    try {
      setIsSubmitting(true);
      setActionError(null);
      const newBoard = await addBoard(rawId, boardNameInput.trim() || undefined, boardDescInput.trim() || undefined);
      setIsAddModalOpen(false);
      setBoardIdInput('');
      setBoardNameInput('');
      setBoardDescInput('');
      setActionSuccess(`Board "${newBoard.name}" registered and displayed in your list!`);
      setTimeout(() => setActionSuccess(null), 5000);
      await refreshBoards();
    } catch (err: any) {
      setActionError(err.message || 'Failed to add board.');
      // Refresh boards in case it was already registered
      await refreshBoards();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-sm">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold tracking-wider text-brand-600 dark:text-brand-400 uppercase">
            <FolderKanban className="w-4 h-4" />
            <span>Workspace & Board Orchestration</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
            Trello Board Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
            Register multiple Trello boards, activate or inactivate any board, and keep your tasks, metrics, and AI assistant chats completely separate per board.
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <button
            onClick={() => refreshBoards()}
            disabled={isLoading}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition"
            title="Refresh board list"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => {
              setActionError(null);
              setIsAddModalOpen(true);
            }}
            className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-sm shadow-md shadow-brand-500/20 transition active:scale-95"
          >
            <Plus className="w-4 h-4" />
            <span>Add Board</span>
          </button>
        </div>
      </div>

      {/* Global Alerts */}
      {actionSuccess && (
        <div className="flex items-center space-x-3 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 text-sm animate-fadeIn">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
          <span className="flex-1 font-medium">{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-500 hover:text-emerald-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {actionError && (
        <div className="flex items-center space-x-3 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 text-sm animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400 shrink-0" />
          <span className="flex-1">{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Hero Card: Currently Active Board or Inactive State */}
      {activeBoard ? (
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-500/10 via-slate-50 to-brand-500/10 dark:from-emerald-950/40 dark:via-slate-900 dark:to-brand-950/30 border-2 border-emerald-500/40 dark:border-emerald-500/30 p-6 sm:p-7 shadow-lg">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-3">
              <div className="flex items-center space-x-2.5">
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse mr-1.5" />
                  Currently Active Board
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  All AI agent commands & task views target this board
                </span>
              </div>

              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <span>{activeBoard.name}</span>
                </h2>
                {activeBoard.desc && (
                  <p className="text-sm text-slate-600 dark:text-slate-300 mt-1 max-w-xl">
                    {activeBoard.desc}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3 pt-1">
                {/* Board ID pill with copy */}
                <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white/80 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-700 dark:text-slate-200">
                  <span className="text-slate-400 font-sans">ID:</span>
                  <span>{activeBoard.board_id}</span>
                  <button
                    onClick={() => handleCopy(activeBoard.board_id)}
                    title="Copy Board ID"
                    className="p-1 hover:text-brand-500 text-slate-400 transition"
                  >
                    {copiedId === activeBoard.board_id ? (
                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                {/* External link to Trello */}
                {activeBoard.url && (
                  <a
                    href={activeBoard.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white/80 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 hover:text-brand-600 dark:hover:text-brand-400 hover:border-brand-500/50 transition"
                  >
                    <span>Open in Trello</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>

            {/* Quick Actions Right */}
            <div className="flex flex-row md:flex-col items-stretch justify-center gap-2.5 shrink-0">
              <button
                onClick={() => handleDeactivate(activeBoard.board_id, activeBoard.name)}
                className="flex items-center justify-center space-x-2 px-4 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30 text-xs font-semibold transition"
                title="Mark this board as Inactive"
              >
                <Power className="w-3.5 h-3.5" />
                <span>Mark Inactive</span>
              </button>

              {onNavigate && (
                <>
                  <button
                    onClick={() => onNavigate('tasks')}
                    className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-medium text-xs hover:opacity-90 transition shadow-sm"
                  >
                    <span>View Board Tasks</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>

                  <button
                    onClick={() => onNavigate('ai-assistant')}
                    className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-brand-600/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 border border-brand-500/30 font-medium text-xs hover:bg-brand-600/20 transition"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Open AI Assistant for Board</span>
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="relative overflow-hidden rounded-2xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 p-6 sm:p-7 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-400 dark:bg-slate-600" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  No Board Currently Active
                </span>
              </div>
              <h3 className="text-lg font-bold text-slate-800 dark:text-slate-200">
                Choose a Board to Activate
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-lg">
                Click &quot;Activate&quot; on any configured board below to route all AI agent interactions and task views to that board.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Grid of All Configured Boards */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Layers className="w-5 h-5 text-slate-400" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">
              All Configured Boards ({boards.length})
            </h3>
          </div>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Activate or inactivate any board
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {boards.map((b) => {
            const isActive = b.board_id === activeBoardId || b.is_active;
            const isSwitching = switchingId === b.board_id;

            return (
              <div
                key={b.board_id}
                className={`relative flex flex-col justify-between p-5 rounded-2xl bg-white dark:bg-slate-900 border transition-all duration-200 ${
                  isActive
                    ? 'border-emerald-500 dark:border-emerald-500/80 shadow-md ring-1 ring-emerald-500/20'
                    : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-sm'
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center space-x-2 min-w-0">
                      <div
                        className={`p-2 rounded-xl shrink-0 ${
                          isActive
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
                        }`}
                      >
                        <FolderKanban className="w-4 h-4" />
                      </div>
                      <h4 className="font-bold text-slate-900 dark:text-white text-base truncate">
                        {b.name}
                      </h4>
                    </div>

                    {/* Active/Inactive Toggle Pill Switch */}
                    <button
                      type="button"
                      onClick={() => handleToggle(b.board_id, b.name)}
                      disabled={isSwitching}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        isActive ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'
                      }`}
                      title={isActive ? 'Click to make Inactive' : 'Click to make Active'}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                          isActive ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center space-x-2 mb-2">
                    {isActive ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 shrink-0" />
                        Active Board
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 mr-1.5 shrink-0" />
                        Inactive
                      </span>
                    )}
                  </div>

                  {b.desc && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mb-3">
                      {b.desc}
                    </p>
                  )}

                  <div className="flex items-center space-x-2 text-xs font-mono bg-slate-50 dark:bg-slate-800/60 p-2 rounded-lg border border-slate-100 dark:border-slate-800 mb-4">
                    <span className="text-slate-400 select-none">ID:</span>
                    <span className="text-slate-700 dark:text-slate-300 truncate flex-1">
                      {b.board_id}
                    </span>
                    <button
                      onClick={() => handleCopy(b.board_id)}
                      className="text-slate-400 hover:text-brand-500 transition"
                      title="Copy ID"
                    >
                      {copiedId === b.board_id ? (
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800 gap-2">
                  <div className="flex items-center space-x-2">
                    {b.url && (
                      <a
                        href={b.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                        title="Open in Trello"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                    {boards.length > 1 && (
                      <button
                        onClick={() => handleDelete(b)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition"
                        title="Remove board from platform"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  <div>
                    {isActive ? (
                      <button
                        onClick={() => handleDeactivate(b.board_id, b.name)}
                        disabled={isSwitching}
                        className="px-3.5 py-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition active:scale-95 flex items-center space-x-1.5"
                        title="Click to inactivate this board"
                      >
                        {isSwitching ? (
                          <RefreshCw className="w-3 h-3 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5 text-emerald-500" />
                        )}
                        <span>Active</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleActivate(b.board_id, b.name)}
                        disabled={isSwitching}
                        className="px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white text-xs font-semibold transition active:scale-95 flex items-center space-x-1.5"
                      >
                        {isSwitching ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            <span>Activating...</span>
                          </>
                        ) : (
                          <span>Activate Board</span>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Helpful Guide Accordion */}
      <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
        <button
          onClick={() => setShowHelp(!showHelp)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center space-x-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
            <HelpCircle className="w-4 h-4 text-brand-500" />
            <span>How to find your Trello Board ID?</span>
          </div>
          <span className="text-xs text-brand-600 dark:text-brand-400 font-medium">
            {showHelp ? 'Hide guide' : 'Show guide'}
          </span>
        </button>

        {showHelp && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-300 space-y-2.5 animate-fadeIn">
            <p>
              Every Trello board has a unique 24-character hexadecimal ID (e.g., <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-brand-600 dark:text-brand-400">6af5688583f6e4d6f991059b</code>).
            </p>
            <ol className="list-decimal list-inside space-y-1.5 pl-1">
              <li>
                Open the board in your web browser:{' '}
                <span className="font-mono text-slate-500">https://trello.com/b/xyz123/my-board</span>
              </li>
              <li>
                Add <span className="font-bold text-slate-900 dark:text-white">.json</span> to the end of the URL in your browser's address bar:{' '}
                <span className="font-mono text-slate-500">https://trello.com/b/xyz123/my-board.json</span>
              </li>
              <li>
                Press Enter. The very first key in the JSON is <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">"id": "6af5688583f6e4d6f991059b"</code>.
              </li>
              <li>
                Copy that 24-character string and paste it into the "Add Board" dialog above!
              </li>
            </ol>
          </div>
        )}
      </div>

      {/* Add Board Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
          <div className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-2xl space-y-5 animate-scaleUp">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                  <FolderKanban className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                    Add / Register Trello Board
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Register a new board or display an existing board
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Trello Board ID or Board URL <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 6af5688583f6e4d6f991059b or https://trello.com/b/..."
                  value={boardIdInput}
                  onChange={(e) => setBoardIdInput(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition font-mono"
                />
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                  You can paste the 24-character ID or the full Trello board URL.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Board Friendly Name <span className="text-slate-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Primary Board / Mobile App Sprint"
                  value={boardNameInput}
                  onChange={(e) => setBoardNameInput(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition"
                />
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                  If left empty, the name will be fetched automatically from Trello.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Description <span className="text-slate-400 font-normal">(optional)</span>
                </label>
                <textarea
                  rows={2}
                  placeholder="Brief description of the board purpose"
                  value={boardDescInput}
                  onChange={(e) => setBoardDescInput(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition resize-none"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center space-x-2 px-5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium shadow-md shadow-brand-500/20 transition disabled:opacity-60 active:scale-95"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Saving Board...</span>
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      <span>Save Board</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
