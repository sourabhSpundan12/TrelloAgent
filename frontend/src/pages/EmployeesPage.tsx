import React, { useState, useMemo } from 'react';
import {
  Search,
  Building,
  UserCheck,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Modal } from '../components/common/Modal';
import { DemoBanner } from '../components/common/DemoBanner';
import { EmptyState } from '../components/common/EmptyState';
import { MOCK_EMPLOYEES } from '../mock/mockEmployees';
import { MOCK_TASKS } from '../mock/mockTasks';
import { Employee } from '../types';

export const EmployeesPage: React.FC = () => {
  const [employees] = useState<Employee[]>(MOCK_EMPLOYEES);
  const [searchQuery, setSearchQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('ALL');
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);

  const departments = useMemo(() => {
    return Array.from(new Set(employees.map((e) => e.department)));
  }, [employees]);

  const filteredEmployees = useMemo(() => {
    return employees.filter((emp) => {
      const matchesSearch =
        emp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        emp.empId.toLowerCase().includes(searchQuery.toLowerCase()) ||
        emp.role.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesDept = departmentFilter === 'ALL' || emp.department === departmentFilter;

      return matchesSearch && matchesDept;
    });
  }, [employees, searchQuery, departmentFilter]);

  // Tasks belonging to selected employee
  const employeeTasks = useMemo(() => {
    if (!selectedEmployee) return [];
    return MOCK_TASKS.filter((t) => t.assignee.id === selectedEmployee.id);
  }, [selectedEmployee]);

  return (
    <div className="space-y-6">
      <DemoBanner
        mode="demo"
        message="Placeholder / Demonstration Directory: This is a static conceptual view. The primary workflow of Agentic Task Manager is conversational through the AI Assistant. Real tasks are synced live with Trello."
      />

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name, ID (e.g. EMP-101) or role..."
            className="w-full bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
          />
        </div>

        <div className="flex items-center space-x-2">
          <select
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value)}
            className="bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-700 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition"
          >
            <option value="ALL">All Departments</option>
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

      {/* Employees Grid / Table */}
      {filteredEmployees.length === 0 ? (
        <EmptyState
          title="No employees found"
          description="No team members matched your search query."
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
              className="p-5 flex flex-col justify-between space-y-4"
            >
              {/* Header Profile */}
              <div className="flex items-start space-x-3.5">
                <img
                  src={emp.avatar}
                  alt={emp.name}
                  className="w-12 h-12 rounded-2xl object-cover ring-2 ring-slate-200 dark:ring-slate-700"
                />
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
                  <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{emp.role}</p>
                </div>
              </div>

              {/* Department */}
              <div className="flex items-center space-x-1.5 text-xs text-slate-500 dark:text-slate-400">
                <Building className="w-3.5 h-3.5 text-slate-400" />
                <span>{emp.department}</span>
              </div>

              {/* Metric Breakdown Grid */}
              <div className="grid grid-cols-5 gap-1.5 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-center">
                <div>
                  <span className="text-[10px] text-slate-400 block">Assigned</span>
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                    {emp.assignedTasksCount}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-sky-500 block">Active</span>
                  <span className="text-xs font-bold text-sky-600 dark:text-sky-400">
                    {emp.inProgressCount}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-amber-500 block">Review</span>
                  <span className="text-xs font-bold text-amber-600 dark:text-amber-400">
                    {emp.inReviewCount}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-emerald-500 block">Done</span>
                  <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                    {emp.completedCount}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-rose-500 block">Overdue</span>
                  <span
                    className={`text-xs font-bold ${
                      emp.overdueCount > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-400'
                    }`}
                  >
                    {emp.overdueCount}
                  </span>
                </div>
              </div>

              {/* Card Footer Action */}
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-xs">
                <span className="text-[11px] text-slate-400 flex items-center space-x-1">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Workload: Optimal</span>
                </span>
                <span className="text-brand-600 dark:text-brand-400 font-medium">View Workload →</span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Employee Details Modal */}
      <Modal
        isOpen={!!selectedEmployee}
        onClose={() => setSelectedEmployee(null)}
        title={selectedEmployee ? selectedEmployee.name : 'Employee Profile'}
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
              <img
                src={selectedEmployee.avatar}
                alt={selectedEmployee.name}
                className="w-14 h-14 rounded-2xl object-cover ring-2 ring-slate-200 dark:ring-slate-700"
              />
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  {selectedEmployee.name}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400">{selectedEmployee.email}</p>
                <div className="flex items-center space-x-2 pt-1">
                  <Badge variant="purple">{selectedEmployee.department}</Badge>
                  <Badge variant="success">Active Status</Badge>
                </div>
              </div>
            </div>

            {/* Strict Requirement Note Banner */}
            <div className="p-3 bg-sky-500/10 border border-sky-500/20 text-sky-800 dark:text-sky-300 rounded-xl text-xs space-y-1">
              <span className="font-semibold block">Task Activity Distinction:</span>
              <p className="text-[11px]">
                {selectedEmployee.name} is currently assigned {selectedEmployee.assignedTasksCount} tasks in total, with{' '}
                <span className="font-bold underline">{selectedEmployee.inProgressCount} task actively in progress</span>.
                Task activity records reflect board transitions and do not imply physical attendance.
              </p>
            </div>

            {/* Assigned Tasks Breakdown List */}
            <div className="space-y-2">
              <h5 className="font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider text-[11px]">
                Assigned Board Cards ({employeeTasks.length})
              </h5>

              {employeeTasks.length === 0 ? (
                <p className="text-slate-400 italic py-2">No active sprint tasks currently assigned.</p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {employeeTasks.map((t) => (
                    <div
                      key={t.id}
                      className="p-3 rounded-lg border border-slate-100 dark:border-slate-800 flex items-center justify-between"
                    >
                      <div>
                        <span className="font-mono text-[10px] text-slate-400 mr-2">{t.id}</span>
                        <span className="font-medium text-slate-800 dark:text-slate-200">{t.title}</span>
                      </div>
                      <Badge variant={t.status === 'IN_PROGRESS' ? 'info' : t.status === 'DONE' ? 'success' : 'neutral'}>
                        {t.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
