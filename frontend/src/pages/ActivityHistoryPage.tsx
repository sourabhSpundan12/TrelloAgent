import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Search,
  PlusCircle,
  Edit3,
  MoveRight,
  CheckCircle,
  Clock,
  ExternalLink,
  ShieldAlert,
  XCircle,
  RefreshCw,
  User,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { DemoBanner } from '../components/common/DemoBanner';
import { EmptyState } from '../components/common/EmptyState';
import { useAuth } from '../context/AuthContext';
import { fetchLiveActivities } from '../services/api';

export const ActivityHistoryPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [activities, setActivities] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');

  const loadActivities = async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    try {
      const data = await fetchLiveActivities();
      if (data && data.status === 'SUCCESS') {
        setActivities(data.activities || []);
      }
    } catch (err) {
      console.error('Failed to load live activities:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadActivities();
  }, [isAuthenticated]);

  const filteredActivities = useMemo(() => {
    return activities.filter((act) => {
      const matchesSearch =
        !searchQuery ||
        (act.title && act.title.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (act.action_id && act.action_id.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (act.tool_name && act.tool_name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (act.user_email && act.user_email.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesStatus = selectedStatus === 'ALL' || act.status === selectedStatus;

      return matchesSearch && matchesStatus;
    });
  }, [activities, searchQuery, selectedStatus]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'EXECUTED':
        return <CheckCircle className="w-4 h-4 text-emerald-500" />;
      case 'PENDING':
        return <ShieldAlert className="w-4 h-4 text-amber-500" />;
      case 'REJECTED':
        return <XCircle className="w-4 h-4 text-rose-500" />;
      default:
        return <History className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <DemoBanner
        mode="live"
        message="Live Audit Trail: Real-time action log stored in MongoDB Atlas pending_actions. Displays all conversational tool intents, human approvals, and MCP executions."
      />

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search audit trail by title, action ID, user, or tool..."
            className="w-full bg-slate-100 dark:bg-slate-800 border border-transparent dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 transition"
          />
        </div>

        <div className="flex items-center space-x-2">
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-700 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition"
          >
            <option value="ALL">All Statuses ({activities.length})</option>
            <option value="EXECUTED">Executed</option>
            <option value="PENDING">Pending Approval</option>
            <option value="REJECTED">Cancelled / Rejected</option>
          </select>

          <Button
            variant="outline"
            size="sm"
            onClick={loadActivities}
            disabled={isLoading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSearchQuery('');
              setSelectedStatus('ALL');
            }}
          >
            Clear
          </Button>
        </div>
      </Card>

      {/* Timeline View */}
      <Card className="p-6">
        {filteredActivities.length === 0 ? (
          <EmptyState
            title="No activity records found"
            description={
              activities.length === 0
                ? "No audit records in MongoDB Atlas yet. Actions performed via the AI Assistant chat will automatically appear here."
                : "No events match your current filter criteria."
            }
            actionLabel="Refresh Activities"
            onAction={loadActivities}
          />
        ) : (
          <div className="relative pl-6 space-y-8 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-800">
            {filteredActivities.map((act) => (
              <div key={act.id} className="relative flex items-start space-x-4 text-xs group">
                {/* Event Marker Node */}
                <div className="absolute -left-6 mt-1 p-1 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 ring-4 ring-white dark:ring-slate-900 shrink-0">
                  {getStatusIcon(act.status)}
                </div>

                {/* Event Content Container */}
                <div className="flex-1 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 space-y-2 hover:border-slate-300 dark:hover:border-slate-700 transition">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-500">
                        <User className="w-3 h-3" />
                      </div>
                      <span className="font-semibold text-slate-900 dark:text-slate-100">
                        {act.user_email || 'Authenticated User'}
                      </span>
                      <span className="text-slate-400">•</span>
                      <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                        {act.tool_name}
                      </span>
                    </div>

                    <div className="flex items-center space-x-2 text-[11px] text-slate-400 font-mono">
                      <Clock className="w-3 h-3" />
                      <span>{new Date(act.created_at).toLocaleString()}</span>
                    </div>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-slate-800 dark:text-slate-200 font-semibold text-xs">
                        {act.title}
                      </p>
                      {act.description && (
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
                          {act.description}
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={
                        act.status === 'EXECUTED'
                          ? 'success'
                          : act.status === 'REJECTED'
                          ? 'danger'
                          : 'warning'
                      }
                    >
                      {act.status}
                    </Badge>
                  </div>

                  <div className="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-200/60 dark:border-slate-800">
                    <span className="font-mono">Action ID: {act.action_id}</span>
                    {act.card_url && (
                      <a
                        href={act.card_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center space-x-1 text-brand-600 hover:underline font-semibold"
                      >
                        <span>View in Trello</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
