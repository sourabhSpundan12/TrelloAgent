import React, { useState, useEffect, useMemo } from 'react';
import {
  RefreshCw,
  Printer,
  ListTodo,
  CheckCircle2,
  Clock,
  Activity,
  Layers,
  AlertTriangle,
  UserCheck,
  UserX,
  Calendar,
  ExternalLink,
  Filter,
  FileSpreadsheet,
  X,
  Briefcase,
} from 'lucide-react';
import { Card, CardHeader } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import { fetchBoardTaskReport, fetchWorkloadReport } from '../services/api';
import { exportToExcel } from '../utils/excelExport';

interface BoardTask {
  id: string;
  card: string;
  description: string;
  employee: string;
  employee_count: number;
  list: string;
  status: 'Completed' | 'Pending';
  in_progress: boolean;
  is_overdue: boolean;
  overdue: string;
  due_date?: string | null;
  date: string;
  created_at: string;
  url?: string;
}

interface EmployeeAvailabilityItem {
  id: string;
  name: string;
  email: string;
  role: string;
  avatar: string;
  busy_cards_count: number;
  active_cards_count: number;
  total_assigned_cards: number;
  completed_cards_count: number;
  is_busy: boolean;
  current_tasks: string[];
  working_hours_allocated: number;
  working_hours_total: number;
}

