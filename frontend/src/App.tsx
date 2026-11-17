import React, { useState } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { BoardProvider } from './context/BoardContext';
import { AuthPage } from './pages/AuthPage';
import { MainLayout } from './components/layout/MainLayout';
import { OverviewPage } from './pages/OverviewPage';
import { AIAssistantPage } from './pages/AIAssistantPage';
import { TasksPage } from './pages/TasksPage';
import { EmployeesPage } from './pages/EmployeesPage';
import { ReportsPage } from './pages/ReportsPage';
import { ActivityHistoryPage } from './pages/ActivityHistoryPage';
import { ToolManagementPage } from './pages/ToolManagementPage';
import { BoardsPage } from './pages/BoardsPage';
import { SettingsPage } from './pages/SettingsPage';
import { Loader2 } from 'lucide-react';

export const AppContent: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [currentTab, setCurrentTab] = useState<string>('overview');

  if (isLoading) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-950 text-slate-600 dark:text-slate-400">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600 mb-3" />
        <p className="text-xs font-medium tracking-wide">Initializing session...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthPage />;
  }

  const renderActivePage = () => {
    switch (currentTab) {
      case 'overview':
        return <OverviewPage onNavigate={setCurrentTab} />;
      case 'ai-assistant':
        return <AIAssistantPage />;
      case 'tasks':
        return <TasksPage />;
      case 'employees':
        return <EmployeesPage />;
      case 'reports':
        return <ReportsPage />;
      case 'activity':
        return <ActivityHistoryPage />;
      case 'tools':
        return <ToolManagementPage />;
      case 'boards':
        return <BoardsPage onNavigate={setCurrentTab} />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <OverviewPage onNavigate={setCurrentTab} />;
    }
  };

  return (
    <MainLayout currentTab={currentTab} onTabChange={setCurrentTab}>
      {renderActivePage()}
    </MainLayout>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BoardProvider>
          <AppContent />
        </BoardProvider>
      </AuthProvider>
    </ThemeProvider>
  );
};

export default App;
