import React, { useState, useEffect } from 'react';
import {
  User,
  Sliders,
  Sun,
  Moon,
  Layers,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle2,
  KeyRound,
  ShieldCheck,
  Loader2,
  X,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { changePassword } from '../services/api';

export const SettingsPage: React.FC = () => {
  const { theme, setTheme } = useTheme();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'profile' | 'security' | 'preferences' | 'theme' | 'integrations'>('profile');

  // Preference toggles
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [autoRefreshReports, setAutoRefreshReports] = useState(true);
  const [strictPrivacyMode, setStrictPrivacyMode] = useState(true);

  // Change Password state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState<string | null>(null);
  const [toastError, setToastError] = useState<string | null>(null);
  const [toastSuccess, setToastSuccess] = useState<string | null>(null);

  // Auto-dismiss floating error and success toasts after 5 seconds
  useEffect(() => {
    if (!toastError) return;
    const timer = setTimeout(() => {
      setToastError(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toastError]);

  useEffect(() => {
    if (!toastSuccess) return;
    const timer = setTimeout(() => {
      setToastSuccess(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toastSuccess]);

  const handleChangePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setChangeError(null);
    setChangeSuccess(null);
    setToastError(null);
    setToastSuccess(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      const msg = 'Please fill in all password fields.';
      setChangeError(msg);
      setToastError(msg);
      return;
    }

    if (newPassword.length < 8) {
      const msg = 'New password must be at least 8 characters long.';
      setChangeError(msg);
      setToastError(msg);
      return;
    }

    if (newPassword !== confirmPassword) {
      const msg = 'New password and confirm password do not match.';
      setChangeError(msg);
      setToastError(msg);
      return;
    }

    if (currentPassword === newPassword) {
      const msg = 'New password cannot be the same as your current password.';
      setChangeError(msg);
      setToastError(msg);
      return;
    }

    setIsChangingPassword(true);
    try {
      const res = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      const successMsg = res.message || 'Password updated successfully!';
      setChangeSuccess(successMsg);
      setToastSuccess(successMsg);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      const msg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        err.message ||
        'Current password is incorrect.';
      setChangeError(msg);
      setToastError(msg);
    } finally {
      setIsChangingPassword(false);
    }
  };

  return (
    <div className="space-y-6 relative">
      {/* Floating Error Toast Notification Popup */}
      {toastError && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 flex items-center space-x-3 px-4 py-3 bg-rose-600 text-white rounded-2xl shadow-2xl border border-rose-500 animate-in fade-in slide-in-from-top-4 duration-200 max-w-sm sm:max-w-md">
          <AlertCircle className="w-5 h-5 shrink-0 text-white" />
          <p className="text-xs sm:text-sm font-semibold tracking-wide flex-1">{toastError}</p>
          <button
            type="button"
            onClick={() => setToastError(null)}
            className="p-1 text-white/80 hover:text-white rounded-lg hover:bg-rose-700/50 transition"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Floating Success Toast Notification Popup */}
      {toastSuccess && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 flex items-center space-x-3 px-4 py-3 bg-emerald-600 text-white rounded-2xl shadow-2xl border border-emerald-500 animate-in fade-in slide-in-from-top-4 duration-200 max-w-sm sm:max-w-md">
          <CheckCircle2 className="w-5 h-5 shrink-0 text-white" />
          <p className="text-xs sm:text-sm font-semibold tracking-wide flex-1">{toastSuccess}</p>
          <button
            type="button"
            onClick={() => setToastSuccess(null)}
            className="p-1 text-white/80 hover:text-white rounded-lg hover:bg-emerald-700/50 transition"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Left Subnav Tabs */}
        <Card className="w-full lg:w-64 p-3 shrink-0 h-fit space-y-1">
          {[
            { id: 'profile', label: 'User Profile', icon: User },
            { id: 'security', label: 'Security & Password', icon: Lock },
            { id: 'preferences', label: 'Application Preferences', icon: Sliders },
            { id: 'theme', label: 'Appearance & Theme', icon: Sun },
            { id: 'integrations', label: 'Service Integrations', icon: Layers },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  setChangeError(null);
                  setChangeSuccess(null);
                }}
                className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
                  isActive
                    ? 'bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </Card>

        {/* Right Settings Body */}
        <div className="flex-1 space-y-6">
          {/* 1. Profile Settings */}
          {activeTab === 'profile' && (
            <Card>
              <CardHeader
                title="User Profile"
                subtitle="Manage your personal information and system administrator role"
              />
              <CardContent className="space-y-6">
                <div className="flex items-center space-x-4">
                  <div className="w-16 h-16 rounded-2xl bg-brand-600 text-white font-bold text-xl flex items-center justify-center ring-2 ring-brand-500/20 shadow-md">
                    {user?.full_name ? user.full_name[0].toUpperCase() : 'U'}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                      {user?.full_name || 'System User'}
                    </h4>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{user?.email || 'user@example.com'}</p>
                    <Badge variant="purple" className="mt-1">
                      {user?.role || 'Administrator'} Role
                    </Badge>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Full Name</label>
                    <input
                      type="text"
                      readOnly
                      value={user?.full_name || ''}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Email Address</label>
                    <input
                      type="email"
                      readOnly
                      value={user?.email || ''}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Department</label>
                    <input
                      type="text"
                      value={user?.department || 'Engineering'}
                      disabled
                      className="w-full bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-500 cursor-not-allowed"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Assigned Role</label>
                    <input
                      type="text"
                      value={user?.role || 'EMPLOYEE'}
                      disabled
                      className="w-full bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-500 cursor-not-allowed"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 2. Security & Change Password Settings */}
          {activeTab === 'security' && (
            <Card>
              <CardHeader
                title="Security & Password Management"
                subtitle="Change your password regularly to secure access to your AI agent and Trello boards"
                action={
                  <span className="inline-flex items-center space-x-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-200 dark:border-emerald-500/20">
                    <ShieldCheck className="w-3.5 h-3.5 mr-1" />
                    <span>Argon2 Encrypted</span>
                  </span>
                }
              />
              <CardContent className="space-y-6">
                {changeError && (
                  <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/25 text-rose-700 dark:text-rose-400 text-xs flex items-start space-x-2.5">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span className="flex-1 font-medium">{changeError}</span>
                  </div>
                )}

                {changeSuccess && (
                  <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/25 text-emerald-800 dark:text-emerald-300 text-xs flex items-start space-x-2.5">
                    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                    <span className="flex-1 font-medium">{changeSuccess}</span>
                  </div>
                )}

                <form onSubmit={handleChangePasswordSubmit} className="space-y-4 text-xs max-w-lg">
                  <div>
                    <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                      Current Password
                    </label>
                    <div className="relative flex items-center">
                      <Lock className="w-4 h-4 text-slate-400 absolute left-3" />
                      <input
                        type={showCurrentPassword ? 'text' : 'password'}
                        required
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="Enter your current password"
                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-10 py-2.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                        className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                        tabIndex={-1}
                      >
                        {showCurrentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                      New Password
                    </label>
                    <div className="relative flex items-center">
                      <KeyRound className="w-4 h-4 text-slate-400 absolute left-3" />
                      <input
                        type={showNewPassword ? 'text' : 'password'}
                        required
                        minLength={8}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Minimum 8 characters"
                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-10 py-2.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                        tabIndex={-1}
                      >
                        {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Must contain at least 8 characters. We recommend a mix of letters, numbers, and symbols.
                    </p>
                  </div>

                  <div>
                    <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                      Confirm New Password
                    </label>
                    <div className="relative flex items-center">
                      <Lock className="w-4 h-4 text-slate-400 absolute left-3" />
                      <input
                        type={showConfirmPassword ? 'text' : 'password'}
                        required
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Re-type your new password"
                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-10 py-2.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                        tabIndex={-1}
                      >
                        {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="pt-2">
                    <Button
                      type="submit"
                      variant="primary"
                      size="sm"
                      disabled={isChangingPassword}
                      icon={isChangingPassword ? <Loader2 className="w-4 h-4 animate-spin" /> : undefined}
                    >
                      {isChangingPassword ? 'Updating Password...' : 'Change Password'}
                    </Button>
                  </div>
                </form>

                <div className="p-3.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 space-y-1">
                  <p className="font-semibold text-slate-700 dark:text-slate-300">Session Security Notice</p>
                  <p>
                    Changing your password will revoke all active refresh tokens. You will stay signed in on this current browser, but any sessions on other devices will need to sign in again.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 2. Application Preferences */}
          {activeTab === 'preferences' && (
            <Card>
              <CardHeader
                title="Application Preferences"
                subtitle="Configure dashboard notifications and automatic refresh options"
              />
              <CardContent className="space-y-4 text-xs">
                <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div>
                    <p className="font-semibold text-slate-800 dark:text-slate-200">Pending Action Notifications</p>
                    <p className="text-slate-500 dark:text-slate-400 text-[11px]">
                      Alert in-app whenever an AI natural-language mutation requires human review.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={emailNotifications}
                    onChange={(e) => setEmailNotifications(e.target.checked)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                </div>

                <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div>
                    <p className="font-semibold text-slate-800 dark:text-slate-200">Strict Privacy Enforcement</p>
                    <p className="text-slate-500 dark:text-slate-400 text-[11px]">
                      Prevent card bodies and private records from ever entering LLM message contexts.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={strictPrivacyMode}
                    onChange={(e) => setStrictPrivacyMode(e.target.checked)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                </div>

                <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div>
                    <p className="font-semibold text-slate-800 dark:text-slate-200">Auto-refresh Dashboard Metrics</p>
                    <p className="text-slate-500 dark:text-slate-400 text-[11px]">
                      Poll health and task rollups every 30 seconds automatically.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={autoRefreshReports}
                    onChange={(e) => setAutoRefreshReports(e.target.checked)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* 3. Theme Settings */}
          {activeTab === 'theme' && (
            <Card>
              <CardHeader
                title="Appearance & Theme"
                subtitle="Select your preferred dashboard visual theme"
              />
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Light Theme Card */}
                  <div
                    onClick={() => setTheme('light')}
                    className={`p-5 rounded-2xl border-2 cursor-pointer transition text-center space-y-3 ${
                      theme === 'light'
                        ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-500/10 shadow-sm'
                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                    }`}
                  >
                    <div className="p-3 mx-auto w-fit rounded-xl bg-amber-500/10 text-amber-600">
                      <Sun className="w-6 h-6" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Light Theme</h4>
                      <p className="text-xs text-slate-500 mt-0.5">Clean enterprise standard</p>
                    </div>
                    {theme === 'light' && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-500/15 text-brand-700 dark:text-brand-300 border border-brand-500/30">
                        Active Theme
                      </span>
                    )}
                  </div>

                  {/* Dark Theme Card */}
                  <div
                    onClick={() => setTheme('dark')}
                    className={`p-5 rounded-2xl border-2 cursor-pointer transition text-center space-y-3 ${
                      theme === 'dark'
                        ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-500/10 shadow-sm'
                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                    }`}
                  >
                    <div className="p-3 mx-auto w-fit rounded-xl bg-slate-700 text-slate-200">
                      <Moon className="w-6 h-6" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Dark Theme</h4>
                      <p className="text-xs text-slate-500 mt-0.5">High-contrast dark mode for low-light</p>
                    </div>
                    {theme === 'dark' && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-500/15 text-brand-700 dark:text-brand-300 border border-brand-500/30">
                        Active Theme
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 4. Integration Configuration UI */}
          {activeTab === 'integrations' && (
            <div className="space-y-4 text-xs">
              {/* Trello Status Card */}
              <Card>
                <CardHeader
                  title="Trello REST API Integration"
                  subtitle="Board task synchronization and card mutations"
                  action={<Badge variant="info">Configured on Backend</Badge>}
                />
                <CardContent className="space-y-3">
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-2">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Board Identifier:</span>
                      <span className="font-mono text-slate-800 dark:text-slate-200">
                        board_eng_sprint_prod_01
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">API Key / Token:</span>
                      <span className="font-mono text-slate-400">•••••••••••••••• (Managed via Backend .env)</span>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-400 flex items-center space-x-1.5">
                    <Lock className="w-3.5 h-3.5 text-slate-400" />
                    <span>In accordance with Section 5 privacy rules, tokens are never exposed to React.</span>
                  </p>
                </CardContent>
              </Card>

              {/* Gemini Status Card */}
              <Card>
                <CardHeader
                  title="Google Gemini AI Provider"
                  subtitle="Intent interpretation & dynamic tool selection"
                  action={<Badge variant="success">SDK google-genai</Badge>}
                />
                <CardContent className="space-y-3">
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-2">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Active Model:</span>
                      <span className="font-mono font-semibold text-brand-600 dark:text-brand-400">
                        gemini-2.5-flash
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Orchestration Boundary:</span>
                      <span className="text-slate-700 dark:text-slate-300">Tool Selection Only (No Arbitrary Exec)</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* n8n Status Card */}
              <Card>
                <CardHeader
                  title="n8n Workflow Automation"
                  subtitle="Cron triggers & outbound webhook notifications"
                  action={<Badge variant="purple">Orchestrator Ready</Badge>}
                />
                <CardContent className="space-y-3">
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-2">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Webhook Target:</span>
                      <span className="font-mono text-slate-800 dark:text-slate-200">
                        http://localhost:5678/webhook
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
