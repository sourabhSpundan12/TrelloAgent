import React, { useState, useEffect, useMemo } from 'react';
import {
  Search,
  Building,
  UserCheck,
  RefreshCw,
  ExternalLink,
  Calendar,
  Layers,
  Inbox,
  AlertCircle,
  CheckCircle2,
  Play,
  History,
  Filter,
  ArrowRight,
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Edit3,
  Mail,
  User,
  Download,
  FileSpreadsheet,
} from 'lucide-react';
import { exportToExcel } from '../utils/excelExport';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Modal } from '../components/common/Modal';
import { EmptyState } from '../components/common/EmptyState';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import {
  fetchTeamWorkload,
  fetchEmployeeSummaries,
  fetchEmployeeAssignments,
  fetchAssignmentHistory,
  updateAssignmentDueDate,
  startAssignmentTask,
  completeAssignmentTask,
} from '../services/api';
import {
  Employee,
  EmployeeTaskReportSummary,
  TaskAssignment,
  TaskAssignmentHistoryItem,
} from '../types';

interface RealTeamMember extends Employee {
  username?: string;
  todoCount?: number;
  tasks?: Array<{
    id: string;
    title: string;
    description: string;
    status: string;
    list_name: string;
    due_date?: string | null;
    is_overdue?: boolean;
    url?: string;
  }>;
}

interface UnassignedTask {
  id: string;
  title: string;
  description: string;
  status: string;
  list_name: string;
  due_date?: string | null;
  is_overdue?: boolean;
  url?: string;
}

const MemberAvatar: React.FC<{
  name: string;
  avatarUrl?: string;
  size?: 'md' | 'lg' | 'xl';
}> = ({ name, avatarUrl, size = 'md' }) => {
  const [imgError, setImgError] = useState(false);
  const sizeClasses =
    size === 'xl'
      ? 'w-16 h-16 text-lg'
      : size === 'lg'
      ? 'w-14 h-14 text-base'
      : 'w-12 h-12 text-sm';
  const initials = name
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const colors = [
    'from-emerald-500/20 to-teal-500/20 text-emerald-400 border-emerald-500/30 ring-emerald-500/20',
    'from-sky-500/20 to-blue-500/20 text-sky-400 border-sky-500/30 ring-sky-500/20',
    'from-purple-500/20 to-violet-500/20 text-purple-400 border-purple-500/30 ring-purple-500/20',
    'from-amber-500/20 to-orange-500/20 text-amber-400 border-amber-500/30 ring-amber-500/20',
    'from-rose-500/20 to-pink-500/20 text-rose-400 border-rose-500/30 ring-rose-500/20',
  ];
  const colorIndex = (name.charCodeAt(0) + (name.charCodeAt(1) || 0)) % colors.length;
  const colorClass = colors[colorIndex];

  if (avatarUrl && !imgError) {
    return (
      <img
        src={avatarUrl}
        alt={name}
        onError={() => setImgError(true)}
        className={`${sizeClasses} rounded-2xl object-cover ring-2 ring-slate-700/60 shadow-md shrink-0`}
      />
    );
  }

  return (
    <div
      className={`${sizeClasses} rounded-2xl bg-gradient-to-br ${colorClass} font-bold flex items-center justify-center border ring-2 shadow-md shrink-0`}
    >
      {initials}
    </div>
  );
};

