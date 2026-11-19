import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Kanban,
  ChevronDown,
  Check,
  Search,
  ExternalLink,
  RefreshCw,
  Plus,
  Layers,
  Sparkles,
} from 'lucide-react';
import { useBoard } from '../../context/BoardContext';
import { Board } from '../../types';

interface BoardSelectorDropdownProps {
  onNavigateToBoards?: () => void;
  className?: string;
}

export const BoardSelectorDropdown: React.FC<BoardSelectorDropdownProps> = ({
  onNavigateToBoards,
  className = '',
}) => {
  const { boards, activeBoard, activeBoardId, activateBoard, refreshBoards, isLoading } = useBoard();
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      // Auto-focus search input when opened
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Filter boards based on search query
  const filteredBoards = useMemo(() => {
    if (!searchQuery.trim()) return boards;
    const q = searchQuery.toLowerCase().trim();
    return boards.filter(
      (b) =>
        b.name?.toLowerCase().includes(q) ||
        b.board_id?.toLowerCase().includes(q) ||
        b.desc?.toLowerCase().includes(q)
    );
  }, [boards, searchQuery]);

  const handleSelectBoard = async (board: Board) => {
    if (board.board_id === activeBoardId) {
      setIsOpen(false);
      return;
    }
    try {
      setSwitchingId(board.board_id);
      await activateBoard(board.board_id);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to activate board:', err);
    } finally {
      setSwitchingId(null);
    }
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      {/* Dropdown Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        title={activeBoard ? `Active Board: ${activeBoard.name}` : 'Select a Trello Board'}
        className="group flex items-center space-x-2 px-2.5 py-1.5 rounded-xl bg-slate-100/90 dark:bg-slate-800/80 hover:bg-slate-200/90 dark:hover:bg-slate-700/80 border border-slate-200 dark:border-slate-700/70 text-slate-800 dark:text-slate-200 transition-all shadow-xs cursor-pointer focus:outline-none focus:ring-2 focus:ring-brand-500/30 max-w-[210px] sm:max-w-[260px] md:max-w-[290px]"
      >
        <div className="w-5 h-5 rounded-lg bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 flex items-center justify-center shrink-0">
          <Kanban className="w-3.5 h-3.5" />
        </div>

        <div className="flex flex-col text-left min-w-0 flex-1">
          <div className="flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
            <span className="text-[11px] font-semibold text-slate-900 dark:text-slate-100 truncate">
              {activeBoard ? activeBoard.name : 'Select Board'}
            </span>
          </div>
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-400 dark:text-slate-500 shrink-0 transition-transform duration-200 ${
            isOpen ? 'rotate-180 text-brand-600 dark:text-brand-400' : 'group-hover:text-slate-600'
          }`}
        />
      </button>

      {/* Dropdown Popover */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-80 sm:w-88 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-900/15 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Header */}
          <div className="p-3 bg-slate-50/80 dark:bg-slate-800/50 border-b border-slate-200/70 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Layers className="w-4 h-4 text-brand-600 dark:text-brand-400" />
              <span className="text-xs font-bold text-slate-900 dark:text-slate-100 tracking-tight">
                Switch Active Board
              </span>
            </div>
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-200/70 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300">
              {boards.length} {boards.length === 1 ? 'board' : 'boards'}
            </span>
          </div>

          {/* Search Input (if more than 2 boards) */}
          {boards.length > 2 && (
            <div className="p-2 border-b border-slate-100 dark:border-slate-800">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search boards by name or ID..."
                  className="w-full bg-slate-100/70 dark:bg-slate-800/70 border border-transparent rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
                />
              </div>
            </div>
          )}

          {/* Boards List */}
          <div className="max-h-64 overflow-y-auto p-1.5 space-y-1">
            {filteredBoards.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-400">
                No matching boards found
              </div>
            ) : (
              filteredBoards.map((board) => {
                const isActive = board.board_id === activeBoardId || board.is_active;
                const isSwitching = switchingId === board.board_id;

                return (
                  <button
                    key={board.board_id}
                    type="button"
                    onClick={() => handleSelectBoard(board)}
                    disabled={isSwitching}
                    className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition-all group ${
                      isActive
                        ? 'bg-brand-50/80 dark:bg-brand-500/10 border border-brand-500/30 text-brand-900 dark:text-brand-200'
                        : 'hover:bg-slate-100/80 dark:hover:bg-slate-800/70 text-slate-700 dark:text-slate-300 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center space-x-2.5 min-w-0 flex-1 mr-2">
                      <div
                        className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                          isActive
                            ? 'bg-brand-500 text-white shadow-xs'
                            : 'bg-slate-200/80 dark:bg-slate-800 text-slate-500 dark:text-slate-400 group-hover:bg-slate-300 dark:group-hover:bg-slate-700'
                        }`}
                      >
                        <Kanban className="w-3.5 h-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center space-x-1.5">
                          <p className="text-xs font-semibold truncate leading-tight">
                            {board.name || 'Unnamed Board'}
                          </p>
                          {isActive && (
                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 uppercase tracking-wider shrink-0">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-400 dark:text-slate-500 truncate mt-0.5">
                          ID: {board.board_id}
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0 flex items-center">
                      {isSwitching ? (
                        <RefreshCw className="w-4 h-4 text-brand-500 animate-spin" />
                      ) : isActive ? (
                        <div className="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center">
                          <Check className="w-3 h-3 stroke-[2.5]" />
                        </div>
                      ) : (
                        <span className="text-[11px] text-slate-400 group-hover:text-brand-600 dark:group-hover:text-brand-400 font-medium">
                          Switch
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Footer Actions */}
          <div className="p-2.5 bg-slate-50/80 dark:bg-slate-800/40 border-t border-slate-200/70 dark:border-slate-800 flex items-center justify-between text-[11px]">
            <button
              type="button"
              onClick={() => {
                refreshBoards();
              }}
              disabled={isLoading}
              className="inline-flex items-center space-x-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition py-1 px-1.5 rounded"
            >
              <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>

            {onNavigateToBoards && (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  onNavigateToBoards();
                }}
                className="inline-flex items-center space-x-1 text-brand-600 dark:text-brand-400 hover:underline font-semibold py-1 px-1.5 rounded"
              >
                <span>Manage All Boards</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

