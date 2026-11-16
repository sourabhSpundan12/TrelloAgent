import React, { useState } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import { LoginModal } from './components/auth/LoginModal';
import { MainLayout } from './components/layout/MainLayout';
import { OverviewPage } from './pages/OverviewPage';
import { AIAssistantPage } from './pages/AIAssistantPage';
import { TasksPage } from './pages/TasksPage';
import { EmployeesPage } from './pages/EmployeesPage';
import { ReportsPage } from './pages/ReportsPage';
import { ActivityHistoryPage } from './pages/ActivityHistoryPage';
import { ToolManagementPage } from './pages/ToolManagementPage';
import { SettingsPage } from './pages/SettingsPage';

export const AppContent: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('overview');

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
      case 'settings':
        return <SettingsPage />;
      default:
        return <OverviewPage onNavigate={setCurrentTab} />;
    }
  };

  return (
    <>
      <MainLayout currentTab={currentTab} onTabChange={setCurrentTab}>
        {renderActivePage()}
      </MainLayout>
      <LoginModal />
    </>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
};

export default App;
