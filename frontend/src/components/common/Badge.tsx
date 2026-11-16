import React from 'react';
import { TaskStatus, TaskPriority, ToolCategory } from '../../types';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'neutral';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'sm',
  className = '',
}) => {
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-medium';

  const variantMap: Record<string, string> = {
    default: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700',
    success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20',
    warning: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20',
    danger: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400 border-rose-200 dark:border-rose-500/20',
    info: 'bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400 border-sky-200 dark:border-sky-500/20',
    purple: 'bg-purple-50 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400 border-purple-200 dark:border-purple-500/20',
    neutral: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${sizeClasses} ${variantMap[variant] || variantMap.default} ${className}`}
    >
      {children}
    </span>
  );
};

export const StatusBadge: React.FC<{ status: TaskStatus }> = ({ status }) => {
  switch (status) {
    case 'TODO':
      return <Badge variant="neutral">To Do</Badge>;
    case 'IN_PROGRESS':
      return <Badge variant="info">In Progress</Badge>;
    case 'IN_REVIEW':
      return <Badge variant="warning">In Review</Badge>;
    case 'DONE':
      return <Badge variant="success">Completed</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
};

export const PriorityBadge: React.FC<{ priority: TaskPriority }> = ({ priority }) => {
  switch (priority) {
    case 'LOW':
      return <Badge variant="neutral">Low</Badge>;
    case 'MEDIUM':
      return <Badge variant="info">Medium</Badge>;
    case 'HIGH':
      return <Badge variant="warning">High</Badge>;
    case 'URGENT':
      return <Badge variant="danger">Urgent</Badge>;
    default:
      return <Badge>{priority}</Badge>;
  }
};

export const CategoryBadge: React.FC<{ category: ToolCategory | string }> = ({ category }) => {
  const cat = String(category).toUpperCase();
  switch (cat) {
    case 'TRELLO':
      return <Badge variant="info">Trello</Badge>;
    case 'REPORTING':
      return <Badge variant="purple">Reporting</Badge>;
    case 'EMPLOYEE':
      return <Badge variant="success">Employee</Badge>;
    case 'ANALYTICS':
      return <Badge variant="warning">Analytics</Badge>;
    case 'SYSTEM':
      return <Badge variant="neutral">System</Badge>;
    default:
      return <Badge>{category}</Badge>;
  }
};

