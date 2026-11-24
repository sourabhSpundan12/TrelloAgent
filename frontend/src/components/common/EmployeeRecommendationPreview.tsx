import React from 'react';
import {
  UserCheck,
  CheckCircle,
  AlertTriangle,
  Clock,
  Briefcase,
  TrendingUp,
  Award,
  Zap,
  Check,
  ChevronRight,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { EmployeeRecommendationResult, EmployeeCandidateEvaluation } from '../../types';

interface EmployeeRecommendationPreviewProps {
  data: EmployeeRecommendationResult;
  onAcceptRecommendation: (employee: EmployeeCandidateEvaluation) => void;
  onSelectAlternative: (employee: EmployeeCandidateEvaluation) => void;
  onCancel: () => void;
  isAssigning?: boolean;
}

export const EmployeeRecommendationPreview: React.FC<EmployeeRecommendationPreviewProps> = ({
  data,
  onAcceptRecommendation,
  onSelectAlternative,
  onCancel,
  isAssigning = false,
}) => {
  const recommended = data.recommended_employee;
  const alternatives = data.alternative_employees || [];

  if (!data.has_sufficient_capacity_overall || !recommended) {
    return (
      <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-xs space-y-3 shadow-xs">
        <div className="flex items-center space-x-2 text-amber-700 dark:text-amber-400 font-semibold">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>No Available Capacity for Task Assignment</span>
        </div>
        <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
          {data.no_capacity_reason || 'All employees are currently assigned to in-progress tasks or are at maximum capacity.'}
        </p>
        {alternatives.length > 0 && (
          <div className="pt-2 border-t border-amber-500/20 space-y-2">
            <span className="text-[11px] font-mono font-medium text-slate-500 dark:text-slate-400 uppercase">
              Current Team Workload Overview:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {alternatives.map((emp) => (
                <div
                  key={emp.employee_id}
                  className="p-2 rounded-xl bg-white/70 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 flex items-center justify-between"
                >
                  <div>
                    <span className="font-semibold text-slate-800 dark:text-slate-200 block truncate">{emp.employee_name}</span>
                    <span className="text-[10px] text-slate-500 dark:text-slate-400">
                      {emp.in_progress_count + emp.assigned_tasks_count} active tasks • {emp.available_capacity_hours}h cap
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {emp.current_workload_score}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-emerald-500/5 via-teal-500/5 to-cyan-500/5 dark:from-emerald-950/20 dark:via-teal-950/20 dark:to-cyan-950/10 border-2 border-emerald-500/30 shadow-md space-y-4 text-xs">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-emerald-500/20 pb-3">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 rounded-xl bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
            <UserCheck className="w-4 h-4" />
          </div>
          <div>
            <span className="font-bold block text-xs tracking-wide text-slate-900 dark:text-white flex items-center space-x-1.5">
              <span>Intelligent Employee Recommendation</span>
              <span className="px-2 py-0.2 rounded-full text-[9px] font-mono font-semibold bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/40">
                AI Advisory
              </span>
            </span>
            <span className="text-[10px] text-slate-500 dark:text-slate-400">
              Evaluated via live Trello workload, completion speed & historical task suitability
            </span>
          </div>
        </div>

        <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30 font-mono">
          {Math.round(recommended.suitability_score)}% Match
        </span>
      </div>

      {/* Main Recommended Employee Hero Card */}
      <div className="p-4 rounded-xl bg-white dark:bg-[#0c1424] border border-emerald-500/25 shadow-xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-bold text-sm">
              {recommended.employee_name[0]?.toUpperCase() || 'E'}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-sm text-slate-900 dark:text-slate-100">{recommended.employee_name}</span>
                <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                  {recommended.role}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                {recommended.employee_email || 'Verified Board Member'}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2 self-end sm:self-center">
            <span className="px-2 py-0.5 rounded-lg text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              {recommended.current_workload_score} Workload
            </span>
            <span className="px-2 py-0.5 rounded-lg text-[10px] font-mono font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
              {recommended.available_capacity_hours}h Capacity
            </span>
          </div>
        </div>

        {/* Supporting Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
          <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800">
            <span className="text-[9.5px] text-slate-400 uppercase font-medium flex items-center space-x-1 font-mono">
              <Briefcase className="w-2.5 h-2.5" />
              <span>Current Tasks</span>
            </span>
            <span className="font-bold text-slate-800 dark:text-slate-200 block mt-0.5">
              {recommended.in_progress_count + recommended.assigned_tasks_count} active ({recommended.in_progress_count} in-progress)
            </span>
          </div>

          <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800">
            <span className="text-[9.5px] text-slate-400 uppercase font-medium flex items-center space-x-1 font-mono">
              <CheckCircle className="w-2.5 h-2.5" />
              <span>Completed</span>
            </span>
            <span className="font-bold text-slate-800 dark:text-slate-200 block mt-0.5">
              {recommended.completed_tasks_count} tasks
            </span>
          </div>

          <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800">
            <span className="text-[9.5px] text-slate-400 uppercase font-medium flex items-center space-x-1 font-mono">
              <TrendingUp className="w-2.5 h-2.5" />
              <span>On-Time Rate</span>
            </span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400 block mt-0.5">
              {recommended.has_sufficient_history ? `${Math.round(recommended.on_time_completion_rate)}%` : 'New Member'}
            </span>
          </div>

          <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800">
            <span className="text-[9.5px] text-slate-400 uppercase font-medium flex items-center space-x-1 font-mono">
              <Clock className="w-2.5 h-2.5" />
              <span>Avg Speed</span>
            </span>
            <span className="font-bold text-slate-800 dark:text-slate-200 block mt-0.5">
              {recommended.avg_actual_duration_minutes > 0
                ? `${Math.round(recommended.avg_actual_duration_minutes / 60)}h ${Math.round(recommended.avg_actual_duration_minutes % 60)}m`
                : 'Standard'}
            </span>
          </div>
        </div>

        {/* Similar Experience & Reasoning */}
        <div className="p-2.5 rounded-lg bg-slate-50/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/80 space-y-1">
          <div className="flex items-center space-x-1.5 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold uppercase">
            <Award className="w-3 h-3" />
            <span>Why Recommended:</span>
          </div>
          <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-xs">
            {recommended.recommendation_reason}
          </p>
          <div className="text-[10px] text-slate-500 dark:text-slate-400 font-mono mt-1">
            Similar task experience: <span className="text-slate-700 dark:text-slate-300 font-medium">{recommended.similar_task_experience}</span>
          </div>
        </div>
      </div>

      {/* Alternative Eligible Employees */}
      {alternatives.length > 0 && (
        <div className="space-y-2">
          <span className="text-[10.5px] font-mono font-medium text-slate-500 dark:text-slate-400 uppercase flex items-center space-x-1">
            <Users className="w-3 h-3 text-slate-400" />
            <span>Alternative Suitable Employees:</span>
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {alternatives.map((alt) => (
              <div
                key={alt.employee_id}
                className="p-2.5 rounded-xl bg-white/70 dark:bg-[#0d1424] border border-slate-200 dark:border-slate-800 hover:border-emerald-500/40 transition flex flex-col justify-between space-y-2"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-800 dark:text-slate-200 block truncate">{alt.employee_name}</span>
                    <span className="text-[9px] font-mono text-emerald-600 dark:text-emerald-400 font-bold">
                      {Math.round(alt.suitability_score)}%
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 dark:text-slate-400 block">
                    {alt.in_progress_count + alt.assigned_tasks_count} active tasks • {alt.available_capacity_hours}h cap
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => onSelectAlternative(alt)}
                  disabled={isAssigning}
                  className="w-full py-1 rounded-lg text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 border border-emerald-200 dark:border-emerald-500/30 transition flex items-center justify-center space-x-1"
                >
                  <span>Select {alt.employee_name.split(' ')[0]}</span>
                  <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Manager Decision Action Buttons (Human-in-the-Loop Safe Gate) */}
      <div className="pt-2 border-t border-emerald-500/20 flex items-center justify-between">
        <span className="text-[10px] font-mono text-slate-400 flex items-center space-x-1">
          <ShieldCheck className="w-3 h-3 text-emerald-500" />
          <span>Requires Manager Confirmation before Trello assignment</span>
        </span>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isAssigning}
            className="px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold transition"
          >
            Dismiss
          </button>

          <button
            type="button"
            onClick={() => onAcceptRecommendation(recommended)}
            disabled={isAssigning}
            className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-xs shadow-md flex items-center space-x-1.5 transition disabled:opacity-50"
          >
            <Check className="w-3.5 h-3.5" />
            <span>Assign to {recommended.employee_name.split(' ')[0]}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

