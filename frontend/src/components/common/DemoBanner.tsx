import React from 'react';
import { Sparkles, Radio } from 'lucide-react';

interface DemoBannerProps {
  message?: string;
  className?: string;
  mode?: 'demo' | 'live';
}

export const DemoBanner: React.FC<DemoBannerProps> = ({
  message = 'Demonstration Data: Phase 2 frontend foundation preview. Backend orchestration & live database mutations will be integrated in subsequent phases.',
  className = '',
  mode = 'demo',
}) => {
  const isLive = mode === 'live';
  return (
    <div
      className={`p-3.5 ${isLive
        ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-300'
        : 'bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300'
        } rounded-xl text-xs flex items-center justify-between ${className}`}
    >
      <div className="flex items-center space-x-2.5">
        {isLive ? (
          <Radio className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 animate-pulse" />
        ) : (
          <Sparkles className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
        )}
        <span className="font-medium">{message}</span>
      </div>
      <span
        className={`hidden sm:inline-flex px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase ${isLive
          ? 'bg-emerald-500/20 text-emerald-900 dark:text-emerald-200'
          : 'bg-amber-500/20 text-amber-900 dark:text-amber-200'
          }`}
      >
        {isLive ? 'Live Mode' : 'Demo Mode'}
      </span>
    </div>
  );
};
