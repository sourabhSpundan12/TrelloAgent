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
  Clock,
  CheckCircle2,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Modal } from '../components/common/Modal';
import { EmptyState } from '../components/common/EmptyState';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import { fetchTeamWorkload } from '../services/api';
import { Employee } from '../types';

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
  size?: 'md' | 'lg';
}> = ({ name, avatarUrl, size = 'md' }) => {
  const [imgError, setImgError] = useState(false);
  const sizeClasses = size === 'lg' ? 'w-14 h-14 text-base' : 'w-12 h-12 text-sm';
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
  const { isAuthenticated } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();
  const [employees, setEmployees] = useState<RealTeamMember[]>([]);
  const [unassignedTasks, setUnassignedTasks] = useState<UnassignedTask[]>([]);
  const [unassignedCount, setUnassignedCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('ALL');
  const [selectedEmployee, setSelectedEmployee] = useState<RealTeamMember | null>(null);
  const [showUnassignedModal, setShowUnassignedModal] = useState(false);

  const loadTeam = async () => {
    setIsLoading(true);
    try {
      const data = await fetchTeamWorkload(undefined, activeBoardId || undefined);
      if (data && data.status === 'SUCCESS') {
        setEmployees(Array.isArray(data.members) ? data.members : []);
        setUnassignedTasks(Array.isArray(data.unassigned_tasks) ? data.unassigned_tasks : []);
        setUnassignedCount(data.unassigned_count || 0);
      }
    } catch (err) {
      console.error('Failed to fetch live team members:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTeam();
  }, [isAuthenticated, activeBoardId]);

  const departments = useMemo(() => {
    return Array.from(new Set(employees.map((e) => e.department).filter(Boolean)));
  }, [employees]);

  const filteredEmployees = useMemo(() => {
    return employees.filter((emp) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        emp.name.toLowerCase().includes(q) ||
        emp.empId.toLowerCase().includes(q) ||
        emp.role.toLowerCase().includes(q) ||
        (emp.username && emp.username.toLowerCase().includes(q)) ||
        (emp.email && emp.email.toLowerCase().includes(q));

      const matchesDept = departmentFilter === 'ALL' || emp.department === departmentFilter;

      return matchesSearch && matchesDept;
    });
  }, [employees, searchQuery, departmentFilter]);

  const employeeTasks = useMemo(() => {
    if (!selectedEmployee) return [];
    return selectedEmployee.tasks || [];
  }, [selectedEmployee]);

  const formatDueDate = (rawDue?: string | null) => {
    if (!rawDue) return null;
    try {
      const d = new Date(rawDue);
      if (isNaN(d.getTime())) return null;
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Live Synchronization Telemetry Header */}
      <div className="p-4 rounded-2xl bg-gradient-to-r from-emerald-500/10 via-slate-900/50 to-slate-900/80 border border-emerald-500/20 text-xs shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping absolute opacity-75" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 relative" />
          </div>
          <div>
            <span className="font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <span className="text-sm">Team Workload & Collaborators</span>
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-[10px] font-mono text-emerald-400 font-semibold uppercase tracking-wide">
                Live Trello Synced
              </span>
            </span>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Live collaborator distribution computed directly from Trello board cards and registered accounts.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {unassignedCount > 0 && (
            <button
              onClick={() => setShowUnassignedModal(true)}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition text-xs font-medium"
            >
              <Inbox className="w-3.5 h-3.5" />
              <span>{unassignedCount} Unassigned Cards</span>
            </button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={loadTeam}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            {isLoading ? 'Syncing...' : 'Refresh Board'}
          </Button>
        </div>
      </div>

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

      {/* Employees Grid */}
      {isLoading && employees.length === 0 ? (
        <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
          <RefreshCw className="w-7 h-7 animate-spin text-emerald-500" />
          <p className="text-xs">Loading live collaborators from Trello board...</p>
        </div>
      ) : filteredEmployees.length === 0 ? (
        <EmptyState
          title="No team members found"
          description={
            searchQuery || departmentFilter !== 'ALL'
              ? 'No team members matched your active search or department filter.'
              : 'No team members connected to the board yet.'
          }
          actionLabel="Clear Filters"
          onAction={() => {
            setSearchQuery('');
            setDepartmentFilter('ALL');
          }}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredEmployees.map((emp) => (
            <Card
              key={emp.id}
              hoverable
              onClick={() => setSelectedEmployee(emp)}
              className="p-5 flex flex-col justify-between space-y-4 cursor-pointer transition-all duration-200 hover:border-brand-500/50 hover:shadow-lg hover:shadow-brand-500/5"
            >
              {/* Header Profile - Single Clean Avatar */}
              <div className="flex items-start space-x-3.5">
                <MemberAvatar name={emp.name} avatarUrl={emp.avatar} size="md" />

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-slate-400 font-semibold">{emp.empId}</span>
                    <Badge variant={emp.status === 'ACTIVE' ? 'success' : 'neutral'}>
                      {emp.status}
                    </Badge>
                  </div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 truncate mt-0.5">
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

              {/* Metric Breakdown Grid - Accurately Dissects To Do vs Doing vs Review vs Done */}
              <div className="grid grid-cols-5 gap-1.5 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-center">
                <div>
                  <span className="text-[10px] text-slate-400 block font-medium">Total</span>
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-100">
                    {emp.assignedTasksCount}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-indigo-400 block font-medium">To Do</span>
                  <span className="text-xs font-bold text-indigo-500 dark:text-indigo-400">
                    {emp.todoCount || 0}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-amber-400 block font-medium">Doing</span>
                  <span className="text-xs font-bold text-amber-500 dark:text-amber-400">
                    {emp.inProgressCount || 0}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-purple-400 block font-medium">Review</span>
                  <span className="text-xs font-bold text-purple-500 dark:text-purple-400">
                    {emp.inReviewCount || 0}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-emerald-400 block font-medium">Done</span>
                  <span className="text-xs font-bold text-emerald-500 dark:text-emerald-400">
                    {emp.completedCount || 0}
                  </span>
                </div>
              </div>

              {/* Card Footer Action */}
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-xs">
                <span className="text-[11px] text-slate-400 flex items-center space-x-1">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-500" />
                  <span>
                    {emp.assignedTasksCount > 0
                      ? `${emp.assignedTasksCount} Trello card${emp.assignedTasksCount > 1 ? 's' : ''}`
                      : 'No active cards'}
                    {emp.overdueCount > 0 ? (
                      <span className="text-rose-400 font-bold ml-1">({emp.overdueCount} overdue)</span>
                    ) : ''}
                  </span>
                </span>
                <span className="text-brand-500 dark:text-brand-400 font-medium group-hover:underline">
                  View Tasks ({emp.tasks?.length || emp.assignedTasksCount}) →
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Selected Employee Details Modal */}
      <Modal
        isOpen={!!selectedEmployee}
        onClose={() => setSelectedEmployee(null)}
        title={selectedEmployee ? selectedEmployee.name : 'Collaborator Profile'}
        subtitle={selectedEmployee ? `${selectedEmployee.empId} • ${selectedEmployee.role}` : ''}
        maxWidth="lg"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setSelectedEmployee(null)}>
            Close Profile
          </Button>
        }
      >
        {selectedEmployee && (
          <div className="space-y-5 text-xs">
            {/* Top Employee Bio */}
            <div className="flex items-center space-x-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800">
              <MemberAvatar name={selectedEmployee.name} avatarUrl={selectedEmployee.avatar} size="lg" />
              <div className="space-y-1 min-w-0 flex-1">
                <h4 className="text-base font-bold text-slate-900 dark:text-slate-100 truncate">
                  {selectedEmployee.name}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{selectedEmployee.email}</p>
                <div className="flex items-center space-x-2 pt-1 flex-wrap gap-y-1">
                  <Badge variant="purple">{selectedEmployee.department}</Badge>
                  <Badge variant="success">Trello Collaborator</Badge>
                </div>
              </div>
            </div>

            {/* Live Trello Workload Breakdown */}
            <div className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/80 rounded-xl space-y-2 text-xs">
              <span className="font-semibold text-slate-900 dark:text-slate-100 flex items-center space-x-1.5">
                <Layers className="w-3.5 h-3.5 text-brand-500" />
                <span>Board Workload Summary</span>
              </span>
              <div className="flex items-center space-x-4 text-[11px] text-slate-400 flex-wrap gap-y-1">
                <span>
                  Total:{' '}
                  <strong className="text-slate-200">{selectedEmployee.assignedTasksCount}</strong>
                </span>
                <span>
                  To Do:{' '}
                  <strong className="text-indigo-400">{selectedEmployee.todoCount || 0}</strong>
                </span>
                <span>
                  Doing:{' '}
                  <strong className="text-amber-400">{selectedEmployee.inProgressCount || 0}</strong>
                </span>
                <span>
                  Review/Testing:{' '}
                  <strong className="text-purple-400">{selectedEmployee.inReviewCount || 0}</strong>
                </span>
                <span>
                  Done:{' '}
                  <strong className="text-emerald-400">{selectedEmployee.completedCount || 0}</strong>
                </span>
                {selectedEmployee.overdueCount > 0 && (
                  <span>
                    Overdue:{' '}
                    <strong className="text-rose-400">{selectedEmployee.overdueCount}</strong>
                  </span>
                )}
              </div>
            </div>

            {/* Assigned Tasks Breakdown List */}
            <div className="space-y-2">
              <h5 className="font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider text-[11px] flex items-center justify-between">
                <span>Assigned Trello Cards ({employeeTasks.length})</span>
                <span className="text-[10px] text-slate-400 font-normal">Directly Synced via MCP</span>
              </h5>

              {employeeTasks.length === 0 ? (
                <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-slate-800/20 border border-dashed border-slate-200 dark:border-slate-700/60 text-slate-400 space-y-1">
                  <p className="font-medium text-xs text-slate-300">No cards currently assigned</p>
                  <p className="text-[11px]">
                    You can assign cards to this member naturally in the AI Assistant (e.g., &quot;assign JWT authentication to {selectedEmployee.name}&quot;).
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                  {employeeTasks.map((t) => (
                    <div
                      key={t.id}
                      className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900/80 flex items-start justify-between space-x-3 hover:border-brand-500/40 transition"
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
                          <p className="text-[11px] text-slate-400 line-clamp-2">
                            {t.description}
                          </p>
                        )}

                        {t.due_date && (
                          <div className="flex items-center space-x-1.5 text-[10px] text-slate-400 pt-0.5">
                            <Calendar className="w-3 h-3 text-slate-400" />
                            <span>Due: {formatDueDate(t.due_date)}</span>
                            {t.is_overdue && (
                              <span className="text-rose-500 font-bold ml-1">Overdue</span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center space-x-2 shrink-0">
                        {t.url && (
                          <a
                            href={t.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 text-[11px] font-medium transition"
                            title="Open Card in Trello"
                          >
                            <span>Open</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* Unassigned Tasks Modal */}
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
