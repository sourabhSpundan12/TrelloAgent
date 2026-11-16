import React, { useState } from 'react';
import {
  Search,
  Bell,
  Sun,
  Moon,
  ChevronDown,
  User,
  Shield,
  LogOut,
  Command,
  CheckCircle,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../common/Button';

interface TopNavbarProps {
  currentTab: string;
  onSearchClick?: () => void;
}

export const TopNavbar: React.FC<TopNavbarProps> = ({ currentTab }) => {
  const { theme, toggleTheme } = useTheme();
  const { user, isAuthenticated, logout, openLoginModal } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const tabLabels: Record<string, { title: string; category: string }> = {
    overview: { title: 'Overview Dashboard', category: 'Analytics & Summary' },
    'ai-assistant': { title: 'AI Agent Assistant', category: 'Conversational Orchestration' },
    tasks: { title: 'Task Management', category: 'Trello Board Tasks' },
    employees: { title: 'Employee Directory', category: 'Workload & Team' },
    reports: { title: 'Performance Reports', category: 'Metrics & Rollups' },
    activity: { title: 'Activity History', category: 'Audit Trail & Events' },
    tools: { title: 'Dynamic Tool Management', category: 'Registry & Discovery' },
    settings: { title: 'Platform Settings', category: 'Configuration & Providers' },
  };

  const currentMeta = tabLabels[currentTab] || { title: currentTab, category: 'App' };

  return (
    <header className="h-16 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800/80 px-6 flex items-center justify-between sticky top-0 z-30 transition-colors">
      {/* Breadcrumb & Title */}
      <div className="flex flex-col">
        <div className="flex items-center space-x-1.5 text-[11px] text-slate-400 dark:text-slate-500 font-medium">
          <span>Platform</span>
          <span>/</span>
          <span>{currentMeta.category}</span>
        </div>
        <h2 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          {currentMeta.title}
        </h2>
      </div>

      {/* Center Global Search UI */}
      <div className="hidden md:flex items-center flex-1 max-w-md mx-8">
        <div className="relative w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search tasks, tools, employees or commands..."
            className="w-full bg-slate-100 dark:bg-slate-800/70 border border-transparent dark:border-slate-700/60 rounded-xl pl-9 pr-12 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500/50 focus:bg-white dark:focus:bg-slate-800 transition"
          />
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center space-x-0.5 text-[10px] text-slate-400 bg-white dark:bg-slate-700 px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-600">
            <Command className="w-2.5 h-2.5" />
            <span>K</span>
          </div>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-2.5">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 transition"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-600" />}
        </button>

        {/* Notifications Icon & Popover */}
        <div className="relative">
          <button
            onClick={() => {
              setNotificationsOpen(!notificationsOpen);
              setProfileOpen(false);
            }}
            className="relative p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 transition"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-brand-500 ring-2 ring-white dark:ring-slate-900"></span>
          </button>

          {notificationsOpen && (
            <div className="absolute right-0 mt-2 w-80 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl p-4 z-40 animate-in fade-in zoom-in-95 duration-100">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">Notifications</span>
                <span className="text-[10px] text-brand-600 dark:text-brand-400 font-medium">3 unread</span>
              </div>
              <div className="divide-y divide-slate-100 dark:divide-slate-800/60 mt-2 space-y-1">
                <div className="py-2.5 text-xs">
                  <p className="font-medium text-slate-800 dark:text-slate-200">Pending Approval Required</p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    "Login API" card creation preview is waiting for your confirmation.
                  </p>
                  <span className="text-[10px] text-slate-400 mt-1 block">5m ago</span>
                </div>
                <div className="py-2.5 text-xs">
                  <p className="font-medium text-slate-800 dark:text-slate-200">Task Completed</p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    Elena completed "Employee Workload Calculation Engine".
                  </p>
                  <span className="text-[10px] text-slate-400 mt-1 block">2h ago</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* User Profile / Auth Action */}
        {isAuthenticated && user ? (
          <div className="relative">
            <button
              onClick={() => {
                setProfileOpen(!profileOpen);
                setNotificationsOpen(false);
              }}
              className="flex items-center space-x-2.5 p-1 pl-2 pr-2.5 rounded-xl border border-slate-200/60 dark:border-slate-700/60 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
            >
              <div className="w-7 h-7 rounded-lg bg-brand-600 text-white font-semibold text-xs flex items-center justify-center">
                {user.full_name ? user.full_name[0].toUpperCase() : 'U'}
              </div>
              <div className="text-left hidden sm:block">
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-tight">
                  {user.full_name}
                </p>
                <p className="text-[10px] text-slate-400 leading-tight">
                  {user.role}
                </p>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {profileOpen && (
              <div className="absolute right-0 mt-2 w-60 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl p-2 z-40 animate-in fade-in zoom-in-95 duration-100">
                <div className="p-3 border-b border-slate-100 dark:border-slate-800">
                  <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{user.full_name}</p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">{user.email}</p>
                  <span className="mt-1.5 inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-400 border border-brand-200 dark:border-brand-500/20">
                    <Shield className="w-2.5 h-2.5" />
                    <span>{user.role} Role</span>
                  </span>
                </div>

                <div className="py-1">
                  <div className="px-3 py-2 text-xs text-slate-500">
                    Department: <span className="font-medium text-slate-700 dark:text-slate-300">{user.department || 'Engineering'}</span>
                  </div>
                </div>

                <div className="pt-1 border-t border-slate-100 dark:border-slate-800">
                  <button
                    onClick={() => {
                      setProfileOpen(false);
                      logout();
                    }}
                    className="w-full flex items-center space-x-2 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-lg transition"
                  >
                    <LogOut className="w-4 h-4" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={openLoginModal}
            icon={<User className="w-3.5 h-3.5" />}
          >
            Sign In
          </Button>
        )}
      </div>
    </header>
  );
};

