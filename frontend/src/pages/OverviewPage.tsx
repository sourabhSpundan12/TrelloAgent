import React, { useState, useEffect } from 'react';
import {
  CheckSquare,
  Clock,
  Eye,
  ListTodo,
  CheckCircle2,
  Wrench,
  ShieldCheck,
  Calendar,
  ArrowRight,
  ExternalLink,
  Bot,
  RefreshCw,
} from 'lucide-react';
import { StatCard } from '../components/common/StatCard';
import { Card, CardHeader, CardContent } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { useAuth } from '../context/AuthContext';
import { useBoard } from '../context/BoardContext';
import { fetchOverviewStats } from '../services/api';
import { DashboardReportsWidget } from '../components/reports/DashboardReportsWidget';

interface OverviewPageProps {
  onNavigate: (tab: string) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ onNavigate }) => {
  const { isAuthenticated } = useAuth();
  const { activeBoard, activeBoardId } = useBoard();
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadStats = async (forceRefresh: boolean = false, silent: boolean = false) => {
    if (!isAuthenticated) return;
    if (!silent) setIsLoading(true);
    try {
      const data = await fetchOverviewStats(undefined, activeBoardId || undefined, forceRefresh);
      if (data && data.status === 'SUCCESS') {
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to load overview stats:', err);
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStats(false, false);
    // Real-time synchronization polling every 15 seconds to track external Trello changes
    const interval = setInterval(() => {
      loadStats(false, true);
    }, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated, activeBoardId]);

  const tasks = stats?.tasks || { total: 0, todo: 0, doing: 0, done: 0, completion_rate: 0 };
  const system = stats?.system || { active_tools: 9, pending_approvals: 0, executed_mutations: 0 };

  const donePercent = tasks.total > 0 ? Math.round((tasks.done / tasks.total) * 100) : 0;
  const doingPercent = tasks.total > 0 ? Math.round((tasks.doing / tasks.total) * 100) : 0;
  const todoPercent = tasks.total > 0 ? Math.round((tasks.todo / tasks.total) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Header Action Bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            System Operational Overview
          </h2>
          {/* <p className="text-xs text-slate-500 dark:text-slate-400">
            Real-time status of Trello tasks, MCP tools, and human-in-the-loop approvals
          </p> */}
        </div>
        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => loadStats(true, false)}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onNavigate('ai-assistant')}
            icon={<Bot className="w-3.5 h-3.5" />}
          >
            AI Assistant
          </Button>
        </div>
      </div>

      {/* Active Board Information Banner */}
      {activeBoard && (
        <div className="p-3.5 rounded-2xl bg-gradient-to-r from-emerald-500/10 via-brand-500/5 to-transparent border border-emerald-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400 shrink-0">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-900 dark:text-white">
                  Active Board: {activeBoard.name}
                </span>
                {/* <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200/60 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                  {activeBoard.board_id}
                </span> */}
              </div>
              {/* <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Showing live cards, member workloads, and mutation audits for this Trello workspace.
              </p> */}
            </div>
          </div>
          <div className="flex items-center space-x-2 self-end sm:self-center">
            <a
              href={`https://trello.com/b/${activeBoard.board_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 text-[11px] font-medium transition shadow-2xs"
            >
              <span>View in Trello</span>
              <ExternalLink className="w-3 h-3 text-slate-400" />
            </a>
          </div>
        </div>
      )}

      {/* 6 Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          title="Total Cards"
          value={tasks.total}
          icon={CheckSquare}
          color="slate"
          subtitle={activeBoard ? activeBoard.name : 'Configured Board'}
          onClick={() => onNavigate('tasks')}
        />
        <StatCard
          title="Completed"
          value={tasks.done}
          icon={CheckCircle2}
          color="emerald"
          trend={{ value: `${donePercent}% done`, isPositive: true }}
          onClick={() => onNavigate('tasks')}
        />
        <StatCard
          title="In Progress / Doing"
          value={tasks.doing}
          icon={Clock}
          color="blue"
          subtitle="Actively worked on"
          onClick={() => onNavigate('tasks')}
        />
        <StatCard
          title="To Do"
          value={tasks.todo}
          icon={ListTodo}
          color="purple"
          subtitle="Sprint backlog queue"
          onClick={() => onNavigate('tasks')}
        />
        <StatCard
          title="Active MCP Tools"
          value={system.active_tools}
          icon={Wrench}
          color="slate"
          subtitle="MongoDB Tool Registry"
          onClick={() => onNavigate('tools')}
        />
        {/* <StatCard
          title="Executed Actions"
          value={system.executed_mutations}
          icon={ShieldCheck}
          color="amber"
          subtitle="Approved mutations"
          onClick={() => onNavigate('activity')}
        /> */}
      </div>

      {/* Weekly Executive Reports & AI Feedback Widget on Dashboard */}
      <DashboardReportsWidget
        boardId={activeBoardId}
        onNavigate={onNavigate}
      />

      {/* Main Grid: Status Distribution & AI Integration Highlights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 1. Live Task Distribution by Status */}
        <Card className="lg:col-span-1">
          <CardHeader
            title="Trello List Breakdown"
            subtitle="Live cards across configured board lists"
            action={
              <Button variant="ghost" size="sm" onClick={() => onNavigate('tasks')}>
                View Board
              </Button>
            }
          />
          <CardContent className="space-y-4">
            {/* Multi-segment Progress Bar */}
            <div className="h-3 w-full rounded-full bg-slate-100 dark:bg-slate-800 flex overflow-hidden">
              <div style={{ width: `${donePercent}%` }} className="bg-emerald-500 h-full" title={`Completed: ${donePercent}%`} />
              <div style={{ width: `${doingPercent}%` }} className="bg-sky-500 h-full" title={`In Progress: ${doingPercent}%`} />
              <div style={{ width: `${todoPercent}%` }} className="bg-slate-400 dark:bg-slate-600 h-full" title={`TODO: ${todoPercent}%`} />
            </div>

            {/* Status Legend Breakdown */}
            <div className="space-y-3 pt-2">
              {[
                { label: 'Completed (Done)', count: tasks.done, percent: donePercent, color: 'bg-emerald-500' },
                { label: 'In Progress (Doing)', count: tasks.doing, percent: doingPercent, color: 'bg-sky-500' },
                { label: 'Pending (To Do)', count: tasks.todo, percent: todoPercent, color: 'bg-slate-400 dark:bg-slate-600' },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${item.color}`} />
                    <span className="text-slate-700 dark:text-slate-300 font-medium">{item.label}</span>
                  </div>
                  <div className="flex items-center space-x-3 text-slate-500 dark:text-slate-400">
                    <span className="font-semibold text-slate-800 dark:text-slate-200">{item.count}</span>
                    <span className="w-8 text-right font-mono">{item.percent}%</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400 flex items-center justify-between">
              <span>Overall sprint completion:</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">{donePercent}%</span>
            </div>
          </CardContent>
        </Card>

        {/* 2. Conversational Agent Pipeline Status */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Conversational AI Agent Architecture"
            // subtitle="Human-in-the-Loop Execution Pipeline (Phase 7A)"
            action={
              <Button variant="primary" size="sm" onClick={() => onNavigate('ai-assistant')} icon={<Bot className="w-3.5 h-3.5" />}>
                AI Assistant
              </Button>
            }
          />
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="p-3.5 rounded-xl border border-brand-200 dark:border-brand-500/20 bg-brand-50/40 dark:bg-brand-500/5 space-y-1.5">
                <span className="font-semibold text-brand-900 dark:text-brand-300 block flex items-center space-x-1.5">
                  <Bot className="w-4 h-4 text-brand-600" />
                  <span>1. Natural Interface</span>
                </span>
                <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
                  Users manage tasks using natural language in chat. Gemini 3.5 Flash Lite parses intents and parameters with zero manual forms needed.
                </p>
              </div>

              <div className="p-3.5 rounded-xl border border-amber-200 dark:border-amber-500/20 bg-amber-50/40 dark:bg-amber-500/5 space-y-1.5">
                <span className="font-semibold text-amber-900 dark:text-amber-300 block flex items-center space-x-1.5">
                  <ShieldCheck className="w-4 h-4 text-amber-600" />
                  <span>2. Live Draft Preview</span>
                </span>
                <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
                  Mutations generate structured previews in Atlas. Users can reply &quot;Confirm&quot;, &quot;Cancel&quot;, or request edits in chat before any write occurs.
                </p>
              </div>

              <div className="p-3.5 rounded-xl border border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/40 dark:bg-emerald-500/5 space-y-1.5">
                <span className="font-semibold text-emerald-900 dark:text-emerald-300 block flex items-center space-x-1.5">
                  <Wrench className="w-4 h-4 text-emerald-600" />
                  <span>3. MCP Execution</span>
                </span>
                <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
                  Upon approval, actions execute atomically through the Model Context Protocol (MCP) tool registry, syncing real cards to Trello.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
              <span className="text-slate-600 dark:text-slate-400">
                Pending approvals awaiting user confirmation:
              </span>
              <Badge variant={system.pending_approvals > 0 ? 'warning' : 'neutral'}>
                {system.pending_approvals} Pending
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
