import React, { useState, useEffect } from 'react';
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
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  ExternalLink,
  CheckCheck,
  Inbox,
  Loader2,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../common/Button';
import { NotificationItem } from '../../types';
import { fetchNotifications, markNotificationsRead } from '../../services/api';

interface TopNavbarProps {
  currentTab: string;
  onTabChange?: (tabId: string) => void;
  onSearchClick?: () => void;
}

export const TopNavbar: React.FC<TopNavbarProps> = ({ currentTab, onTabChange }) => {
  const { theme, toggleTheme } = useTheme();
  const { user, isAuthenticated, logout, openLoginModal } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [isLoadingNotifications, setIsLoadingNotifications] = useState<boolean>(false);

  const parseAsUtcDate = (dateVal?: string | Date): Date | null => {
    if (!dateVal) return null;
    if (dateVal instanceof Date) return isNaN(dateVal.getTime()) ? null : dateVal;
    let str = String(dateVal).trim();
    if (!str) return null;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(str) && !str.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(str)) {
      str += 'Z';
    }
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  };

  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const d = parseAsUtcDate(dateStr);
      if (!d) return '';
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      if (diffMs < 0) return 'Just now';
      const diffSecs = Math.floor(diffMs / 1000);
      if (diffSecs < 60) return 'Just now';
      const diffMins = Math.floor(diffSecs / 60);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays === 1) return 'Yesterday';
      if (diffDays < 7) return `${diffDays}d ago`;
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  const loadNotifications = async () => {
    if (!isAuthenticated) return;
    try {
      setIsLoadingNotifications(true);
      const res = await fetchNotifications(20);
      if (res && res.notifications) {
        setNotifications(res.notifications);
        setUnreadCount(res.unread_count ?? 0);
      }
    } catch (err) {
      console.error('Failed to load notifications:', err);
    } finally {
      setIsLoadingNotifications(false);
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 20000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  useEffect(() => {
    if (notificationsOpen) {
      loadNotifications();
    }
  }, [notificationsOpen]);

  const handleMarkAllRead = async () => {
    try {
      await markNotificationsRead(undefined, true);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error('Failed to mark all as read:', err);
    }
  };

  const handleNotificationClick = async (notif: NotificationItem) => {
    if (!notif.is_read) {
      try {
        await markNotificationsRead(notif.id, false);
        setNotifications((prev) =>
          prev.map((n) => (n.id === notif.id ? { ...n, is_read: true } : n))
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch (err) {
        console.error('Failed to mark notification as read:', err);
      }
    }

    if (notif.target_tab && onTabChange) {
      onTabChange(notif.target_tab);
      setNotificationsOpen(false);
    }
  };

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
        <h2 className="text-sm font-bold text-slate-900 dark:white tracking-tight">
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
            title="Notifications"
            className="relative p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 transition"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-white dark:ring-slate-900 shadow-sm animate-pulse">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {notificationsOpen && (
            <div className="absolute right-0 mt-2 w-88 max-w-[90vw] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl p-4 z-40 animate-in fade-in zoom-in-95 duration-100">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">Notifications</span>
                  {unreadCount > 0 ? (
                    <span className="text-[10px] bg-brand-500/10 text-brand-600 dark:text-brand-400 font-semibold px-2 py-0.5 rounded-full">
                      {unreadCount} unread
                    </span>
                  ) : (
                    <span className="text-[10px] text-slate-400 font-normal">All caught up</span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllRead}
                    className="text-[11px] text-brand-600 dark:text-brand-400 hover:underline flex items-center space-x-1"
                  >
                    <CheckCheck className="w-3 h-3" />
                    <span>Mark all read</span>
                  </button>
                )}
              </div>

              <div className="divide-y divide-slate-100 dark:divide-slate-800/60 mt-2 max-h-80 overflow-y-auto pr-1 space-y-1">
                {isLoadingNotifications && notifications.length === 0 ? (
                  <div className="py-8 flex flex-col items-center justify-center text-slate-400 text-xs space-y-2">
                    <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
                    <span>Loading real notifications...</span>
                  </div>
                ) : notifications.length === 0 ? (
                  <div className="py-8 flex flex-col items-center justify-center text-slate-400 text-xs space-y-2">
                    <Inbox className="w-6 h-6 text-slate-300 dark:text-slate-600" />
                    <span>No notifications yet</span>
                  </div>
                ) : (
                  notifications.map((notif) => {
                    const isPending = notif.type === 'APPROVAL_REQUIRED';
                    const isExecuted = notif.type === 'ACTION_EXECUTED';
                    const isFailed = notif.type === 'ACTION_FAILED';
                    const isCancelled = notif.type === 'ACTION_CANCELLED';

                    return (
                      <div
                        key={notif.id}
                        onClick={() => handleNotificationClick(notif)}
                        className={`py-2.5 px-2 rounded-xl transition cursor-pointer flex items-start space-x-2.5 ${
                          notif.is_read
                            ? 'hover:bg-slate-50 dark:hover:bg-slate-800/50 opacity-80'
                            : 'bg-brand-50/40 dark:bg-brand-500/10 hover:bg-brand-50/70 dark:hover:bg-brand-500/15'
                        }`}
                      >
                        <div className="mt-0.5 shrink-0">
                          {isPending ? (
                            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                              <Clock className="w-3.5 h-3.5" />
                            </div>
                          ) : isExecuted ? (
                            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            </div>
                          ) : isFailed ? (
                            <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400">
                              <AlertCircle className="w-3.5 h-3.5" />
                            </div>
                          ) : isCancelled ? (
                            <div className="p-1.5 rounded-lg bg-slate-500/10 text-slate-500 dark:text-slate-400">
                              <XCircle className="w-3.5 h-3.5" />
                            </div>
                          ) : (
                            <div className="p-1.5 rounded-lg bg-brand-500/10 text-brand-600 dark:text-brand-400">
                              <Bell className="w-3.5 h-3.5" />
                            </div>
                          )}
                        </div>

                        <div className="flex-1 min-w-0 text-xs">
                          <div className="flex items-center justify-between">
                            <p
                              className={`truncate ${
                                notif.is_read
                                  ? 'text-slate-700 dark:text-slate-300 font-medium'
                                  : 'text-slate-900 dark:text-white font-semibold'
                              }`}
                            >
                              {notif.title}
                            </p>
                            {!notif.is_read && (
                              <span className="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0 ml-1.5"></span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2 leading-relaxed">
                            {notif.message}
                          </p>
                          <div className="flex items-center justify-between mt-1 text-[10px] text-slate-400">
                            <span>{formatTimeAgo(notif.created_at)}</span>
                            {notif.card_url && (
                              <a
                                href={notif.card_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center space-x-1 text-brand-600 dark:text-brand-400 hover:underline"
                              >
                                <span>Trello</span>
                                <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
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