export const EmployeesPage: React.FC = () => {
  const { user, isAuthenticated } = useAuth();
  const { boards, activeBoard, activeBoardId } = useBoard();

  // Active view: 'directory' (all employee cards) | 'details' (single employee profile & tasks)
  const [activeTab, setActiveTab] = useState<'directory' | 'details'>('directory');

  // Collaborator & Workload State
  const [employees, setEmployees] = useState<RealTeamMember[]>([]);
  const [unassignedTasks, setUnassignedTasks] = useState<UnassignedTask[]>([]);
  const [unassignedCount, setUnassignedCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(false);

  // Summaries & Selected Employee State
  const [employeeSummaries, setEmployeeSummaries] = useState<EmployeeTaskReportSummary[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<RealTeamMember | null>(null);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('');
  const [employeeAssignments, setEmployeeAssignments] = useState<TaskAssignment[]>([]);
  const [isLoadingAssignments, setIsLoadingAssignments] = useState(false);

  // Filters for Task Tracking
  const [boardFilter, setBoardFilter] = useState<string>(activeBoardId || 'all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [fromDateFilter, setFromDateFilter] = useState<string>('');
  const [toDateFilter, setToDateFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('ALL');

  // Modals state
  const [showUnassignedModal, setShowUnassignedModal] = useState(false);
  const [historyModalAssignment, setHistoryModalAssignment] = useState<TaskAssignment | null>(null);
  const [assignmentHistoryList, setAssignmentHistoryList] = useState<TaskAssignmentHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const [dueDateModalAssignment, setDueDateModalAssignment] = useState<TaskAssignment | null>(null);
  const [newDueDateValue, setNewDueDateValue] = useState<string>('');
  const [dueDateReasonValue, setDueDateReasonValue] = useState<string>('');
  const [isUpdatingDueDate, setIsUpdatingDueDate] = useState(false);

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Load team members and summaries
  const loadAllData = async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      const [workloadData, summariesData] = await Promise.all([
        fetchTeamWorkload(undefined, activeBoardId || undefined).catch(() => null),
        fetchEmployeeSummaries(boardFilter !== 'all' ? boardFilter : undefined).catch(() => []),
      ]);

      if (workloadData && workloadData.status === 'SUCCESS') {
        const membersList: RealTeamMember[] = Array.isArray(workloadData.members) ? workloadData.members : [];
        setEmployees(membersList);
        setUnassignedTasks(Array.isArray(workloadData.unassigned_tasks) ? workloadData.unassigned_tasks : []);
        setUnassignedCount(workloadData.unassigned_count || 0);

        // Keep selectedEmployee up-to-date if one is currently selected
        if (selectedEmployee) {
          const fresh = membersList.find((m: RealTeamMember) => m.id === selectedEmployee.id);
          if (fresh) setSelectedEmployee(fresh);
        }
      }

      if (Array.isArray(summariesData)) {
        setEmployeeSummaries(summariesData);
      }
    } catch (err: any) {
      console.error('Failed to load employee data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, [isAuthenticated, activeBoardId]);

  // Load selected employee's assignments when filter or selection changes
  const loadSelectedAssignments = async (targetId?: string) => {
    const empId = targetId || selectedEmployeeId;
    if (!empId) return;
    setIsLoadingAssignments(true);
    setEmployeeAssignments([]); // Clear immediately so previous employee's tasks are never retained

    const targetSummary = employeeSummaries.find((s) => s.employee_id === empId);
    const targetName = targetSummary?.employee_name?.toLowerCase().trim();

    try {
      const tasks = await fetchEmployeeAssignments(empId, {
        boardId: boardFilter !== 'all' ? boardFilter : undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        fromDate: fromDateFilter || undefined,
        toDate: toDateFilter || undefined,
      });

      if (Array.isArray(tasks)) {
        let filteredTasks = tasks;
        if (fromDateFilter || toDateFilter) {
          const fromTs = fromDateFilter ? new Date(`${fromDateFilter}T00:00:00`).getTime() : null;
          const toTs = toDateFilter ? new Date(`${toDateFilter}T23:59:59.999`).getTime() : null;
          filteredTasks = filteredTasks.filter((t) => {
            const datesToCheck: number[] = [];
            if (t.due_date) {
              const d = new Date(t.due_date).getTime();
              if (!isNaN(d)) datesToCheck.push(d);
            }
            if (t.assigned_at) {
              const a = new Date(t.assigned_at).getTime();
              if (!isNaN(a)) datesToCheck.push(a);
            }
            if (t.created_at) {
              const c = new Date(t.created_at).getTime();
              if (!isNaN(c)) datesToCheck.push(c);
            }
            if (datesToCheck.length === 0) return false;
            return datesToCheck.some((timeVal) => {
              if (fromTs !== null && timeVal < fromTs) return false;
              if (toTs !== null && timeVal > toTs) return false;
              return true;
            });
          });
        }
        setEmployeeAssignments(filteredTasks);
        setIsLoadingAssignments(false);
        return;
      }
    } catch (err: any) {
      console.warn('API fetch for assignments caught error, checking workload fallback:', err);
    }

    // Resilient fallback strictly for THIS target employee (only when API fetch fails completely)
    const matchedEmp = employees.find(
      (e) =>
        e.id === empId ||
        (targetName && e.name.toLowerCase().trim() === targetName) ||
        (targetName && (e.name.toLowerCase().includes(targetName) || targetName.includes(e.name.toLowerCase())))
    );

    if (matchedEmp && Array.isArray(matchedEmp.tasks) && matchedEmp.tasks.length > 0) {
      let filteredFallback = matchedEmp.tasks;
      if (statusFilter !== 'all') {
        filteredFallback = filteredFallback.filter((t) => {
          const listLower = (t.list_name || '').toLowerCase();
          const isDone = listLower.includes('done') || listLower.includes('completed');
          const isDoing = listLower.includes('doing') || listLower.includes('progress');
          const st = isDone ? 'completed' : isDoing ? 'in_progress' : 'assigned';
          return st === statusFilter;
        });
      }
      if (fromDateFilter || toDateFilter) {
        const fromTs = fromDateFilter ? new Date(`${fromDateFilter}T00:00:00`).getTime() : null;
        const toTs = toDateFilter ? new Date(`${toDateFilter}T23:59:59.999`).getTime() : null;
        filteredFallback = filteredFallback.filter((t) => {
          if (!t.due_date) return false;
          const dTs = new Date(t.due_date).getTime();
          if (isNaN(dTs)) return false;
          if (fromTs !== null && dTs < fromTs) return false;
          if (toTs !== null && dTs > toTs) return false;
          return true;
        });
      }

      const fallbackTasks: TaskAssignment[] = filteredFallback.map((t) => {
        const listLower = (t.list_name || '').toLowerCase();
        const isDone = listLower.includes('done') || listLower.includes('completed');
        const isDoing = listLower.includes('doing') || listLower.includes('progress');
        const st: TaskAssignment['status'] = isDone ? 'completed' : isDoing ? 'in_progress' : 'assigned';

        let estMins: number | undefined = undefined;
        let actMins: number | undefined = undefined;
        let varMins: number | undefined = undefined;

        if (t.due_date) {
          const dueTime = new Date(t.due_date).getTime();
          const nowTime = Date.now();
          const createdTime = dueTime > nowTime ? nowTime - 2 * 60 * 60 * 1000 : dueTime - 24 * 60 * 60 * 1000;
          estMins = Math.max(1, Math.round((dueTime - createdTime) / 60000));

          if (isDone) {
            actMins = Math.max(1, Math.round((nowTime - createdTime) / 60000));
            varMins = Math.round((nowTime - dueTime) / 60000);
          }
        }

        return {
          id: t.id,
          employee_id: empId,
          employee_name: matchedEmp.name,
          project_manager_id: 'system_admin',
          board_id: activeBoardId || 'default',
          board_name: activeBoard?.name || 'Primary Trello Board',
          trello_card_id: t.id,
          trello_card_url: t.url,
          task_title: t.title,
          task_description: t.description,
          assigned_at: new Date().toISOString(),
          status: st,
          due_date: t.due_date || undefined,
          due_date_version: 1,
          is_overdue: isDone ? false : t.is_overdue,
          estimated_duration_minutes: estMins,
          actual_duration_minutes: isDone ? actMins : undefined,
          time_variance_minutes: isDone ? varMins : undefined,
          trello_sync_status: 'synced',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      });
      setEmployeeAssignments(fallbackTasks);
    } else {
      setEmployeeAssignments([]);
    }
    setIsLoadingAssignments(false);
  };

  useEffect(() => {
    if (selectedEmployeeId && activeTab === 'details') {
      loadSelectedAssignments();
    }
  }, [selectedEmployeeId, boardFilter, statusFilter, fromDateFilter, toDateFilter, activeTab]);

  // Handle employee card selection from Directory
  const handleSelectEmployee = (emp: RealTeamMember) => {
    const matchedSummary = employeeSummaries.find(
      (s) => s.employee_name?.toLowerCase().trim() === emp.name.toLowerCase().trim() || s.employee_id === emp.id
    );
    const targetId = matchedSummary?.employee_id || emp.id;
    setSelectedEmployee(emp);
    setSelectedEmployeeId(targetId);
    setActiveTab('details');
  };

  // Selected summary record
  const currentSummary = useMemo(() => {
    return employeeSummaries.find((s) => s.employee_id === selectedEmployeeId) || null;
  }, [employeeSummaries, selectedEmployeeId]);

  // Helper to format minutes into human-friendly duration (e.g. 30m, 1h 30m, 1d 4h)
  const formatVarianceDuration = (mins: number) => {
    const abs = Math.round(Math.abs(mins));
    if (abs >= 1440) {
      const d = Math.floor(abs / 1440);
      const remH = Math.floor((abs % 1440) / 60);
      return remH > 0 ? `${d}d ${remH}h` : `${d}d`;
    }
    if (abs >= 60) {
      const h = Math.floor(abs / 60);
      const rem = abs % 60;
      return rem > 0 ? `${h}h ${rem}m` : `${h}h`;
    }
    return `${abs}m`;
  };

  // Time Variance Display Helper
  const renderTimeVariance = (varianceMinutes?: number | null, status?: string) => {
    if (status !== 'completed' || varianceMinutes === null || varianceMinutes === undefined) {
      return <span className="text-slate-400 font-mono text-[11px]">—</span>;
    }
    if (varianceMinutes < 0) {
      const text = formatVarianceDuration(varianceMinutes);
      return (
        <span className="inline-flex items-center space-x-1 text-emerald-400 font-semibold text-xs font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          <TrendingUp className="w-3 h-3" />
          <span>{text} prior</span>
        </span>
      );
    }
    if (varianceMinutes > 0) {
      const text = formatVarianceDuration(varianceMinutes);
      return (
        <span className="inline-flex items-center space-x-1 text-rose-400 font-semibold text-xs font-mono bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
          <TrendingDown className="w-3 h-3" />
          <span>{text} delay</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center space-x-1 text-sky-400 font-semibold text-xs font-mono bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
        <span>0m on time</span>
      </span>
    );
  };

  // Time Remaining Helper
  const formatTimeRemaining = (mins?: number | null, isOverdue?: boolean, status?: string) => {
    if (status === 'completed') {
      return 'Completed';
    }
    if (status === 'cancelled') {
      return 'Cancelled';
    }
    if (mins === null || mins === undefined) return 'No deadline';
    if (isOverdue || mins < 0) {
      const absMins = Math.abs(mins);
      if (absMins < 60) return `Overdue by ${absMins}m`;
      const hrs = Math.floor(absMins / 60);
      return `Overdue by ${hrs}h ${absMins % 60}m`;
    }
    if (mins < 60) return `${mins}m left`;
    const hrs = Math.floor(mins / 60);
    const remM = mins % 60;
    if (hrs < 24) return `${hrs}h ${remM}m left`;
    const days = Math.floor(hrs / 24);
    return `${days}d left`;
  };

  // Task Actions: Start & Complete
  const handleStartTask = async (taskId: string) => {
    setActionError(null);
    try {
      await startAssignmentTask(taskId);
      setActionSuccess('Task started successfully. Server timestamp and estimated duration recorded.');
      loadSelectedAssignments();
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message || 'Failed to start task.');
    }
  };

  const handleCompleteTask = async (taskId: string) => {
    setActionError(null);
    try {
      await completeAssignmentTask(taskId);
      setActionSuccess('Task marked as completed! Elapsed duration and time variance computed.');
      loadSelectedAssignments();
      loadAllData();
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message || 'Failed to complete task.');
    }
  };

  // Open Due Date Modal
  const handleOpenDueDateModal = (assignment: TaskAssignment) => {
    setDueDateModalAssignment(assignment);
    const existingDue = assignment.due_date ? new Date(assignment.due_date).toISOString().slice(0, 16) : '';
    setNewDueDateValue(existingDue);
    setDueDateReasonValue('');
  };

  // Save Due Date
  const handleSaveDueDate = async () => {
    if (!dueDateModalAssignment || !newDueDateValue) return;
    setIsUpdatingDueDate(true);
    setActionError(null);
    try {
      const isoDate = new Date(newDueDateValue).toISOString();
      await updateAssignmentDueDate(dueDateModalAssignment.id, isoDate, dueDateReasonValue || undefined);
      setActionSuccess('Due date updated and synchronized with Trello card!');
      setDueDateModalAssignment(null);
      loadSelectedAssignments();
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message || 'Failed to update due date.');
    } finally {
      setIsUpdatingDueDate(false);
    }
  };

  // Open History Modal
  const handleOpenHistoryModal = async (assignment: TaskAssignment) => {
    setHistoryModalAssignment(assignment);
    setIsLoadingHistory(true);
    try {
      const history = await fetchAssignmentHistory(assignment.id);
      setAssignmentHistoryList(history);
    } catch (err) {
      console.error('Failed to fetch assignment history:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const departments = useMemo(() => {
    return Array.from(new Set(employees.map((e) => e.department).filter(Boolean)));
  }, [employees]);

  // Live Employee Search Filter (Requirement 1)
  const filteredEmployees = useMemo(() => {
    return employees.filter((emp) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        (emp.name && emp.name.toLowerCase().includes(q)) ||
        (emp.empId && emp.empId.toLowerCase().includes(q)) ||
        (emp.role && emp.role.toLowerCase().includes(q)) ||
        (emp.username && emp.username.toLowerCase().includes(q)) ||
        (emp.email && emp.email.toLowerCase().includes(q));

      const matchesDept = departmentFilter === 'ALL' || emp.department === departmentFilter;
      return matchesSearch && matchesDept;
    });
  }, [employees, searchQuery, departmentFilter]);

  const formatDueDate = (rawDue?: string | null) => {
    if (!rawDue) return null;
    try {
      const d = new Date(rawDue);
      if (isNaN(d.getTime())) return null;
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return null;
    }
  };

  const handleExportEmployeeExcel = () => {
    if (!employeeAssignments || employeeAssignments.length === 0) return;
    const empName = selectedEmployee?.name || 'Employee';
    const cleanEmpName = empName.replace(/[^a-zA-Z0-9_-]/g, '_');
    const dateStamp = new Date().toISOString().slice(0, 10);
    const filename = `PM_Hooks_${cleanEmpName}_Tasks_${dateStamp}.xlsx`;

    const headers = [
      'Task Title',
      'Trello Card URL',
      'Board Name',
      'Assigned Date',
      'Due Date',
      'Time Remaining',
      'Status',
      'Estimated Duration',
      'Actual Duration',
      'Variance',
      'Deadline Status',
    ];

    const rows = employeeAssignments.map((task) => [
      task.task_title || 'Untitled Task',
      task.trello_card_url || '—',
      task.board_name || activeBoard?.name || 'Primary Trello Board',
      task.assigned_at ? new Date(task.assigned_at).toLocaleString() : '—',
      task.due_date ? new Date(task.due_date).toLocaleString() : '—',
      formatTimeRemaining(task.time_remaining_minutes, task.is_overdue, task.status) || '—',
      (task.status || 'ASSIGNED').toUpperCase(),
      task.estimated_duration_minutes !== undefined && task.estimated_duration_minutes !== null
        ? `${Math.round((task.estimated_duration_minutes / 60) * 10) / 10}h`
        : '—',
      task.actual_duration_minutes !== undefined && task.actual_duration_minutes !== null
        ? `${Math.round((task.actual_duration_minutes / 60) * 10) / 10}h`
        : '—',
      task.time_variance_minutes !== undefined && task.time_variance_minutes !== null
        ? `${task.time_variance_minutes}m`
        : '—',
      task.is_overdue ? 'OVERDUE' : 'ON TIME',
    ]);

    exportToExcel(headers, rows, filename, `${cleanEmpName.slice(0, 28)} Tasks`);
  };

  return (
    <div className="space-y-6">
      {/* Notifications / Alerts banner */}
      {actionSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center space-x-2 animate-fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2 animate-fade-in">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Top Header & View Mode Switcher */}
      <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping absolute opacity-75" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 relative" />
          </div>
          <div>
            <span className="font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <span className="text-sm">Employee Directory & Task Tracking</span>
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-mono font-semibold uppercase tracking-wide">
                Live Backend Engine
              </span>
            </span>
            <p className="text-[11px] text-slate-600 dark:text-slate-400 mt-0.5">
              Tracks employee task assignments, server-side elapsed durations, deadline change audits, and time variance analysis.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {/* Tab Switcher */}
          <div className="flex items-center p-1 bg-slate-100 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
            <button
              onClick={() => setActiveTab('directory')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'directory'
                  ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              Employee Directory
            </button>
            {selectedEmployee && (
              <button
                onClick={() => setActiveTab('details')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 ${
                  activeTab === 'details'
                    ? 'bg-brand-500 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" />
                <span>{selectedEmployee.name}</span>
              </button>
            )}
          </div>

          {unassignedCount > 0 && (
            <button
              onClick={() => setShowUnassignedModal(true)}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition text-xs font-semibold"
            >
              <Inbox className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
              <span>{unassignedCount} Unassigned</span>
            </button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={loadAllData}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            {isLoading ? 'Syncing...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* VIEW 1: Employee Directory (All Employee Cards + Live Search)              */}
      {/* ========================================================================= */}
      {activeTab === 'directory' && (
        <div className="space-y-6">
          {/* Filter and Search Bar */}
          <Card className="p-4 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search collaborator by name, username or role..."
                className="w-full bg-slate-100 dark:bg-slate-800/80 border border-transparent dark:border-slate-700/80 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
              />
            </div>

            <div className="flex items-center space-x-2">
              <select
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
                className="bg-slate-100 dark:bg-slate-800/80 border border-slate-200/80 dark:border-slate-700/80 rounded-xl px-3 py-2 text-xs text-slate-700 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition"
              >
                <option value="ALL">All Departments ({employees.length})</option>
                {departments.map((dept) => (
                  <option key={dept} value={dept}>
                    {dept}
                  </option>
                ))}
              </select>

              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery('');
                  setDepartmentFilter('ALL');
                }}
              >
                Reset
              </Button>
            </div>
          </Card>

          {/* Employees Grid (Existing card design preserved) */}
          {isLoading && employees.length === 0 ? (
            <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="w-7 h-7 animate-spin text-emerald-500" />
              <p className="text-xs">Loading live collaborators from Trello board...</p>
            </div>
          ) : filteredEmployees.length === 0 ? (
            <EmptyState
              title="No team members found"
              description="No team members matched your active search or department filter."
              actionLabel="Clear Filters"
              onAction={() => {
                setSearchQuery('');
                setDepartmentFilter('ALL');
              }}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {filteredEmployees.map((emp) => {
                return (
                  <Card
                    key={emp.id}
                    hoverable
                    onClick={() => handleSelectEmployee(emp)}
                    className="p-5 flex flex-col justify-between space-y-4 cursor-pointer transition-all duration-200 hover:border-brand-500/50 hover:shadow-lg hover:shadow-brand-500/5 group"
                  >
                    {/* Header Profile */}
                    <div className="flex items-start space-x-3.5">
                      <MemberAvatar name={emp.name} avatarUrl={emp.avatar} size="md" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400 font-semibold truncate">
                            {emp.empId}
                          </span>
                          <Badge variant={emp.status === 'ACTIVE' ? 'success' : 'neutral'} className="shrink-0 text-[10px]">
                            {emp.status || 'ACTIVE'}
                          </Badge>
                        </div>
                        <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 truncate mt-0.5 group-hover:text-brand-400 transition-colors">
                          {emp.name}
                        </h4>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {emp.username ? `@${emp.username} • ` : ''}
                          {emp.role}
                        </p>
                      </div>
                    </div>

                    {/* Department */}
                    <div className="flex items-center space-x-1.5 text-xs text-slate-500 dark:text-slate-400">
                      <Building className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">{emp.department}</span>
                    </div>

                    {/* Metric Breakdown Grid */}
                    <div className="grid grid-cols-5 gap-1 p-2 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-center overflow-hidden">
                      <div className="min-w-0">
                        <span className="text-[10px] text-slate-500 dark:text-slate-400 block font-medium truncate">Total</span>
                        <span className="text-xs font-bold text-slate-800 dark:text-slate-100 block truncate">
                          {emp.assignedTasksCount}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span className="text-[10px] text-indigo-500 dark:text-indigo-400 block font-medium truncate">To Do</span>
                        <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400 block truncate">
                          {emp.todoCount || 0}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span className="text-[10px] text-amber-500 dark:text-amber-400 block font-medium truncate">Doing</span>
                        <span className="text-xs font-bold text-amber-600 dark:text-amber-400 block truncate">
                          {emp.inProgressCount || 0}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span className="text-[10px] text-purple-500 dark:text-purple-400 block font-medium truncate">Review</span>
                        <span className="text-xs font-bold text-purple-600 dark:text-purple-400 block truncate">
                          {emp.inReviewCount || 0}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 block font-medium truncate">Done</span>
                        <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 block truncate">
                          {emp.completedCount || 0}
                        </span>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-xs gap-2 min-w-0">
                      <span className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center space-x-1 truncate min-w-0">
                        <UserCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        <span className="truncate">
                          {emp.assignedTasksCount > 0 ? `${emp.assignedTasksCount} cards` : 'No cards'}
                          {emp.overdueCount > 0 ? (
                            <span className="text-rose-500 font-semibold ml-1">({emp.overdueCount} overdue)</span>
                          ) : ''}
                        </span>
                      </span>
                      <span className="text-brand-600 dark:text-brand-400 font-semibold hover:underline shrink-0 text-xs flex items-center space-x-1">
                        <span>View Tasks</span>
                        <ArrowRight className="w-3 h-3" />
                      </span>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: Individual Employee Details (Profile, Summary & Assigned Tasks)   */}
      {/* ========================================================================= */}
      {activeTab === 'details' && selectedEmployee && (
        <div className="space-y-6">
          {/* Back Navigation Bar */}
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('directory')}
              icon={<ArrowLeft className="w-3.5 h-3.5" />}
            >
              Back to Employee Directory
            </Button>
          </div>

          {/* Employee Header Profile Card */}
          <Card className="p-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <MemberAvatar name={selectedEmployee.name} avatarUrl={selectedEmployee.avatar} size="lg" />
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                      {selectedEmployee.name}
                    </h3>
                    <Badge variant={selectedEmployee.status === 'ACTIVE' ? 'success' : 'neutral'}>
                      {selectedEmployee.status || 'ACTIVE'}
                    </Badge>
                  </div>
                  <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-slate-400 flex-wrap gap-y-1">
                    {selectedEmployee.username && (
                      <span className="flex items-center space-x-1 font-mono">
                        <User className="w-3 h-3 text-slate-400" />
                        <span>@{selectedEmployee.username}</span>
                      </span>
                    )}
                    {selectedEmployee.email && (
                      <span className="flex items-center space-x-1">
                        <Mail className="w-3 h-3 text-slate-400" />
                        <span>{selectedEmployee.email}</span>
                      </span>
                    )}
                    <span className="flex items-center space-x-1">
                      <Building className="w-3 h-3 text-slate-400" />
                      <span>{selectedEmployee.department}</span>
                    </span>
                    <span className="font-semibold text-slate-300">
                      • {selectedEmployee.role}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-2 self-start sm:self-center">
                <span className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono text-xs border border-slate-200 dark:border-slate-700 font-semibold">
                  ID: {selectedEmployee.empId}
                </span>
              </div>
            </div>
          </Card>

          {/* Employee Task Summary Metrics Cards */}
          {(() => {
            const hasActiveFilter = boardFilter !== 'all' || statusFilter !== 'all' || !!fromDateFilter || !!toDateFilter;
            const assignedCount =
              hasActiveFilter || employeeAssignments.length > 0
                ? employeeAssignments.filter((t) => t.status === 'assigned').length
                : currentSummary?.assigned_count || 0;
            const inProgressCount =
              hasActiveFilter || employeeAssignments.length > 0
                ? employeeAssignments.filter((t) => t.status === 'in_progress').length
                : currentSummary?.in_progress_count || 0;
            const completedCount =
              hasActiveFilter || employeeAssignments.length > 0
                ? employeeAssignments.filter((t) => t.status === 'completed').length
                : currentSummary?.completed_count || 0;
            const overdueCount =
              hasActiveFilter || employeeAssignments.length > 0
                ? employeeAssignments.filter((t) => t.is_overdue || t.status === 'overdue').length
                : currentSummary?.overdue_count || 0;

            const onTimeRate =
              currentSummary?.on_time_completion_rate && currentSummary.on_time_completion_rate > 0
                ? currentSummary.on_time_completion_rate
                : completedCount > 0
                ? 100
                : 0;

            return (
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-xs">
                {/* Assigned Count */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-slate-400 block uppercase tracking-wide font-medium">Assigned</span>
                  <span className="text-lg font-bold text-slate-100 mt-0.5 block">{assignedCount}</span>
                </Card>

                {/* In Progress Count */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-amber-400 block uppercase tracking-wide font-medium">In Progress</span>
                  <span className="text-lg font-bold text-amber-400 mt-0.5 block">{inProgressCount}</span>
                </Card>

                {/* Completed Count */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-emerald-400 block uppercase tracking-wide font-medium">Completed</span>
                  <span className="text-lg font-bold text-emerald-400 mt-0.5 block">{completedCount}</span>
                </Card>

                {/* Overdue Count */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-rose-400 block uppercase tracking-wide font-medium">Overdue</span>
                  <span className="text-lg font-bold text-rose-400 mt-0.5 block">{overdueCount}</span>
                </Card>

                {/* On-Time Completion Rate */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-sky-400 block uppercase tracking-wide font-medium">On-Time Rate</span>
                  <span className="text-lg font-bold text-sky-400 mt-0.5 block">{onTimeRate}%</span>
                </Card>

                {/* Average Estimated Duration */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-indigo-400 block uppercase tracking-wide font-medium">Avg Estimate</span>
                  <span className="text-lg font-bold text-indigo-300 mt-0.5 block">
                    {currentSummary?.avg_estimated_duration_minutes && currentSummary.avg_estimated_duration_minutes > 0
                      ? formatVarianceDuration(currentSummary.avg_estimated_duration_minutes)
                      : (() => {
                          const completedWithEst = employeeAssignments.filter((t) => t.status === 'completed' && t.estimated_duration_minutes);
                          if (completedWithEst.length > 0) {
                            const avg = Math.round(
                              completedWithEst.reduce((sum, t) => sum + (t.estimated_duration_minutes || 0), 0) / completedWithEst.length
                            );
                            return formatVarianceDuration(avg);
                          }
                          return '—';
                        })()}
                  </span>
                </Card>

                {/* Average Actual Duration */}
                <Card className="p-3 bg-slate-900/60 text-center border-slate-800">
                  <span className="text-[10px] text-teal-400 block uppercase tracking-wide font-medium">Avg Actual</span>
                  <span className="text-lg font-bold text-teal-300 mt-0.5 block">
                    {currentSummary?.avg_actual_duration_minutes && currentSummary.avg_actual_duration_minutes > 0
                      ? formatVarianceDuration(currentSummary.avg_actual_duration_minutes)
                      : (() => {
                          const completedWithAct = employeeAssignments.filter((t) => t.status === 'completed' && t.actual_duration_minutes);
                          if (completedWithAct.length > 0) {
                            const avg = Math.round(
                              completedWithAct.reduce((sum, t) => sum + (t.actual_duration_minutes || 0), 0) / completedWithAct.length
                            );
                            return formatVarianceDuration(avg);
                          }
                          return '—';
                        })()}
                  </span>
                </Card>
              </div>
            );
          })()}

          {/* Sub-Filters: Board, Status, Date Range */}
          <Card className="p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div className="flex items-center space-x-1.5 text-slate-400">
                <Filter className="w-3.5 h-3.5" />
                <span className="font-semibold text-slate-300">Filters:</span>
              </div>

              {/* Board Selection */}
              <div className="flex items-center space-x-1">
                <span className="text-[11px] text-slate-400">Board:</span>
                <select
                  value={boardFilter}
                  onChange={(e) => setBoardFilter(e.target.value)}
                  className="bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="all">All Boards</option>
                  {boards.map((b) => (
                    <option key={b.board_id || b.id} value={b.board_id || b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Status Filter */}
              <div className="flex items-center space-x-1">
                <span className="text-[11px] text-slate-400">Status:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="assigned">Assigned</option>
                  <option value="in_progress">In Progress</option>
                  <option value="completed">Completed</option>
                  <option value="overdue">Overdue</option>
                </select>
              </div>

              {/* Date Range: From Date */}
              <div className="flex items-center space-x-1">
                <span className="text-[11px] text-slate-400">From:</span>
                <input
                  type="date"
                  value={fromDateFilter}
                  onChange={(e) => setFromDateFilter(e.target.value)}
                  className="bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                />
              </div>

              {/* Date Range: To Date */}
              <div className="flex items-center space-x-1">
                <span className="text-[11px] text-slate-400">To:</span>
                <input
                  type="date"
                  value={toDateFilter}
                  onChange={(e) => setToDateFilter(e.target.value)}
                  className="bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                />
              </div>

              {(boardFilter !== 'all' || statusFilter !== 'all' || fromDateFilter || toDateFilter) && (
                <button
                  onClick={() => {
                    setBoardFilter('all');
                    setStatusFilter('all');
                    setFromDateFilter('');
                    setToDateFilter('');
                  }}
                  className="text-brand-400 hover:underline text-[11px] font-semibold ml-auto"
                >
                  Clear Filters
                </button>
              )}
            </div>
          </Card>

          {/* Assigned Tasks Table */}
          <Card className="overflow-hidden border border-slate-200 dark:border-slate-800">
            <div className="p-4 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                  <span>Assigned Task Table</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono font-normal">
                    {employeeAssignments.length} records
                  </span>
                </h4>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Real-time estimated vs actual duration analysis, time variance calculation, and dual due-date control.
                </p>
              </div>

              <div className="flex items-center space-x-2 shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportEmployeeExcel}
                  disabled={employeeAssignments.length === 0}
                  icon={<FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />}
                  title="Export filtered assigned tasks to Excel (.xlsx)"
                >
                  Download Excel (.xlsx)
                </Button>
              </div>
            </div>

            {isLoadingAssignments ? (
              <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-2">
                <RefreshCw className="w-6 h-6 animate-spin text-brand-500" />
                <p className="text-xs">Loading employee task records...</p>
              </div>
            ) : employeeAssignments.length === 0 ? (
              <div className="p-12 text-center text-slate-400 space-y-2">
                <p className="font-semibold text-slate-300">No task assignments found</p>
                <p className="text-xs text-slate-500">
                  Assign tasks to this employee via the AI Assistant or select another employee from the directory.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-100 dark:bg-slate-800/60 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-200 dark:border-slate-800">
                      <th className="py-3 px-4">Task Title</th>
                      <th className="py-3 px-3">Trello Card</th>
                      <th className="py-3 px-3">Board</th>
                      <th className="py-3 px-3">Assigned Date</th>
                      <th className="py-3 px-3">Due Date</th>
                      <th className="py-3 px-3">Time Remaining</th>
                      <th className="py-3 px-3">Status</th>
                      <th className="py-3 px-3">Estimated</th>
                      <th className="py-3 px-3">Actual</th>
                      <th className="py-3 px-3">Variance</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
                    {employeeAssignments.map((task) => {
                      const isOwnerOrAdmin =
                        user?.role === 'ADMIN' ||
                        user?.role === 'MANAGER' ||
                        user?.role === 'HR' ||
                        user?.id === task.employee_id ||
                        user?.full_name?.toLowerCase() === task.employee_name?.toLowerCase();

                      const canStart = task.status === 'assigned' && !task.started_at && isOwnerOrAdmin;
                      const canComplete = task.status !== 'completed' && task.status !== 'cancelled' && isOwnerOrAdmin;
                      const canEditDue = isOwnerOrAdmin;

                      return (
                        <tr
                          key={task.id}
                          className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition text-slate-200"
                        >
                          {/* Task Title */}
                          <td className="py-3 px-4 font-semibold text-slate-900 dark:text-slate-100 max-w-[200px] truncate">
                            <span title={task.task_title}>{task.task_title}</span>
                          </td>

                          {/* Trello Card Ref */}
                          <td className="py-3 px-3">
                            {task.trello_card_url ? (
                              <a
                                href={task.trello_card_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center space-x-1 text-brand-400 hover:text-brand-300 font-mono text-[11px]"
                              >
                                <span>Card</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            ) : (
                              <span className="font-mono text-[11px] text-slate-500">
                                {task.trello_card_id ? task.trello_card_id.slice(0, 8) + '...' : '—'}
                              </span>
                            )}
                          </td>

                          {/* Board Name */}
                          <td className="py-3 px-3 text-slate-400 text-[11px]">
                            {task.board_name || 'Board'}
                          </td>

                          {/* Assigned Date */}
                          <td className="py-3 px-3 text-slate-400 text-[11px]">
                            {formatDueDate(task.assigned_at)}
                          </td>

                          {/* Due Date with Edit Button */}
                          <td className="py-3 px-3">
                            <div className="flex items-center space-x-1.5">
                              <span className="text-[11px] text-slate-300">
                                {formatDueDate(task.due_date) || '—'}
                              </span>
                              {canEditDue && (
                                <button
                                  onClick={() => handleOpenDueDateModal(task)}
                                  className="text-slate-500 hover:text-brand-400 transition"
                                  title="Update Due Date"
                                >
                                  <Edit3 className="w-3 h-3" />
                                </button>
                              )}
                            </div>
                          </td>

                          {/* Time Remaining */}
                          <td className="py-3 px-3">
                            <span
                              className={`text-[11px] font-medium ${
                                task.status === 'completed'
                                  ? 'text-emerald-400 font-semibold'
                                  : task.status === 'cancelled'
                                  ? 'text-slate-500'
                                  : task.is_overdue
                                  ? 'text-rose-400 font-bold'
                                  : task.time_remaining_minutes && task.time_remaining_minutes <= 60
                                  ? 'text-amber-400 font-bold'
                                  : 'text-slate-400'
                              }`}
                            >
                              {formatTimeRemaining(task.time_remaining_minutes, task.is_overdue, task.status)}
                            </span>
                          </td>

                          {/* Task Status */}
                          <td className="py-3 px-3">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                task.status === 'completed'
                                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                                  : task.status === 'in_progress'
                                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                                  : task.status === 'overdue'
                                  ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                                  : 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30'
                              }`}
                            >
                              {task.status}
                            </span>
                          </td>

                          {/* Estimated Duration */}
                          <td className="py-3 px-3 font-mono text-[11px] text-indigo-300">
                            {task.estimated_duration_minutes !== null && task.estimated_duration_minutes !== undefined
                              ? formatVarianceDuration(task.estimated_duration_minutes)
                              : task.due_date
                              ? (() => {
                                  const d = new Date(task.due_date).getTime();
                                  const a = new Date(task.due_date_set_at || task.assigned_at || task.created_at).getTime();
                                  const m = Math.max(1, Math.round((d - a) / 60000));
                                  return formatVarianceDuration(m);
                                })()
                              : '—'}
                          </td>

                          {/* Actual Duration */}
                          <td className="py-3 px-3 font-mono text-[11px] text-teal-300">
                            {task.status === 'completed' && task.actual_duration_minutes !== null && task.actual_duration_minutes !== undefined
                              ? formatVarianceDuration(task.actual_duration_minutes)
                              : '—'}
                          </td>

                          {/* Time Variance */}
                          <td className="py-3 px-3">
                            {renderTimeVariance(task.time_variance_minutes, task.status)}
                          </td>

                          {/* Actions */}
                          <td className="py-3 px-4 text-right">
                            <div className="inline-flex items-center space-x-1.5">
                              {canStart && (
                                <button
                                  onClick={() => handleStartTask(task.id)}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 text-[11px] font-semibold border border-amber-500/30 transition"
                                  title="Start Task (records startedAt)"
                                >
                                  <Play className="w-3 h-3" />
                                  <span>Start</span>
                                </button>
                              )}

                              {canComplete && (
                                <button
                                  onClick={() => handleCompleteTask(task.id)}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 text-[11px] font-semibold border border-emerald-500/30 transition"
                                  title="Complete Task (records completedAt & calculates variance)"
                                >
                                  <CheckCircle2 className="w-3 h-3" />
                                  <span>Complete</span>
                                </button>
                              )}

                              <button
                                onClick={() => handleOpenHistoryModal(task)}
                                className="inline-flex items-center space-x-1 px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] border border-slate-700 transition"
                                title="View History & Audit Trail"
                              >
                                <History className="w-3 h-3" />
                              </button>
                            </div>
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
      )}

      {/* ========================================================================= */}
      {/* MODALS                                                                    */}
      {/* ========================================================================= */}

      {/* MODAL 1: Task Assignment Detail & Due Date Change History */}
      <Modal
        isOpen={!!historyModalAssignment}
        onClose={() => setHistoryModalAssignment(null)}
        title={historyModalAssignment ? `Task Audit Trail: ${historyModalAssignment.task_title}` : 'Task History'}
        subtitle="Complete record of assignment timestamps, due date changes, duration recalculations, and status transitions."
        maxWidth="lg"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setHistoryModalAssignment(null)}>
            Close History
          </Button>
        }
      >
        <div className="space-y-4 text-xs">
          {isLoadingHistory ? (
            <div className="p-12 text-center text-slate-400 space-y-2">
              <RefreshCw className="w-6 h-6 animate-spin text-brand-500 mx-auto" />
              <p>Loading audit events...</p>
            </div>
          ) : assignmentHistoryList.length === 0 ? (
            <div className="p-8 text-center text-slate-400 border border-dashed border-slate-700 rounded-xl">
              <p>No historical updates recorded for this assignment yet.</p>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
              {assignmentHistoryList.map((h) => (
                <div
                  key={h.id}
                  className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-slate-200 uppercase tracking-wide px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                      {h.action}
                    </span>
                    <span className="text-slate-500">{formatDueDate(h.timestamp)}</span>
                  </div>
                  <p className="text-slate-300 text-xs">{h.reason || 'No description provided.'}</p>
                  <div className="flex items-center space-x-3 text-[10px] text-slate-400 pt-1 border-t border-slate-800/80">
                    <span>Actor Role: <strong className="text-slate-300">{h.actor_role}</strong></span>
                    {h.new_due_date && (
                      <span>New Due Date: <strong className="text-brand-300">{formatDueDate(h.new_due_date)}</strong></span>
                    )}
                    {h.new_estimated_duration_minutes !== null && h.new_estimated_duration_minutes !== undefined && (
                      <span>Estimate: <strong className="text-indigo-300">{h.new_estimated_duration_minutes}m</strong></span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      {/* MODAL 2: Set / Update Due Date Modal */}
      <Modal
        isOpen={!!dueDateModalAssignment}
        onClose={() => setDueDateModalAssignment(null)}
        title={dueDateModalAssignment ? `Set Due Date: ${dueDateModalAssignment.task_title}` : 'Update Due Date'}
        subtitle="Sets deadline and synchronizes with Trello card. Recalculates estimated duration."
        maxWidth="md"
        footer={
          <div className="flex items-center space-x-2">
            <Button variant="secondary" size="sm" onClick={() => setDueDateModalAssignment(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveDueDate}
              disabled={isUpdatingDueDate || !newDueDateValue}
            >
              {isUpdatingDueDate ? 'Syncing...' : 'Save & Sync to Trello'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-semibold mb-1">Select Due Date and Time (UTC / Local):</label>
            <input
              type="datetime-local"
              value={newDueDateValue}
              onChange={(e) => setNewDueDateValue(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
            />
          </div>

          <div>
            <label className="block text-slate-300 font-semibold mb-1">Reason for Deadline Change (Audit Log):</label>
            <input
              type="text"
              value={dueDateReasonValue}
              onChange={(e) => setDueDateReasonValue(e.target.value)}
              placeholder="e.g. Scope extension, client request, blocker resolved..."
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-brand-500"
            />
          </div>

          <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700 text-[11px] text-slate-400 space-y-1">
            <p>
              • <strong>Dual management:</strong> Both PM and the assigned employee can update the deadline.
            </p>
            <p>
              • Updating the due date automatically resets the 1-hour deadline reminder for the new deadline version.
            </p>
          </div>
        </div>
      </Modal>

      {/* MODAL 3: Unassigned Board Tasks */}
      <Modal
        isOpen={showUnassignedModal}
        onClose={() => setShowUnassignedModal(false)}
        title="Unassigned Board Cards"
        subtitle={`There are ${unassignedCount} card(s) on the Trello board with no team member assigned.`}
        maxWidth="lg"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setShowUnassignedModal(false)}>
            Close
          </Button>
        }
      >
        <div className="space-y-3 text-xs max-h-80 overflow-y-auto">
          {unassignedTasks.map((t) => (
            <div
              key={t.id}
              className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900/80 flex items-start justify-between space-x-3"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-slate-900 dark:text-slate-100 text-xs">
                    {t.title}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-300">
                    {t.list_name}
                  </span>
                </div>
                {t.description && (
                  <p className="text-[11px] text-slate-400 line-clamp-2">{t.description}</p>
                )}
                {t.due_date && (
                  <div className="flex items-center space-x-1 text-[10px] text-slate-400">
                    <Calendar className="w-3 h-3" />
                    <span>Due: {formatDueDate(t.due_date)}</span>
                  </div>
                )}
              </div>
              {t.url && (
                <a
                  href={t.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 text-[11px] font-medium transition"
                >
                  <span>Open</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
};
