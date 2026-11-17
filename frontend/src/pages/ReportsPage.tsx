import React, { useState, useEffect } from 'react';
import {
  RefreshCw,
  Printer,
  Download,
  ListTodo,
  CheckCircle2,
  Clock,
  Activity,
  Layers,
  Bot,
} from 'lucide-react';
import { Card, CardHeader } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import { fetchWorkloadReport } from '../services/api';

export const ReportsPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();
  const [report, setReport] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadReport = async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    try {
      const data = await fetchWorkloadReport(undefined, activeBoardId || undefined);
      if (data && data.status === 'SUCCESS') {
        setReport(data);
      }
    } catch (err) {
      console.error('Failed to load workload report:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, [isAuthenticated, activeBoardId]);

  const totalTasks = report?.total_tasks || 0;
  const completed = report?.completed || 0;
  const inProgress = report?.in_progress || 0;
  const todo = report?.todo || 0;
  const completionRate = report?.completion_rate || 0;
  const listBreakdown: Record<string, number> = report?.list_breakdown || {};
  const health = report?.health || 'OPTIMAL';

  return (
    <div className="space-y-6">
      {/* Control Filter Bar */}
      <Card className="p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Sprint Workload & Card Distribution
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Aggregated directly from live Trello lists and card counts
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadReport}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh Metrics
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            icon={<Printer className="w-3.5 h-3.5" />}
          >
            Print
          </Button>
        </div>
      </Card>

      {/* Workload Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-5">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
            <ListTodo className="w-3.5 h-3.5 text-slate-400" />
            <span>Total Trello Cards</span>
          </span>
          <h4 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
            {totalTasks} Cards
          </h4>
          <p className="text-[11px] text-slate-500 mt-1">Across all active board lists</p>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider flex items-center space-x-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>Completion Rate</span>
          </span>
          <h4 className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
            {completionRate}%
          </h4>
          <p className="text-[11px] text-slate-500 mt-1">{completed} cards in Done list</p>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold text-sky-600 dark:text-sky-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Clock className="w-3.5 h-3.5 text-sky-500" />
            <span>In Progress / Doing</span>
          </span>
          <h4 className="text-2xl font-bold text-sky-600 dark:text-sky-400 mt-1">
            {inProgress} Cards
          </h4>
          <p className="text-[11px] text-slate-500 mt-1">Currently being worked on</p>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider flex items-center space-x-1.5">
            <Activity className="w-3.5 h-3.5 text-purple-500" />
            <span>Sprint Health</span>
          </span>
          <h4 className="text-2xl font-bold text-purple-600 dark:text-purple-400 mt-1">
            {health}
          </h4>
          <p className="text-[11px] text-slate-500 mt-1">{todo} cards in backlog queue</p>
        </Card>
      </div>

      {/* List Breakdown Table */}
      <Card className="overflow-hidden">
        <CardHeader
          title="Trello Board List Distribution"
          subtitle="Real-time count of cards organized by list"
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold">
                <th className="py-3 px-4">Trello List Name</th>
                <th className="py-3 px-4">Card Count</th>
                <th className="py-3 px-4">Share of Board</th>
                <th className="py-3 px-4">Status Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Object.keys(listBreakdown).length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-slate-400 italic">
                    No list data available from Trello MCP.
                  </td>
                </tr>
              ) : (
                Object.entries(listBreakdown).map(([listName, count]) => {
                  const share = totalTasks > 0 ? Math.round((count / totalTasks) * 100) : 0;
                  const isDone = listName.toLowerCase().includes('done');
                  const isDoing = listName.toLowerCase().includes('doing') || listName.toLowerCase().includes('progress');

                  return (
                    <tr key={listName} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-slate-100">
                        {listName}
                      </td>
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-700 dark:text-slate-300">
                        {count}
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="flex items-center space-x-2">
                          <div className="w-24 bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                            <div
                              style={{ width: `${share}%` }}
                              className={`h-full ${
                                isDone ? 'bg-emerald-500' : isDoing ? 'bg-sky-500' : 'bg-purple-500'
                              }`}
                            />
                          </div>
                          <span className="font-mono text-slate-500 text-[11px]">{share}%</span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <Badge
                          variant={
                            isDone ? 'success' : isDoing ? 'info' : 'neutral'
                          }
                        >
                          {isDone ? 'COMPLETED' : isDoing ? 'ACTIVE' : 'BACKLOG'}
                        </Badge>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
