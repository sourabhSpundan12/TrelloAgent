import React, { useState } from 'react';
import {
  User,
  Sliders,
  Sun,
  Moon,
  Layers,
  Lock,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { useTheme } from '../context/ThemeContext';

export const SettingsPage: React.FC = () => {
  const { theme, setTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<'profile' | 'preferences' | 'theme' | 'integrations'>('profile');

  // Preference toggles
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [autoRefreshReports, setAutoRefreshReports] = useState(true);
  const [strictPrivacyMode, setStrictPrivacyMode] = useState(true);

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Left Subnav Tabs */}
        <Card className="w-full lg:w-64 p-3 shrink-0 h-fit space-y-1">
          {[
            { id: 'profile', label: 'User Profile', icon: User },
            { id: 'preferences', label: 'Application Preferences', icon: Sliders },
            { id: 'theme', label: 'Appearance & Theme', icon: Sun },
            { id: 'integrations', label: 'Service Integrations', icon: Layers },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
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
                  <img
                    src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120&h=120&fit=crop&crop=faces"
                    alt="Sarah Connor"
                    className="w-16 h-16 rounded-2xl object-cover ring-2 ring-slate-200 dark:ring-slate-700"
                  />
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Sarah Connor</h4>
                    <p className="text-xs text-slate-500 dark:text-slate-400">s.connor@example.com</p>
                    <Badge variant="purple" className="mt-1">
                      Platform Administrator
                    </Badge>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Full Name</label>
                    <input
                      type="text"
                      defaultValue="Sarah Connor"
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Email Address</label>
                    <input
                      type="email"
                      defaultValue="s.connor@example.com"
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Department</label>
                    <input
                      type="text"
                      defaultValue="Platform Security & Architecture"
                      disabled
                      className="w-full bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-500 cursor-not-allowed"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 dark:text-slate-400 font-medium mb-1">Employee ID</label>
                    <input
                      type="text"
                      defaultValue="EMP-101"
                      disabled
                      className="w-full bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-500 cursor-not-allowed"
                    />
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <Button variant="primary" size="sm">
                    Save Profile
                  </Button>
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
