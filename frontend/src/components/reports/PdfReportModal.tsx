import React, { useState, useEffect } from 'react';
import {
  FileText,
  Mail,
  Download,
  Users,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  TrendingUp,
  Briefcase,
  User,
  Calendar,
} from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { useAuth } from '../../context/AuthContext';
import {
  downloadBoardWeeklyPdf,
  sendBoardWeeklyPdfEmail,
  downloadEmployeeWeeklyPdf,
  sendEmployeeWeeklyPdfEmail,
  fetchReportPreviewSummary,
  fetchEmployeeSummaries,
} from '../../services/api';
import { EmployeeTaskReportSummary } from '../../types';

interface PdfReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  boardId?: string;
  defaultEmployeeId?: string;
  defaultEmployeeName?: string;
}

export const PdfReportModal: React.FC<PdfReportModalProps> = ({
  isOpen,
  onClose,
  boardId,
  defaultEmployeeId,
  defaultEmployeeName,
}) => {
  const { user } = useAuth();
  const [context, setContext] = useState<'board' | 'employee'>('board');
  const [employees, setEmployees] = useState<EmployeeTaskReportSummary[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>(defaultEmployeeId || '');
  const [selectedEmployeeName, setSelectedEmployeeName] = useState<string>(defaultEmployeeName || '');
  const [adminEmail, setAdminEmail] = useState<string>(user?.email || '');

  // Reporting Date Range (Defaults to past 7 days)
  const defaultToDate = new Date().toISOString().slice(0, 10);
  const defaultFromDate = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const [fromDate, setFromDate] = useState<string>(defaultFromDate);
  const [toDate, setToDate] = useState<string>(defaultToDate);

  // Preview data state
  const [preview, setPreview] = useState<any>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Action states
  const [isDownloading, setIsDownloading] = useState(false);
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Load employees list on mount or open
  useEffect(() => {
    if (!isOpen) return;
    const loadEmps = async () => {
      try {
        const emps = await fetchEmployeeSummaries(boardId);
        setEmployees(emps || []);
        if (!selectedEmployeeId && emps.length > 0) {
          const first = emps[0];
          setSelectedEmployeeId(first.employee_id);
          setSelectedEmployeeName(first.employee_name || first.employee_id);
        }
      } catch (e) {
        console.error('Failed to load employee list for reports:', e);
      }
    };
    loadEmps();
  }, [isOpen, boardId]);

  // Load report preview
  const loadPreview = async () => {
    if (!isOpen) return;
    try {
      setIsLoadingPreview(true);
      setPreviewError(null);
      if (context === 'employee' && !selectedEmployeeId) {
        setPreview(null);
        return;
      }
      const res = await fetchReportPreviewSummary(context, {
        employee_id: context === 'employee' ? selectedEmployeeId : undefined,
        employee_name: context === 'employee' ? selectedEmployeeName : undefined,
        board_id: boardId,
        from_date: context === 'employee' ? fromDate : undefined,
        to_date: context === 'employee' ? toDate : undefined,
      });
      if (res && res.summary) {
        setPreview(res.summary);
      }
    } catch (err: any) {
      setPreviewError(err?.response?.data?.detail || err.message || 'Failed to generate report preview.');
    } finally {
      setIsLoadingPreview(false);
    }
  };

  useEffect(() => {
    loadPreview();
  }, [isOpen, context, selectedEmployeeId, boardId, fromDate, toDate]);

  // Handle Download PDF
  const handleDownload = async () => {
    try {
      setIsDownloading(true);
      let blob: Blob;
      let filename = '';
      const dateTag = new Date().toISOString().slice(0, 10).replace(/-/g, '');

      if (context === 'board') {
        blob = await downloadBoardWeeklyPdf(boardId);
        filename = `Board_Weekly_Report_${dateTag}.pdf`;
      } else {
        blob = await downloadEmployeeWeeklyPdf(
          selectedEmployeeId,
          selectedEmployeeName,
          boardId,
          fromDate,
          toDate
        );
        const safeName = (selectedEmployeeName || selectedEmployeeId).replace(/[^\w\-]/g, '_');
        filename = `Employee_Weekly_Report_${safeName}_${dateTag}.pdf`;
      }

      // Trigger browser download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setFeedback({ type: 'success', text: `Downloaded ${filename} successfully!` });
    } catch (err: any) {
      setFeedback({ type: 'error', text: err?.response?.data?.detail || err.message || 'Failed to download PDF.' });
    } finally {
      setIsDownloading(false);
    }
  };

  // Handle Send to Admin Email
  const handleSendEmail = async () => {
    const targetEmail = adminEmail.trim();
    if (!targetEmail || !targetEmail.includes('@')) {
      setFeedback({ type: 'error', text: 'Please provide a valid Admin Email address.' });
      return;
    }

    try {
      setIsSendingEmail(true);
      if (context === 'board') {
        await sendBoardWeeklyPdfEmail({
          board_id: boardId,
          admin_email: targetEmail,
        });
      } else {
        await sendEmployeeWeeklyPdfEmail({
          employee_id: selectedEmployeeId,
          employee_name: selectedEmployeeName,
          board_id: boardId,
          admin_email: targetEmail,
          from_date: fromDate,
          to_date: toDate,
        });
      }
      setFeedback({
        type: 'success',
        text: `Official PDF report successfully sent to admin email: ${targetEmail}`,
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        text: err?.response?.data?.detail || err.message || 'Failed to send email to admin.',
      });
    } finally {
      setIsSendingEmail(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div className="flex items-center space-x-2">
          <FileText className="w-5 h-5 text-brand-600 dark:text-brand-400" />
          <span>Export & Email Executive PDF Report</span>
        </div>
      }
      subtitle="Generate official PDF reports comprising Weekly Activity, Performance metrics, Occupancy capacity, and AI Feedback."
      maxWidth="lg"
    >
      <div className="space-y-4 text-xs">
        {/* Feedback Alert */}
        {feedback && (
          <div
            className={`p-3 rounded-xl flex items-center space-x-2 animate-in fade-in duration-150 ${
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300 border border-rose-200 dark:border-rose-800'
            }`}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
            )}
            <span className="flex-1 font-medium">{feedback.text}</span>
          </div>
        )}

        {/* 1. Report Context Selector */}
        <div className="space-y-1.5">
          <label className="text-slate-700 dark:text-slate-300 font-semibold block">
            Select Report Scope
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setContext('board');
                setFeedback(null);
              }}
              className={`p-3 rounded-xl border flex items-center space-x-2.5 transition text-left ${
                context === 'board'
                  ? 'border-brand-500 bg-brand-500/10 text-brand-600 dark:text-brand-400 shadow-sm'
                  : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
              }`}
            >
              <div className="p-2 rounded-lg bg-brand-500/15 text-brand-600 dark:text-brand-400 shrink-0">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <p className="font-bold text-xs">1) Board-wise Report</p>
                <p className="text-[10.5px] text-slate-500 dark:text-slate-400">
                  Full sprint deliverables, velocity & team occupancy
                </p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => {
                setContext('employee');
                setFeedback(null);
              }}
              className={`p-3 rounded-xl border flex items-center space-x-2.5 transition text-left ${
                context === 'employee'
                  ? 'border-brand-500 bg-brand-500/10 text-brand-600 dark:text-brand-400 shadow-sm'
                  : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
              }`}
            >
              <div className="p-2 rounded-lg bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 shrink-0">
                <Users className="w-4 h-4" />
              </div>
              <div>
                <p className="font-bold text-xs">2) Employee-based Report</p>
                <p className="text-[10.5px] text-slate-500 dark:text-slate-400">
                  Cards done, est vs actual time & individual AI coaching
                </p>
              </div>
            </button>
          </div>
        </div>

        {/* If Employee Context: Dropdown Selector & Date Range Picker */}
        {context === 'employee' && (
          <div className="space-y-3 p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
            <div className="space-y-1">
              <label className="text-slate-700 dark:text-slate-300 font-semibold block">
                Select Employee *
              </label>
              <select
                value={selectedEmployeeId}
                onChange={(e) => {
                  const empId = e.target.value;
                  setSelectedEmployeeId(empId);
                  const matched = employees.find((x) => x.employee_id === empId);
                  setSelectedEmployeeName(matched?.employee_name || empId);
                }}
                className="w-full px-3 py-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              >
                {employees.map((emp) => (
                  <option key={emp.employee_id} value={emp.employee_id}>
                    {emp.employee_name || emp.employee_id} ({emp.completed_count} completed · {emp.performance_level})
                  </option>
                ))}
              </select>
            </div>

            {/* Reporting Date Range Controls */}
            <div className="space-y-1.5 pt-2 border-t border-slate-200/60 dark:border-slate-700/60">
              <div className="flex items-center justify-between">
                <label className="text-slate-700 dark:text-slate-300 font-semibold flex items-center space-x-1.5">
                  <Calendar className="w-3.5 h-3.5 text-brand-500" />
                  <span>Reporting Date Range</span>
                </label>
                <div className="flex items-center space-x-1 text-[10px]">
                  <button
                    type="button"
                    onClick={() => {
                      const today = new Date().toISOString().slice(0, 10);
                      const past7 = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
                      setFromDate(past7);
                      setToDate(today);
                    }}
                    className="px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-brand-500 hover:text-white transition"
                  >
                    7 Days
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const today = new Date().toISOString().slice(0, 10);
                      const past14 = new Date(Date.now() - 14 * 86400000).toISOString().slice(0, 10);
                      setFromDate(past14);
                      setToDate(today);
                    }}
                    className="px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-brand-500 hover:text-white transition"
                  >
                    14 Days
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const today = new Date().toISOString().slice(0, 10);
                      const past30 = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
                      setFromDate(past30);
                      setToDate(today);
                    }}
                    className="px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-brand-500 hover:text-white transition"
                  >
                    30 Days
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div>
                  <span className="text-[10px] text-slate-500 dark:text-slate-400 block mb-1">From Date</span>
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 dark:text-slate-400 block mb-1">To Date</span>
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Live Report Preview Card with 4 Sections */}
        <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-1.5 text-slate-700 dark:text-slate-300 font-semibold">
              <Sparkles className="w-4 h-4 text-brand-500" />
              <span>Consolidated 4-Section Report Preview</span>
            </div>
            {preview?.week_range && (
              <Badge variant="neutral">Window: {preview.week_range}</Badge>
            )}
          </div>

          {isLoadingPreview ? (
            <div className="py-6 flex flex-col items-center justify-center space-y-1.5 text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
              <span>Compiling 4-section report metrics & AI feedback...</span>
            </div>
          ) : previewError ? (
            <p className="text-rose-500 text-xs">{previewError}</p>
          ) : preview ? (
            <div className="space-y-3">
              {/* Section 1 Preview: Weekly Task Report Counts */}
              <div className="p-2.5 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60 space-y-1.5">
                <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider block">
                  1. Weekly Task Report Metrics
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 text-center">
                  <div className="p-1.5 rounded bg-slate-50 dark:bg-slate-800/50">
                    <span className="text-[9.5px] text-slate-400 block">Assigned</span>
                    <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                      {preview.total_assigned ?? preview.cards_done ?? 0}
                    </span>
                  </div>
                  <div className="p-1.5 rounded bg-emerald-50/50 dark:bg-emerald-950/20">
                    <span className="text-[9.5px] text-emerald-600 dark:text-emerald-400 block">Completed</span>
                    <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                      {preview.cards_done ?? 0}
                    </span>
                  </div>
                  <div className="p-1.5 rounded bg-blue-50/50 dark:bg-blue-950/20">
                    <span className="text-[9.5px] text-blue-600 dark:text-blue-400 block">In-Progress</span>
                    <span className="text-xs font-bold text-blue-600 dark:text-blue-400">
                      {preview.in_progress_tasks ?? 0}
                    </span>
                  </div>
                  <div className="p-1.5 rounded bg-slate-50 dark:bg-slate-800/50">
                    <span className="text-[9.5px] text-slate-500 block">Pending</span>
                    <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
                      {preview.pending_tasks ?? 0}
                    </span>
                  </div>
                  <div className="p-1.5 rounded bg-rose-50/50 dark:bg-rose-950/20">
                    <span className="text-[9.5px] text-rose-600 dark:text-rose-400 block">Overdue</span>
                    <span className="text-xs font-bold text-rose-600 dark:text-rose-400">
                      {preview.overdue_tasks ?? 0}
                    </span>
                  </div>
                </div>
              </div>

              {/* Section 2: Performance Report Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">2. On-Time Rate</span>
                  <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                    {preview.on_time_rate ?? 100}%
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">Late: {preview.late_completed_tasks ?? 0}</span>
                </div>
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">2. Task Completion</span>
                  <span className="text-sm font-bold text-blue-600 dark:text-blue-400">
                    {preview.task_completion_rate ?? 0}%
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">{preview.completed_tasks ?? preview.cards_done ?? 0}/{preview.total_assigned ?? 0} tasks</span>
                </div>
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">2. Estimated Time</span>
                  <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                    {preview.total_estimated_hours ?? 0} hrs
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">Total Planned</span>
                </div>
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">2. Actual Time</span>
                  <span className="text-sm font-bold text-purple-600 dark:text-purple-400">
                    {preview.total_actual_hours ?? 0} hrs
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">Total Logged</span>
                </div>
              </div>

              {/* Section 3: Occupancy Report Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">3. Total Working Hours</span>
                  <span className="text-sm font-bold text-purple-600 dark:text-purple-400">
                    {preview.total_available_hours ?? 45} hrs
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">5 days x 9 hrs capacity</span>
                </div>
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">3. Occupancy Rate</span>
                  <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                    {preview.occupancy_percentage ?? 0}%
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">Capacity utilization</span>
                </div>
                <div className="p-2 rounded-lg bg-white dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-[10px] text-slate-400 font-medium block">3. Available Hours</span>
                  <span className="text-sm font-bold text-brand-600 dark:text-brand-400">
                    {preview.available_hours ?? 0} hrs
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5">Remaining capacity</span>
                </div>
              </div>

              {/* Section 4: PM Feedback & Time Tracking Callout Box */}
              {preview.explicit_hours_statement && (
                <div className="p-3 rounded-xl bg-brand-500/10 border border-brand-500/20 text-brand-700 dark:text-brand-300 space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-brand-600 dark:text-brand-400">
                    4. Project Manager Assessment & Time Allocation
                  </span>
                  <p className="text-[11px] leading-relaxed font-medium">
                    &ldquo;{preview.explicit_hours_statement}&rdquo;
                  </p>
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* 2. Admin Email Input */}
        <div className="space-y-1.5">
          <label className="text-slate-700 dark:text-slate-300 font-semibold block flex items-center justify-between">
            <span>Admin Email Recipient *</span>
            <span className="text-[10.5px] text-slate-400 font-normal">
              PDF will be attached directly to this address
            </span>
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="email"
              required
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder="admin@yourcompany.com"
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
          </div>
        </div>

        {/* Modal Footer Controls */}
        <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>

          <div className="flex items-center space-x-2">
            {/* Download Button */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isDownloading || isSendingEmail}
              onClick={handleDownload}
              className="flex items-center space-x-1.5"
            >
              {isDownloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              <span>Download PDF</span>
            </Button>

            {/* Send to Admin Email Button */}
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={isSendingEmail || isDownloading}
              onClick={handleSendEmail}
              className="flex items-center space-x-1.5"
            >
              {isSendingEmail ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Mail className="w-3.5 h-3.5" />
              )}
              <span>Send to Admin Mail</span>
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