export const ReportsPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();

  // Report Data State
  const [reportData, setReportData] = useState<any>(null);
  const [workloadReport, setWorkloadReport] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Date Filtering State
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  // Top N Display Control
  const [topNLimit, setTopNLimit] = useState<number>(5);

  const loadData = async (forceRefresh: boolean = false, silent: boolean = false) => {
    if (!isAuthenticated) return;
    if (!silent) setIsLoading(true);
    const boardToQuery = activeBoardId || undefined;

    try {
      const [boardRes, workloadRes] = await Promise.all([
        fetchBoardTaskReport(undefined, boardToQuery, fromDate || undefined, toDate || undefined, forceRefresh),
        fetchWorkloadReport(undefined, boardToQuery, forceRefresh),
      ]);

      if (boardRes && boardRes.status === 'SUCCESS') {
        setReportData(boardRes);
      }
      if (workloadRes && workloadRes.status === 'SUCCESS') {
        setWorkloadReport(workloadRes);
      }
    } catch (err) {
      console.error('Failed to load board tasks report:', err);
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData(false, false);
    // Real-time synchronization polling every 15 seconds to track external Trello changes
    const interval = setInterval(() => {
      loadData(false, true);
    }, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated, activeBoardId, fromDate, toDate]);

  const handleClearFilters = () => {
    setFromDate('');
    setToDate('');
  };

  // Availability metrics
  const availability = reportData?.availability || {};
  const busyCount = availability.busy_count || 0;
  const freeCount = availability.free_count || 0;
  const totalEmployees = availability.total_employees || busyCount + freeCount || 0;
  const busiestEmployees: EmployeeAvailabilityItem[] = availability.busiest_employees || [];
  const freeEmployees: EmployeeAvailabilityItem[] = availability.free_employees || [];

  const busyPercent = totalEmployees > 0 ? Math.round((busyCount / totalEmployees) * 100) : 0;
  const freePercent = totalEmployees > 0 ? 100 - busyPercent : 0;

  // Board Summary KPIs
  const summary = reportData?.summary || {};
  const totalCards = summary.total_cards ?? (reportData?.cards?.length || 0);
  const overdueCards = summary.overdue_cards ?? 0;
  const completedCards = summary.completed_cards ?? 0;
  const pendingCards = summary.pending_cards ?? 0;
  const inProgressCards = summary.in_progress_cards ?? 0;

  // Filtered Cards Table
  const cards: BoardTask[] = useMemo(() => {
    return reportData?.cards || [];
  }, [reportData]);

  // Excel Export Handler
  const handleExportExcel = () => {
    if (!cards || cards.length === 0) return;

    const boardName = reportData?.board_name || activeBoard?.name || 'Trello_Board';
    const cleanBoardName = boardName.replace(/[^a-zA-Z0-9_-]/g, '_');
    const dateStamp = new Date().toISOString().slice(0, 10);
    const filename = `PM_Hooks_${cleanBoardName}_Task_Report_${dateStamp}.xlsx`;

    const headers = [
      'Card',
      'Employee',
      'List',
      'Status',
      'Overdue',
      'Due Date',
      'Created Date',
      'Trello Card URL',
    ];

    const rows = cards.map((c) => [
      c.card || 'Untitled Card',
      c.employee || 'Unassigned',
      c.list || '—',
      c.status || 'Pending',
      c.overdue || '—',
      c.due_date ? new Date(c.due_date).toLocaleString() : '—',
      c.created_at ? new Date(c.created_at).toLocaleString() : '—',
      c.url || '—',
    ]);

    exportToExcel(headers, rows, filename, `${cleanBoardName.slice(0, 28)} Tasks`);
  };

  const listBreakdown: Record<string, number> = workloadReport?.list_breakdown || {};

  return (
    <div className="space-y-6">
      {/* Top Control Bar */}
      <Card className="p-5 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Sprint Workload & Board Reports (PM Hooks)
            </h2>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Real-time availability, board-wise card metrics, and Excel export calculated from live Trello cards.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
          {/* Active Board Display (Synchronized with top navbar) */}
          <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700">
            <Layers className="w-3.5 h-3.5 text-brand-500" />
            <span className="text-xs text-slate-500 font-medium">Board:</span>
            <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">
              {activeBoard?.name || reportData?.board_name || 'Primary Trello Board'}
            </span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => loadData(true, false)}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            icon={<Printer className="w-3.5 h-3.5" />}
          >
            Print
          </Button>
        </div>
      </Card>

      {/* ========================================================================= */}
      {/* 1. TODAY'S EMPLOYEE AVAILABILITY */}
      {/* ========================================================================= */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-brand-500/10 text-brand-400 border border-brand-500/20">
              <UserCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Today's Employee Availability
              </h3>
              <p className="text-[11px] text-slate-500">
                Calculated entirely from live Trello card assignments across today's 8-hour working period.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400 text-[11px]">Show Top:</span>
            {[3, 5, 10].map((num) => (
              <button
                key={num}
                onClick={() => setTopNLimit(num)}
                className={`px-2 py-0.5 rounded text-xs font-semibold transition ${
                  topNLimit === num
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {num}
              </button>
            ))}
          </div>
        </div>

        {/* Availability KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Busy Employees Card */}
          <Card className="p-5 border-l-4 border-l-amber-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-500 uppercase tracking-wider flex items-center space-x-1.5">
                <Briefcase className="w-3.5 h-3.5" />
                <span>Busy Employees Today</span>
              </span>
              <Badge variant="warning">{busyPercent}% of team</Badge>
            </div>
            <h4 className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
              {busyCount} <span className="text-sm font-normal text-slate-400">/ {totalEmployees} Employees</span>
            </h4>
            <p className="text-[11px] text-slate-500 mt-1">
              Have ≥1 active assigned Trello card whose due date has not yet arrived
            </p>
          </Card>

          {/* Free Employees Card */}
          <Card className="p-5 border-l-4 border-l-emerald-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-500 uppercase tracking-wider flex items-center space-x-1.5">
                <UserCheck className="w-3.5 h-3.5" />
                <span>Free Employees Today</span>
              </span>
              <Badge variant="success">{freePercent}% available</Badge>
            </div>
            <h4 className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1.5">
              {freeCount} <span className="text-sm font-normal text-slate-400">/ {totalEmployees} Employees</span>
            </h4>
            <p className="text-[11px] text-slate-500 mt-1">
              No assigned Trello cards to work on today (100% capacity free)
            </p>
          </Card>

          {/* 8-Hour Working Period Card */}
          <Card className="p-5 border-l-4 border-l-sky-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-sky-500 uppercase tracking-wider flex items-center space-x-1.5">
                <Clock className="w-3.5 h-3.5" />
                <span>Working Period Window</span>
              </span>
              <Badge variant="info">8 Hours</Badge>
            </div>
            <h4 className="text-2xl font-bold text-sky-600 dark:text-sky-400 mt-1.5">
              8-Hour Shift
            </h4>
            <p className="text-[11px] text-slate-500 mt-1">
              Active working capacity tracking for today ({totalEmployees * 8}h total pool)
            </p>
          </Card>
        </div>

        {/* Top N Busiest & Top N Free Employees Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Top N Busiest Employees */}
          <Card className="p-4 flex flex-col justify-between">
            <CardHeader
              title={`Top ${topNLimit} Busiest Employees`}
              subtitle="Employees currently holding the highest active assigned Trello workload"
            />
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80 mt-2">
              {busiestEmployees.length === 0 ? (
                <div className="py-8 text-center text-slate-400 text-xs italic">
                  No busy employees currently. All team members are free today!
                </div>
              ) : (
                busiestEmployees.slice(0, topNLimit).map((emp, idx) => (
                  <div
                    key={emp.id}
                    className="py-3 flex items-center justify-between gap-3 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 px-2 rounded-lg transition"
                  >
                    <div className="flex items-center space-x-3 min-w-0">
                      <span className="w-5 text-center text-xs font-mono font-bold text-slate-400">
                        #{idx + 1}
                      </span>
                      <img
                        src={emp.avatar}
                        alt={emp.name}
                        className="w-9 h-9 rounded-xl object-cover ring-1 ring-slate-700 shrink-0"
                      />
                      <div className="min-w-0">
                        <h5 className="text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
                          {emp.name}
                        </h5>
                        <p className="text-[10px] text-slate-500 truncate">{emp.role}</p>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      <div className="text-right">
                        <span className="text-xs font-bold text-amber-400 font-mono">
                          {emp.active_cards_count} Active Cards
                        </span>
                        <span className="block text-[10px] text-slate-400">
                          {emp.working_hours_allocated}h / 8h booked
                        </span>
                      </div>
                      <Badge variant="warning">BUSY</Badge>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          {/* Top N Free Employees */}
          <Card className="p-4 flex flex-col justify-between">
            <CardHeader
              title={`Top ${topNLimit} Free Employees`}
              subtitle="Employees with zero assigned Trello cards today, ready for new tasks"
            />
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80 mt-2">
              {freeEmployees.length === 0 ? (
                <div className="py-8 text-center text-slate-400 text-xs italic">
                  No free employees. The entire team currently has assigned work.
                </div>
              ) : (
                freeEmployees.slice(0, topNLimit).map((emp, idx) => (
                  <div
                    key={emp.id}
                    className="py-3 flex items-center justify-between gap-3 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 px-2 rounded-lg transition"
                  >
                    <div className="flex items-center space-x-3 min-w-0">
                      <span className="w-5 text-center text-xs font-mono font-bold text-slate-400">
                        #{idx + 1}
                      </span>
                      <img
                        src={emp.avatar}
                        alt={emp.name}
                        className="w-9 h-9 rounded-xl object-cover ring-1 ring-slate-700 shrink-0"
                      />
                      <div className="min-w-0">
                        <h5 className="text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
                          {emp.name}
                        </h5>
                        <p className="text-[10px] text-slate-500 truncate">{emp.role}</p>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      <div className="text-right">
                        <span className="text-xs font-bold text-emerald-400 font-mono">
                          0 Cards Assigned
                        </span>
                        <span className="block text-[10px] text-slate-400">
                          8h capacity available
                        </span>
                      </div>
                      <Badge variant="success">FREE</Badge>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. BOARD-WISE TASK REPORTS & SUMMARY CARDS */}
      {/* ========================================================================= */}
      <div className="space-y-4 pt-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Board-wise Task Reports
              </h3>
              <p className="text-[11px] text-slate-500">
                Live card table and metrics for selected board: {reportData?.board_name || 'Primary Trello Board'}
              </p>
            </div>
          </div>
        </div>

        {/* 5 Summary KPI Cards for Selected Board */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {/* Total Cards */}
          <Card className="p-4">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
              <ListTodo className="w-3.5 h-3.5 text-slate-400" />
              <span>Total Cards</span>
            </span>
            <h4 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
              {totalCards}
            </h4>
            <p className="text-[10px] text-slate-500 mt-0.5">Across all lists</p>
          </Card>

          {/* Overdue Cards */}
          <Card className="p-4 border-l-2 border-l-rose-500">
            <span className="text-[11px] font-semibold text-rose-500 uppercase tracking-wider flex items-center space-x-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Overdue Cards</span>
            </span>
            <h4 className="text-2xl font-bold text-rose-500 mt-1">
              {overdueCards}
            </h4>
            <p className="text-[10px] text-slate-500 mt-0.5">Missed deadline</p>
          </Card>

          {/* Completed Cards */}
          <Card className="p-4 border-l-2 border-l-emerald-500">
            <span className="text-[11px] font-semibold text-emerald-500 uppercase tracking-wider flex items-center space-x-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Completed Cards</span>
            </span>
            <h4 className="text-2xl font-bold text-emerald-500 mt-1">
              {completedCards}
            </h4>
            <p className="text-[10px] text-slate-500 mt-0.5">In Done lists</p>
          </Card>

          {/* Pending Cards */}
          <Card className="p-4 border-l-2 border-l-purple-500">
            <span className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider flex items-center space-x-1.5">
              <Activity className="w-3.5 h-3.5" />
              <span>Pending Cards</span>
            </span>
            <h4 className="text-2xl font-bold text-purple-400 mt-1">
              {pendingCards}
            </h4>
            <p className="text-[10px] text-slate-500 mt-0.5">To Do / Backlog</p>
          </Card>

          {/* In Progress Cards */}
          <Card className="p-4 border-l-2 border-l-sky-500">
            <span className="text-[11px] font-semibold text-sky-400 uppercase tracking-wider flex items-center space-x-1.5">
              <Clock className="w-3.5 h-3.5" />
              <span>In Progress</span>
            </span>
            <h4 className="text-2xl font-bold text-sky-400 mt-1">
              {inProgressCards}
            </h4>
            <p className="text-[10px] text-slate-500 mt-0.5">Actively in Doing</p>
          </Card>
        </div>

        {/* ========================================================================= */}
        {/* 3. DATE-WISE FILTERING AND EXCEL EXPORT */}
        {/* ========================================================================= */}
        <Card className="overflow-hidden border border-slate-200 dark:border-slate-800">
          <div className="p-4 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                <span>Board Cards Table</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono font-normal">
                  {cards.length} records
                </span>
              </h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Live card table with assigned employees, column lists, status, and overdue indicators.
              </p>
            </div>

            {/* Filter and Download Controls */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Date Filters */}
              <div className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-[10px] text-slate-400 font-medium">From:</span>
                <input
                  type="date"
                  aria-label="Filter from date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="bg-transparent text-xs text-slate-900 dark:text-slate-100 focus:outline-none"
                />
              </div>

              <div className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-[10px] text-slate-400 font-medium">To:</span>
                <input
                  type="date"
                  aria-label="Filter to date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="bg-transparent text-xs text-slate-900 dark:text-slate-100 focus:outline-none"
                />
              </div>

              {(fromDate || toDate) && (
                <button
                  onClick={handleClearFilters}
                  title="Clear date filters"
                  className="p-1 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-300 transition"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}

              {/* Excel Download Button */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportExcel}
                disabled={cards.length === 0}
                icon={<FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />}
                title="Download filtered board task records in Excel (.xlsx) format"
              >
                Download Excel (.xlsx)
              </Button>
            </div>
          </div>

          {/* Cards Table */}
          {isLoading ? (
            <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-2">
              <RefreshCw className="w-6 h-6 animate-spin text-brand-500" />
              <p className="text-xs">Loading live Trello board cards...</p>
            </div>
          ) : cards.length === 0 ? (
            <div className="p-12 text-center text-slate-400 space-y-2">
              <p className="font-semibold text-slate-300">No cards found for this board</p>
              <p className="text-xs text-slate-500">
                {fromDate || toDate
                  ? 'No cards match the selected date range. Try clearing the filter.'
                  : 'Add cards to this board on Trello or select another board.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-100 dark:bg-slate-800/60 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-200 dark:border-slate-800">
                    <th className="py-3 px-4">Card</th>
                    <th className="py-3 px-4">Employee</th>
                    <th className="py-3 px-4">List</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Overdue</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
                  {cards.map((task) => {
                    const isCompleted = task.status === 'Completed';

                    return (
                      <tr
                        key={task.id}
                        className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition text-slate-200"
                      >
                        {/* Card Name */}
                        <td className="py-3 px-4 font-semibold text-slate-900 dark:text-slate-100 max-w-[240px]">
                          <div className="flex items-center space-x-1.5">
                            <span className="truncate" title={task.card}>
                              {task.card}
                            </span>
                            {task.url && (
                              <a
                                href={task.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-brand-400 hover:text-brand-300 shrink-0"
                                title="Open card on Trello"
                              >
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        </td>

                        {/* Employee */}
                        <td className="py-3 px-4 text-slate-700 dark:text-slate-300 font-medium">
                          {task.employee === 'Unassigned' ? (
                            <span className="text-slate-400 italic">Unassigned</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 font-semibold border border-slate-200 dark:border-slate-700">
                              {task.employee}
                            </span>
                          )}
                        </td>

                        {/* List */}
                        <td className="py-3 px-4 text-slate-700 dark:text-slate-300">
                          <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[11px] font-mono border border-slate-200 dark:border-slate-700">
                            {task.list}
                          </span>
                        </td>

                        {/* Status (Pending or Completed) */}
                        <td className="py-3 px-4">
                          <Badge variant={isCompleted ? 'success' : 'neutral'}>
                            {task.status.toUpperCase()}
                          </Badge>
                        </td>

                        {/* Overdue */}
                        <td className="py-3 px-4 font-mono text-[11px]">
                          {task.is_overdue ? (
                            <span className="inline-flex items-center space-x-1 text-rose-400 font-semibold bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
                              <AlertTriangle className="w-3 h-3 shrink-0" />
                              <span>{task.overdue}</span>
                            </span>
                          ) : isCompleted ? (
                            <span className="text-slate-500">—</span>
                          ) : task.overdue === 'On Time' ? (
                            <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                              <span>On Time</span>
                            </span>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* ========================================================================= */}
      {/* Existing List Breakdown (Preserved as requested) */}
      {/* ========================================================================= */}
      {Object.keys(listBreakdown).length > 0 && (
        <Card className="overflow-hidden">
          <CardHeader
            title="Trello Board List Distribution"
            subtitle="Real-time count of cards organized by list"
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold">
                  <th className="py-3 px-4">Trello List Name</th>
                  <th className="py-3 px-4">Card Count</th>
                  <th className="py-3 px-4">Share of Board</th>
                  <th className="py-3 px-4">Status Category</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {Object.entries(listBreakdown).map(([listName, count]) => {
                  const share = totalCards > 0 ? Math.round((count / totalCards) * 100) : 0;
                  const isDone = listName.toLowerCase().includes('done');
                  const isDoing =
                    listName.toLowerCase().includes('doing') ||
                    listName.toLowerCase().includes('progress');

                  return (
                    <tr key={listName} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-slate-100">
                        {listName}
                      </td>
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-700 dark:text-slate-300">
                        {count}
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="flex items-center space-x-2">
                          <div className="w-24 bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                            <div
                              style={{ width: `${share}%` }}
                              className={`h-full ${
                                isDone ? 'bg-emerald-500' : isDoing ? 'bg-sky-500' : 'bg-purple-500'
                              }`}
                            />
                          </div>
                          <span className="font-mono text-slate-500 text-[11px]">{share}%</span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <Badge variant={isDone ? 'success' : isDoing ? 'info' : 'neutral'}>
                          {isDone ? 'COMPLETED' : isDoing ? 'ACTIVE' : 'BACKLOG'}
                        </Badge>
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
