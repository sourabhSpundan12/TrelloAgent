import React, { useState, useEffect } from 'react';
import { Lock, Mail, AlertCircle, Loader2, X } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { useAuth } from '../../context/AuthContext';

export const LoginModal: React.FC = () => {
  const { loginModalOpen, closeLoginModal, login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Auto-dismiss floating toast after 5 seconds
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => {
      setToastMessage(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail || !password || loading) {
      const msg = 'Please enter both email and password.';
      setErrorMessage(msg);
      setToastMessage(msg);
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setToastMessage(null);

    try {
      await login({ email: cleanEmail, password });
      closeLoginModal();
    } catch (err: any) {
      const status = err.response?.status;
      const backendMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail;

      let msg = 'Email and password is incorrect.';
      if (
        status === 401 ||
        (backendMsg &&
          (backendMsg.toLowerCase().includes('password') ||
            backendMsg.toLowerCase().includes('email') ||
            backendMsg.toLowerCase().includes('authentication') ||
            backendMsg.toLowerCase().includes('credential') ||
            backendMsg.toLowerCase().includes('incorrect') ||
            backendMsg.toLowerCase().includes('invalid')))
      ) {
        msg = 'Email and password is incorrect.';
      } else if (backendMsg) {
        msg = backendMsg;
      }
      setErrorMessage(msg);
      setToastMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {toastMessage && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[9999] flex items-center space-x-3 px-4 py-3 bg-rose-600 text-white rounded-2xl shadow-2xl border border-rose-500 animate-in fade-in slide-in-from-top-4 duration-200 max-w-sm sm:max-w-md">
          <AlertCircle className="w-5 h-5 shrink-0 text-white" />
          <p className="text-xs sm:text-sm font-semibold tracking-wide flex-1">{toastMessage}</p>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="p-1 text-white/80 hover:text-white rounded-lg hover:bg-rose-700/50 transition"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      <Modal
        isOpen={loginModalOpen}
        onClose={closeLoginModal}
        title="Platform Sign In"
        subtitle="Authenticate with your credentials to unlock live AI requests and Trello MCP actions"
        maxWidth="md"
      >
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-rose-700 dark:text-rose-400 flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 block uppercase">
              Email Address
            </label>
            <div className="relative flex items-center">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 block uppercase">
              Password
            </label>
            <div className="relative flex items-center">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500"
              />
            </div>
          </div>

          <div className="pt-3 flex items-center justify-end space-x-2 border-t border-slate-100 dark:border-slate-800">
            <Button variant="ghost" size="sm" type="button" onClick={closeLoginModal}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={loading}
              icon={loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : undefined}
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};

