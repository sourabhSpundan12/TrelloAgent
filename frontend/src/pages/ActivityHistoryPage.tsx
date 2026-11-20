import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Search,
  PlusCircle,
  Edit3,
  MoveRight,
  CheckCircle,
  CheckCircle2,
  Clock,
  ExternalLink,
  ShieldAlert,
  XCircle,
  RefreshCw,
  User,
  Calendar,
  X,
  FileSpreadsheet,
  Layers,
  Activity,
  AlertTriangle,
  Play,
  UserCheck,
} from 'lucide-react';
import { Card, CardHeader } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { EmptyState } from '../components/common/EmptyState';
import { useAuth } from '../context/AuthContext';
import { fetchLiveActivities } from '../services/api';
import { exportToExcel } from '../utils/excelExport';

export const ActivityHistoryPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [activities, setActivities] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  const loadActivities = async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    try {
      const data = await fetchLiveActivities();
      if (data && data.status === 'SUCCESS') {
        setActivities(data.activities || []);
      }
    } catch (err) {
      console.error('Failed to load live activities:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadActivities();
    const interval = setInterval(loadActivities, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  const filteredActivities = useMemo(() => {
    return activities.filter((act) => {
      // Text Search
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        (act.title && act.title.toLowerCase().includes(q)) ||
        (act.action_id && act.action_id.toLowerCase().includes(q)) ||
        (act.tool_name && act.tool_name.toLowerCase().includes(q)) ||
        (act.user_email && act.user_email.toLowerCase().includes(q)) ||
        (act.user_name && act.user_name.toLowerCase().includes(q)) ||
        (act.description && act.description.toLowerCase().includes(q)) ||
        (act.board_name && act.board_name.toLowerCase().includes(q));

      // Status Filter
      const statusVal = String(act.status || 'EXECUTED').toUpperCase();
      const matchesStatus =
        selectedStatus === 'ALL' ||
        statusVal === selectedStatus.toUpperCase() ||
        (selectedStatus === 'ACTIVE' && (statusVal === 'PENDING' || statusVal === 'IN_PROGRESS'));

      // Event Type Filter
      const typeVal = String(act.action_type || act.event_type || '').toUpperCase();
      const matchesType =
        selectedType === 'ALL' ||
        typeVal === selectedType.toUpperCase() ||
        typeVal.includes(selectedType.toUpperCase());

      // Date Range Filter
      let matchesDate = true;
      if (fromDate || toDate) {
        try {
          const actDate = new Date(act.created_at);
          if (fromDate) {
            const fDate = new Date(fromDate);
            fDate.setHours(0, 0, 0, 0);
            if (actDate < fDate) matchesDate = false;
          }
          if (toDate) {
            const tDate = new Date(toDate);
            tDate.setHours(23, 59, 59, 999);
            if (actDate > tDate) matchesDate = false;
          }
        } catch {
          // ignore date parse errors
        }
      }

      return matchesSearch && matchesStatus && matchesType && matchesDate;
    });
  }, [activities, searchQuery, selectedStatus, selectedType, fromDate, toDate]);

  // Summary Metrics
  const totalCount = activities.length;
  const executedCount = activities.filter((a) => a.status === 'EXECUTED' || a.status === 'COMPLETED').length;
  const pendingCount = activities.filter((a) => a.status === 'PENDING').length;
  const inProgressCount = activities.filter((a) => a.status === 'IN_PROGRESS').length;

  const handleClearFilters = () => {
    setSearchQuery('');
    setSelectedStatus('ALL');
    setSelectedType('ALL');
    setFromDate('');
    setToDate('');
  };

  const handleExportAuditExcel = () => {
    if (filteredActivities.length === 0) return;
    const dateStamp = new Date().toISOString().slice(0, 10);
    const filename = `PM_Hooks_Activity_Audit_Log_${dateStamp}.xlsx`;

    const headers = [
      'Action ID',
      'Event Type',
      'Title',
      'Description',
      'Actor / User',
      'Status',
      'Tool / Engine',
      'Timestamp',
      'Board Name',
      'Trello Card URL',
    ];

    const rows = filteredActivities.map((act) => [
      act.action_id || act.id || '—',
      act.action_type || act.event_type || 'OPERATION',
      act.title || 'Untitled Action',
      act.description || '—',
      act.user_name ? `${act.user_name} (${act.user_email || ''})` : (act.user_email || 'System'),
      (act.status || 'EXECUTED').toUpperCase(),
      act.tool_name || 'Platform Tool',
      act.created_at ? new Date(act.created_at).toLocaleString() : '—',
      act.board_name || 'Primary Board',
      act.card_url || '—',
    ]);

    exportToExcel(headers, rows, filename, 'Activity Audit');
  };

  const getStatusIcon = (status: string, eventType?: string) => {
    const s = String(status || '').toUpperCase();
    const t = String(eventType || '').toUpperCase();

    if (t === 'TASK_ASSIGNED') return <UserCheck className="w-4 h-4 text-sky-500" />;
    if (t === 'TASK_STARTED') return <Play className="w-4 h-4 text-indigo-500" />;
    if (t === 'TASK_COMPLETED' || s === 'COMPLETED') return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
    if (t === 'DUE_DATE_UPDATED') return <Calendar className="w-4 h-4 text-purple-500" />;

    switch (s) {
      case 'EXECUTED':
        return <CheckCircle className="w-4 h-4 text-emerald-500" />;
      case 'PENDING':
        return <ShieldAlert className="w-4 h-4 text-amber-500" />;
      case 'IN_PROGRESS':
        return <Clock className="w-4 h-4 text-sky-500" />;
      case 'REJECTED':
      case 'CANCELLED':
      case 'FAILED':
        return <XCircle className="w-4 h-4 text-rose-500" />;
      default:
        return <Activity className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="p-4 border-l-4 border-l-slate-500">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
            <History className="w-3.5 h-3.5 text-slate-400" />
            <span>Total Logged Events</span>
          </span>
          <h4 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
            {totalCount}
          </h4>
          <p className="text-[10px] text-slate-500 mt-0.5">Permanent audit trail in MongoDB</p>
        </Card>

        <Card className="p-4 border-l-4 border-l-emerald-500">
          <span className="text-[11px] font-semibold text-emerald-500 uppercase tracking-wider flex items-center space-x-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Executed Mutations</span>
          </span>
          <h4 className="text-2xl font-bold text-emerald-500 mt-1">
            {executedCount}
          </h4>
          <p className="text-[10px] text-slate-500 mt-0.5">Applied to Trello board</p>
        </Card>

        <Card className="p-4 border-l-4 border-l-amber-500">
          <span className="text-[11px] font-semibold text-amber-500 uppercase tracking-wider flex items-center space-x-1.5">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Pending Approvals</span>
          </span>
          <h4 className="text-2xl font-bold text-amber-500 mt-1">
            {pendingCount}
          </h4>
          <p className="text-[10px] text-slate-500 mt-0.5">Awaiting user confirmation</p>
        </Card>

        <Card className="p-4 border-l-4 border-l-sky-500">
          <span className="text-[11px] font-semibold text-sky-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>Active / In Progress</span>
          </span>
          <h4 className="text-2xl font-bold text-sky-400 mt-1">
            {inProgressCount}
          </h4>
          <p className="text-[10px] text-slate-500 mt-0.5">Currently active tasks</p>
        </Card>
      </div>

      {/* Control & Filter Bar */}
      <Card className="p-4 space-y-3">
        <div className="flex flex-col lg:flex-row gap-3 items-stretch lg:items-center justify-between">
          {/* Search Input */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              aria-label="Search audit trail"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search audit trail by title, action ID, user, or tool..."
              className="w-full bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportAuditExcel}
              disabled={filteredActivities.length === 0}
              icon={<FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />}
              title="Download activity audit log as Excel spreadsheet"
            >
              Export Audit (.xlsx)
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={loadActivities}
              disabled={isLoading}
              icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
            >
              Refresh
            </Button>

            {(searchQuery || selectedStatus !== 'ALL' || selectedType !== 'ALL' || fromDate || toDate) && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearFilters}
                icon={<X className="w-3.5 h-3.5" />}
              >
                Clear Filters
              </Button>
            )}
          </div>
        </div>

        {/* Filter Dropdowns Row */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100 dark:border-slate-800 text-xs">
          {/* Status Filter */}
          <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
            <span className="text-[10px] text-slate-400 font-medium">Status:</span>
            <select
              aria-label="Filter by status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Statuses ({totalCount})</option>
              <option value="EXECUTED">Executed</option>
              <option value="PENDING">Pending Approval</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="COMPLETED">Completed</option>
              <option value="REJECTED">Cancelled / Rejected</option>
            </select>
          </div>

          {/* Event Type Filter */}
          <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
            <span className="text-[10px] text-slate-400 font-medium">Event Type:</span>
            <select
              aria-label="Filter by event type"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Events</option>
              <option value="CARD_CREATED">Card Created</option>
              <option value="CARD_MOVED">Card Moved</option>
              <option value="TASK_ASSIGNED">Task Assigned</option>
              <option value="TASK_STARTED">Task Started</option>
              <option value="TASK_COMPLETED">Task Completed</option>
              <option value="DUE_DATE_UPDATED">Due Date Updated</option>
              <option value="BOARD_ACTIVATED">Board Activated</option>
            </select>
          </div>

          {/* From Date */}
          <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[10px] text-slate-400 font-medium">From:</span>
            <input
              type="date"
              aria-label="Filter from date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="bg-transparent text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
            />
          </div>

          {/* To Date */}
          <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[10px] text-slate-400 font-medium">To:</span>
            <input
              type="date"
              aria-label="Filter to date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="bg-transparent text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
            />
          </div>
        </div>
      </Card>

      {/* Activity Timeline View */}
      <Card className="p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800 mb-6">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                Persistent Audit Trail Timeline
              </h3>
              <p className="text-[11px] text-slate-500">
                Displaying {filteredActivities.length} of {totalCount} total logged activities.
              </p>
            </div>
          </div>
        </div>

        {isLoading && activities.length === 0 ? (
          <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin text-brand-500" />
            <p className="text-xs">Loading audit trail records from MongoDB Atlas...</p>
          </div>
        ) : filteredActivities.length === 0 ? (
          <EmptyState
            title="No activity records found"
            description={
              activities.length === 0
                ? "No audit records recorded yet. Any actions performed via AI Assistant, Tasks, or Board management will be permanently saved here."
                : "No events match your current filter criteria. Try clearing or expanding the date/status filter."
            }
            actionLabel="Refresh Activities"
            onAction={loadActivities}
          />
        ) : (
          <div className="relative pl-6 space-y-6 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-800">
            {filteredActivities.map((act) => {
              const statusVal = String(act.status || 'EXECUTED').toUpperCase();
              const eventType = String(act.action_type || act.event_type || 'OPERATION').toUpperCase();
              const isExecuted = statusVal === 'EXECUTED' || statusVal === 'COMPLETED';
              const isPending = statusVal === 'PENDING';
              const isFailed = statusVal === 'FAILED' || statusVal === 'REJECTED';

              return (
                <div key={act.id || act.action_id} className="relative flex items-start space-x-4 text-xs group">
                  {/* Event Marker Node */}
                  <div className="absolute -left-6 mt-1 p-1 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 ring-4 ring-white dark:ring-slate-900 shrink-0">
                    {getStatusIcon(act.status, act.action_type || act.event_type)}
                  </div>

                  {/* Event Content Container */}
                  <div className="flex-1 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-800 space-y-2.5 hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-xs transition">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-300 font-bold text-[10px]">
                          <User className="w-3.5 h-3.5" />
                        </div>
                        <span className="font-semibold text-slate-900 dark:text-slate-100">
                          {act.user_name || act.user_email || 'Authenticated User'}
                        </span>
                        <span className="text-slate-400">•</span>
                        <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                          {act.tool_name || 'System'}
                        </span>
                      </div>

                      <div className="flex items-center space-x-2 text-[11px] text-slate-400 font-mono">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span>{new Date(act.created_at).toLocaleString()}</span>
                      </div>
                    </div>

                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                          <p className="text-slate-900 dark:text-slate-100 font-bold text-xs">
                            {act.title}
                          </p>
                          <span className="px-2 py-0.5 rounded-full bg-slate-200/60 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[10px] font-mono font-medium">
                            {eventType.replace(/_/g, ' ')}
                          </span>
                        </div>
                        {act.description && (
                          <p className="text-[11px] text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">
                            {act.description}
                          </p>
                        )}
                      </div>

                      <Badge
                        variant={
                          isExecuted
                            ? 'success'
                            : isFailed
                            ? 'danger'
                            : isPending
                            ? 'warning'
                            : 'neutral'
                        }
                      >
                        {statusVal}
                      </Badge>
                    </div>

                    <div className="pt-2 flex flex-wrap items-center justify-between text-[10px] text-slate-400 border-t border-slate-200/60 dark:border-slate-800/80 gap-2">
                      <div className="flex items-center space-x-3">
                        <span className="font-mono">ID: {act.action_id || act.id}</span>
                        {act.board_name && (
                          <span className="inline-flex items-center space-x-1 text-slate-500 font-mono">
                            <Layers className="w-2.5 h-2.5" />
                            <span>{act.board_name}</span>
                          </span>
                        )}
                      </div>

                      {act.card_url && (
                        <a
                          href={act.card_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center space-x-1 text-emerald-600 dark:text-emerald-400 hover:underline font-semibold"
                        >
                          <span>View in Trello</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
};
