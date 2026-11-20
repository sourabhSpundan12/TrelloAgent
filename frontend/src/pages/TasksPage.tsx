import React, { useState, useEffect, useMemo } from 'react';
import {
  Search,
  ExternalLink,
  Layers,
  Bot,
  RefreshCw,
  Clock,
  CheckCircle2,
  Calendar,
  LayoutGrid,
  List,
  X,
  Filter,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { EmptyState } from '../components/common/EmptyState';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import { fetchTrelloTasks } from '../services/api';

export const TasksPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();
  const [cards, setCards] = useState<any[]>([]);
  const [lists, setLists] = useState<any[]>([]);
  const [boardId, setBoardId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedList, setSelectedList] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  const loadTasks = async (forceRefresh: boolean = false, silent: boolean = false) => {
    if (!isAuthenticated) return;
    if (!silent) setIsLoading(true);
    try {
      const data = await fetchTrelloTasks(undefined, activeBoardId || undefined, forceRefresh);
      if (data && data.status === 'SUCCESS') {
        setCards(data.cards || []);
        setLists(data.lists || []);
        setBoardId(data.board_id || activeBoardId || null);
      }
    } catch (err) {
      console.error('Failed to fetch Trello tasks:', err);
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTasks(false, false);
    // Real-time synchronization polling every 15 seconds to track external Trello changes
    const interval = setInterval(() => {
      loadTasks(false, true);
    }, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated, activeBoardId]);

  const filteredCards = useMemo(() => {
    return cards.filter((card) => {
      const matchesSearch =
        !searchQuery ||
        (card.name && card.name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (card.desc && card.desc.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (card.id && card.id.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesList =
        selectedList === 'ALL' ||
        card.list_id === selectedList ||
        card.list_name?.toLowerCase() === selectedList.toLowerCase();

      // Date Range Filtering (From Date - To Date)
      let matchesDate = true;
      if (fromDate || toDate) {
        let cardDate: Date | null = null;
        if (card.due) {
          const d = new Date(card.due);
          if (!isNaN(d.getTime())) cardDate = d;
        }
        // Fallback to creation date from Trello card ID (first 8 hex characters represent UNIX timestamp)
        if (!cardDate && card.id && card.id.length >= 8) {
          try {
            const ts = parseInt(card.id.substring(0, 8), 16) * 1000;
            const d = new Date(ts);
            if (!isNaN(d.getTime())) cardDate = d;
          } catch {
            cardDate = null;
          }
        }

        if (cardDate) {
          if (fromDate) {
            const fromDt = new Date(fromDate);
            fromDt.setHours(0, 0, 0, 0);
            if (cardDate < fromDt) matchesDate = false;
          }
          if (toDate) {
            const toDt = new Date(toDate);
            toDt.setHours(23, 59, 59, 999);
            if (cardDate > toDt) matchesDate = false;
          }
        } else {
          matchesDate = false;
        }
      }

      return matchesSearch && matchesList && matchesDate;
    });
  }, [cards, searchQuery, selectedList, fromDate, toDate]);

  const activeCount = useMemo(() => {
    return filteredCards.filter((c) => {
      const ln = (c.list_name || '').toLowerCase();
      return !ln.includes('done') && !ln.includes('completed');
    }).length;
  }, [filteredCards]);

  const completedCount = useMemo(() => {
    return filteredCards.filter((c) => {
      const ln = (c.list_name || '').toLowerCase();
      return ln.includes('done') || ln.includes('completed');
    }).length;
  }, [filteredCards]);

  return (
    <div className="space-y-6">
      {/* Conversational Callout */}
      <div className="p-4 rounded-2xl bg-brand-50/70 dark:bg-brand-500/10 border border-brand-200/80 dark:border-brand-500/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20 shrink-0">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-brand-900 dark:text-brand-300">
              Agentic Task Interaction {activeBoard ? `(${activeBoard.name})` : ''}
            </h3>
            <p className="text-brand-700/80 dark:text-brand-400/80 text-[11px] mt-0.5">
              To create or move cards, open the AI Assistant and speak naturally: &quot;Create task card Login API&quot; or &quot;Move Login API to Doing&quot;.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadTasks(true, false)}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh Board
          </Button>
          <a
            href={boardId ? `https://trello.com/b/${boardId}` : 'https://trello.com'}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 text-xs font-semibold shadow-xs transition"
          >
            <span>Open in Trello</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* Filter and View Mode Header */}
      <Card className="p-4 space-y-4">
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
          {/* Search Bar */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search live Trello cards by title or description..."
              className="w-full bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
            />
          </div>

          {/* Filters & View Toggle */}
          <div className="flex flex-wrap items-center gap-2">
            {/* List Filter */}
            <select
              value={selectedList}
              onChange={(e) => setSelectedList(e.target.value)}
              className="bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-700 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition"
            >
              <option value="ALL">All Lists ({cards.length})</option>
              {lists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>

            {/* View Mode Toggle */}
            <div className="flex items-center rounded-xl bg-slate-100 dark:bg-slate-800 p-0.5 border border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setViewMode('board')}
                className={`p-1.5 rounded-lg text-xs transition ${
                  viewMode === 'board'
                    ? 'bg-white dark:bg-slate-700 text-brand-600 dark:text-brand-400 shadow-xs'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
                title="Board View"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-lg text-xs transition ${
                  viewMode === 'list'
                    ? 'bg-white dark:bg-slate-700 text-brand-600 dark:text-brand-400 shadow-xs'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
                title="List View"
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchQuery('');
                setSelectedList('ALL');
                setFromDate('');
                setToDate('');
              }}
            >
              Reset
            </Button>
          </div>
        </div>

        {/* Date Range Filtering Strip (From Date - To Date) */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500 dark:text-slate-400 font-medium flex items-center space-x-1.5">
              <Calendar className="w-3.5 h-3.5 text-brand-500" />
              <span>Date Filter:</span>
            </span>

            {/* From Date */}
            <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 rounded-xl px-2.5 py-1">
              <span className="text-[10px] uppercase font-mono font-semibold text-slate-400">From</span>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="bg-transparent text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
                title="Filter tasks from date"
              />
            </div>

            {/* To Date */}
            <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 rounded-xl px-2.5 py-1">
              <span className="text-[10px] uppercase font-mono font-semibold text-slate-400">To</span>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="bg-transparent text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
                title="Filter tasks to date"
              />
            </div>

            {(fromDate || toDate) && (
              <button
                type="button"
                onClick={() => {
                  setFromDate('');
                  setToDate('');
                }}
                className="p-1 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-slate-200 dark:hover:bg-slate-700 transition"
                title="Clear date filters"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Active & Completed Counters */}
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
              Active: {activeCount}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              Completed: {completedCount}
            </span>
            <span className="text-[11px] font-mono text-slate-400">
              Total: {filteredCards.length}
            </span>
          </div>
        </div>
      </Card>

      {/* Main Board or List Display */}
      {filteredCards.length === 0 ? (
        <Card className="p-8">
          <EmptyState
            title="No cards found"
            description={
              cards.length === 0
                ? "No cards currently on the board or loading from Trello MCP. Try asking the AI Assistant: 'Create a task card Login API'."
                : "No cards match your filter criteria. Try clearing the search or list filter."
            }
            actionLabel="Refresh Board"
            onAction={loadTasks}
          />
        </Card>
      ) : viewMode === 'board' ? (
        /* Board Columns View */
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {(lists.length > 0 ? lists : [{ id: 'all', name: 'All Cards' }]).map((list) => {
            const listCards =
              list.id === 'all'
                ? filteredCards
                : filteredCards.filter((c) => c.list_id === list.id || c.list_name === list.name);

            return (
              <div key={list.id} className="flex flex-col space-y-3">
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-xs text-slate-800 dark:text-slate-200 uppercase tracking-wider">
                      {list.name}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-[10px] font-bold text-slate-600 dark:text-slate-400">
                      {listCards.length}
                    </span>
                  </div>
                </div>

                <div className="space-y-3">
                  {listCards.length === 0 ? (
                    <div className="p-4 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-800 text-center text-xs text-slate-400">
                      No cards in this list
                    </div>
                  ) : (
                    listCards.map((card) => (
                      <Card
                        key={card.id}
                        className="p-4 space-y-3 hover:border-brand-500/50 dark:hover:border-brand-500/50 transition cursor-pointer group shadow-xs"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-semibold text-xs text-slate-900 dark:text-slate-100 group-hover:text-brand-600 dark:group-hover:text-brand-400 transition">
                            {card.name}
                          </h4>
                          {card.url && (
                            <a
                              href={card.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-slate-400 hover:text-brand-600 transition shrink-0 p-0.5"
                              title="View in Trello"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>

                        {card.desc && (
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
                            {card.desc}
                          </p>
                        )}

                        <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-400">
                          <div className="flex items-center space-x-1.5">
                            <span className="font-mono">{card.id.slice(-6)}</span>
                            {((card.list_name || '').toLowerCase().includes('done') || (card.list_name || '').toLowerCase().includes('completed')) ? (
                              <span className="px-1.5 py-0.2 rounded-full text-[9px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                                Completed
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.2 rounded-full text-[9px] font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                                Active
                              </span>
                            )}
                          </div>
                          {card.due ? (
                            <span className="flex items-center space-x-1 text-slate-500">
                              <Calendar className="w-3 h-3" />
                              <span>{new Date(card.due).toLocaleDateString()}</span>
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">No due date</span>
                          )}
                        </div>
                      </Card>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* List / Table View */
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold">
                  <th className="py-3 px-4">Card Name</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Trello List</th>
                  <th className="py-3 px-4">Due Date</th>
                  <th className="py-3 px-4">Card ID</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredCards.map((card) => {
                  const isCompleted =
                    (card.list_name || '').toLowerCase().includes('done') ||
                    (card.list_name || '').toLowerCase().includes('completed');
                  return (
                    <tr key={card.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                      <td className="py-3 px-4 max-w-sm">
                        <span className="font-medium text-slate-900 dark:text-slate-100 block truncate">
                          {card.name}
                        </span>
                        {card.desc && (
                          <span className="text-[11px] text-slate-400 block truncate">{card.desc}</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {isCompleted ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                            Completed
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="neutral">{card.list_name || 'List'}</Badge>
                      </td>
                    <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">
                      {card.due ? new Date(card.due).toLocaleDateString() : '—'}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-400 text-[10px]">
                      {card.id}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {card.url && (
                        <a
                          href={card.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center space-x-1 text-brand-600 hover:underline text-[11px]"
                        >
                          <span>Open</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
