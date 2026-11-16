import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { TopNavbar } from './TopNavbar';

interface MainLayoutProps {
  currentTab: string;
  onTabChange: (tabId: string) => void;
  children: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  currentTab,
  onTabChange,
  children,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden font-sans">
      {/* Desktop Sidebar */}
      <div className="hidden md:flex h-full shrink-0">
        <Sidebar
          currentTab={currentTab}
          onTabChange={onTabChange}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
        />
      </div>

      {/* Mobile Drawer Sidebar */}
      {isMobileSidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setIsMobileSidebarOpen(false)}
          />
          <div className="relative z-10 w-72 max-w-[85vw] h-full shadow-2xl flex flex-col bg-white dark:bg-slate-900 animate-in slide-in-from-left duration-200">
            <Sidebar
              currentTab={currentTab}
              onTabChange={(tabId) => {
                onTabChange(tabId);
                setIsMobileSidebarOpen(false);
              }}
              isCollapsed={false}
              onToggleCollapse={() => setIsMobileSidebarOpen(false)}
              isMobile={true}
              onCloseMobile={() => setIsMobileSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Main Panel */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopNavbar
          currentTab={currentTab}
          onTabChange={onTabChange}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen(true)}
        />
        <main
          className={`flex-1 overflow-y-auto ${
            currentTab === 'ai-assistant'
              ? 'p-2 sm:p-4 md:p-6 overflow-hidden flex flex-col'
              : 'p-3 sm:p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6'
          }`}
        >
          <div
            className={`max-w-7xl mx-auto w-full ${
              currentTab === 'ai-assistant' ? 'h-full flex flex-col flex-1' : 'space-y-6'
            }`}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

