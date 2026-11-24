import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  Mail,
  Layers,
  Users,
  Sparkles,
  Clock,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  ShieldCheck,
  CheckSquare,
  Briefcase,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '../common/Card';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { useAuth } from '../../context/AuthContext';
import {
  fetchReportPreviewSummary,
  fetchEmployeeSummaries,
  downloadBoardWeeklyPdf,
  downloadEmployeeWeeklyPdf,
} from '../../services/api';
import { EmployeeTaskReportSummary } from '../../types';
import { PdfReportModal } from './PdfReportModal';

interface DashboardReportsWidgetProps {
  boardId?: string;
  onNavigate?: (tab: string) => void;
}

export const DashboardReportsWidget: React.FC<DashboardReportsWidgetProps> = ({
  boardId,
  onNavigate,
}) => {
  const { user } = useAuth();
  const [context, setContext] = useState<'board' | 'employee'>('board');
  const [employees, setEmployees] = useState<EmployeeTaskReportSummary[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('');
  const [selectedEmployeeName, setSelectedEmployeeName] = useState<string>('');

  const [preview, setPreview] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Load employee directory
  useEffect(() => {
    const loadEmps = async () => {
      try {
        const data = await fetchEmployeeSummaries(boardId);
        setEmployees(data || []);
        if (data && data.length > 0 && !selectedEmployeeId) {
          setSelectedEmployeeId(data[0].employee_id);
          setSelectedEmployeeName(data[0].employee_name || data[0].employee_id);
        }
      } catch (err) {
        console.error('Failed to load employee list for dashboard reports widget:', err);
      }
    };
    loadEmps();
  }, [boardId]);

  // Load preview data
  const loadReportData = async () => {
    try {
      setIsLoading(true);
      if (context === 'employee' && !selectedEmployeeId) {
        setPreview(null);
        return;
      }
      const res = await fetchReportPreviewSummary(context, {
        employee_id: context === 'employee' ? selectedEmployeeId : undefined,
        employee_name: context === 'employee' ? selectedEmployeeName : undefined,
        board_id: boardId,
      });
      if (res && res.summary) {
        setPreview(res.summary);
      }
    } catch (err: any) {
      console.error('Failed to load report summary on dashboard:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadReportData();
  }, [context, selectedEmployeeId, boardId]);

  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const handleQuickDownload = async () => {
    try {
      setIsDownloading(true);
      let blob: Blob;
      let filename = '';
      const dateTag = new Date().toISOString().slice(0, 10).replace(/-/g, '');

      if (context === 'board') {
        blob = await downloadBoardWeeklyPdf(boardId);
        filename = `Board_Weekly_Report_${dateTag}.pdf`;
      } else {
        blob = await downloadEmployeeWeeklyPdf(selectedEmployeeId, selectedEmployeeName, boardId);
        const safeName = (selectedEmployeeName || selectedEmployeeId).replace(/[^\w\-]/g, '_');
        filename = `Employee_Report_${safeName}_${dateTag}.pdf`;
      }

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setToastMessage({ type: 'success', text: `Downloaded ${filename} successfully!` });
    } catch (err: any) {
      setToastMessage({ type: 'error', text: err?.message || 'Failed to download report PDF.' });
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <>
      <Card className="border-t-4 border-t-brand-500 overflow-hidden">
        <CardHeader
          title={
            <div className="flex items-center space-x-2">
              <FileText className="w-5 h-5 text-brand-600 dark:text-brand-400" />
              <span>Weekly Executive Reports & Feedback</span>
            </div>
          }
          // subtitle="Instant weekly performance evaluation, time tracking breakdown, capacity occupancy, and AI feedback statements."
          action={
            <div className="flex items-center space-x-2">
              <Button
                variant="outline"
                size="sm"
                disabled={isDownloading || isLoading}
                onClick={handleQuickDownload}
                className="flex items-center space-x-1.5"
              >
                {isDownloading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                <span className="hidden sm:inline">Download PDF</span>
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsModalOpen(true)}
                className="flex items-center space-x-1.5"
              >
                <Mail className="w-3.5 h-3.5" />
                <span>Send to Admin</span>
              </Button>

              {onNavigate && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onNavigate('reports')}
                  className="hidden md:flex items-center space-x-1"
                >
                  <span>Full View</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              )}
            </div>
          }
        />
        <CardContent className="space-y-4">
          {/* Toast Alert */}
          {toastMessage && (
            <div
              className={`p-3 rounded-xl flex items-center space-x-2 text-xs animate-in fade-in duration-150 ${toastMessage.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300 border border-rose-200 dark:border-rose-800'
                }`}
            >
              {toastMessage.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
              )}
              <span className="font-medium">{toastMessage.text}</span>
            </div>
          )}

          {/* Context Selector Bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-slate-800/80">
            {/* Context Pills */}
            <div className="flex items-center space-x-2 bg-slate-100 dark:bg-slate-800/70 p-1 rounded-xl">
              <button
                type="button"
                onClick={() => setContext('board')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 ${context === 'board'
                  ? 'bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-xs'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>1) Board-wise Report</span>
              </button>

              <button
                type="button"
                onClick={() => setContext('employee')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 ${context === 'employee'
                  ? 'bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-xs'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
              >
                <Users className="w-3.5 h-3.5" />
                <span>2) Employee-based Report</span>
              </button>
            </div>

            {/* Employee Selector if Employee Context */}
            {context === 'employee' && (
              <div className="flex items-center space-x-2 w-full sm:w-auto">
                <span className="text-xs text-slate-500 font-medium shrink-0">Employee:</span>
                <select
                  value={selectedEmployeeId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedEmployeeId(id);
                    const found = employees.find((x) => x.employee_id === id);
                    setSelectedEmployeeName(found?.employee_name || id);
                  }}
                  className="px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                >
                  {employees.map((emp) => (
                    <option key={emp.employee_id} value={emp.employee_id}>
                      {emp.employee_name || emp.employee_id} ({emp.completed_count} completed · {emp.performance_level})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {preview?.week_range && (
              <Badge variant="neutral" className="text-[11px]">
                Sprint: {preview.week_range}
              </Badge>
            )}
          </div>

          {/* Main 4-Section Dashboard Presentation */}
          {isLoading ? (
            <div className="py-12 flex flex-col items-center justify-center space-y-2 text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
              <span>Compiling live weekly performance & feedback...</span>
            </div>
          ) : preview ? (
            <div className="space-y-4">
              {/* 4 Metric Highlights */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {/* 1. Weekly Report Metric */}
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/80 space-y-1">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-[11px] font-medium">
                    <span>1. Weekly Report</span>
                    <CheckSquare className="w-3.5 h-3.5 text-emerald-500" />
                  </div>
                  <div className="flex items-baseline space-x-1.5">
                    <span className="text-xl font-bold text-slate-900 dark:text-slate-100">
                      {preview.cards_done ?? 0}
                    </span>
                    <span className="text-xs text-slate-500">cards done</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    {context === 'board' ? 'Completed across board this week' : 'Delivered by employee this week'}
                  </p>
                </div>

                {/* 2. Performance: Estimated Hours */}
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/80 space-y-1">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-[11px] font-medium">
                    <span>2. Performance (Est)</span>
                    <Clock className="w-3.5 h-3.5 text-brand-500" />
                  </div>
                  <div className="flex items-baseline space-x-1.5">
                    <span className="text-xl font-bold text-slate-900 dark:text-slate-100">
                      {preview.total_estimated_hours ?? 0}
                    </span>
                    <span className="text-xs text-slate-500">hours</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Total estimated time in entire week
                  </p>
                </div>

                {/* 3. Performance: Actual Hours */}
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/80 space-y-1">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-[11px] font-medium">
                    <span>2. Performance (Actual)</span>
                    <TrendingUp className="w-3.5 h-3.5 text-purple-500" />
                  </div>
                  <div className="flex items-baseline space-x-1.5">
                    <span className="text-xl font-bold text-purple-600 dark:text-purple-400">
                      {preview.total_actual_hours ?? 0}
                    </span>
                    <span className="text-xs text-slate-500">hours</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Total actual time taken in entire week
                  </p>
                </div>

                {/* 4. Occupancy Report */}
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/80 space-y-1">
                  <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-[11px] font-medium">
                    <span>3. Occupancy Report</span>
                    <Briefcase className="w-3.5 h-3.5 text-indigo-500" />
                  </div>
                  <div className="flex items-baseline space-x-1.5">
                    <span className="text-xl font-bold text-brand-600 dark:text-brand-400">
                      {preview.occupancy_percentage ?? 0}%
                    </span>
                    <span className="text-xs text-slate-500">bandwidth</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Capacity allocated against 45h standard
                  </p>
                </div>
              </div>

              {/* 4. AI Feedback Report with Explicit Comparison Statement */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-brand-500/10 via-emerald-500/5 to-transparent border border-brand-500/25 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5 text-xs font-bold text-brand-700 dark:text-brand-300 uppercase tracking-wide">
                    <Sparkles className="w-4 h-4 text-brand-500" />
                    <span>4. Feedback Report & Hours Comparison</span>
                  </div>
                  <Badge variant="success">Audited</Badge>
                </div>

                {/* Explicit statement required by user */}
                <div className="p-3 rounded-lg bg-white/80 dark:bg-slate-900/80 border border-brand-500/20 shadow-xs">
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-100 leading-relaxed font-sans">
                    &ldquo;{preview.explicit_hours_statement}&rdquo;
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1 text-xs">
                  <div className="flex items-start space-x-2 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 p-2.5 rounded-lg border border-emerald-500/20">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block">What You Have Done Good (Strengths):</span>
                      <span className="text-[11px] text-slate-600 dark:text-slate-300">
                        {context === 'board'
                          ? `Delivered ${preview.cards_done} task cards on schedule, maintaining steady milestone progress.`
                          : `High milestone execution, completing ${preview.cards_done} card(s) with ${preview.on_time_rate ?? 100}% SLA compliance.`}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2 text-amber-700 dark:text-amber-300 bg-amber-500/10 p-2.5 rounded-lg border border-amber-500/20">
                    <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block">What Things You Should Focus More On:</span>
                      <span className="text-[11px] text-slate-600 dark:text-slate-300">
                        {context === 'board'
                          ? 'Tighten estimation accuracy on backlog items requiring >4h and rebalance in-progress cards.'
                          : 'Buffer edge-case investigations in estimation and update blocked cards earlier in sprint.'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-slate-400 text-xs">
              No report metrics available for this selection.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reusable Official PDF Export & Email Modal */}
      <PdfReportModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        boardId={boardId}
        defaultEmployeeId={context === 'employee' ? selectedEmployeeId : undefined}
        defaultEmployeeName={context === 'employee' ? selectedEmployeeName : undefined}
      />
    </>
  );
};

