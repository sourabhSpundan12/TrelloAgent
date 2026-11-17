import React, { useState, useEffect } from 'react';
import {
  Lock,
  Mail,
  User,
  Building,
  AlertCircle,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  ShieldCheck,
  Zap,
  ArrowRight,
  ArrowLeft,
  Loader2,
  X,
  KeyRound,
  Send,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/common/Button';
import { requestForgotPassword, resetPassword } from '../services/api';

export const AuthPage: React.FC = () => {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup' | 'forgot' | 'reset'>('signin');

  // Sign In form state - strictly empty by default (no automatic pre-fill)
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  // Sign Up form state - strictly empty by default
  const [regFullName, setRegFullName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regDepartment, setRegDepartment] = useState('Engineering');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);

  // Forgot / Reset Password state
  const [forgotEmail, setForgotEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [resetConfirmPassword, setResetConfirmPassword] = useState('');
  const [showResetPassword, setShowResetPassword] = useState(false);

  // Status and feedback
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Auto-dismiss floating error toast after 5 seconds
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => {
      setToastMessage(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = loginEmail.trim();
    if (!cleanEmail || !loginPassword) {
      const msg = 'Please enter both email and password.';
      setErrorMessage(msg);
      setToastMessage(msg);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setToastMessage(null);
    setSuccessMessage(null);

    try {
      await login({ email: cleanEmail, password: loginPassword });
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
      setIsSubmitting(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = regFullName.trim();
    const cleanEmail = regEmail.trim();

    if (!cleanName || !cleanEmail || !regPassword) {
      const msg = 'Please fill in all required fields.';
      setErrorMessage(msg);
      setToastMessage(msg);
      return;
    }

    if (regPassword.length < 8) {
      const msg = 'Password must be at least 8 characters long.';
      setErrorMessage(msg);
      setToastMessage(msg);
      return;
    }

    if (regPassword !== regConfirmPassword) {
      const msg = 'Passwords do not match. Please re-enter your password.';
      setErrorMessage(msg);
      setToastMessage(msg);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setToastMessage(null);
    setSuccessMessage(null);

    try {
      await register({
        full_name: cleanName,
        email: cleanEmail,
        department: regDepartment,
        password: regPassword,
      });
      setSuccessMessage('Account created successfully! Signing you in...');
    } catch (err: any) {
      const msg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        err.message ||
        'Sign up failed. That email might already be in use.';
      setErrorMessage(msg);
      setToastMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleForgotPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = forgotEmail.trim();
    if (!cleanEmail) {
      setErrorMessage('Please enter your email address.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setToastMessage(null);
    setSuccessMessage(null);

    try {
      const res = await requestForgotPassword({ email: cleanEmail });
      setSuccessMessage(res.message || 'Verification code sent to your email.');
      setMode('reset');
    } catch (err: any) {
      const msg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        err.message ||
        'Failed to process password reset request.';
      setErrorMessage(msg);
      setToastMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = forgotEmail.trim();
    const cleanCode = resetCode.trim();

    if (!cleanEmail || !cleanCode || !resetNewPassword) {
      setErrorMessage('Please fill in all required fields.');
      return;
    }

    if (resetNewPassword.length < 8) {
      setErrorMessage('New password must be at least 8 characters long.');
      return;
    }

    if (resetNewPassword !== resetConfirmPassword) {
      setErrorMessage('Passwords do not match. Please re-enter your password.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setToastMessage(null);
    setSuccessMessage(null);

    try {
      const res = await resetPassword({
        email: cleanEmail,
        code: cleanCode,
        new_password: resetNewPassword,
      });
      setSuccessMessage(res.message || 'Password reset successfully! Please sign in with your new password.');
      setLoginEmail(cleanEmail);
      setLoginPassword('');
      setResetCode('');
      setResetNewPassword('');
      setResetConfirmPassword('');
      setMode('signin');
    } catch (err: any) {
      const msg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        err.message ||
        'Failed to reset password. Please check your verification code.';
      setErrorMessage(msg);
      setToastMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const switchMode = (newMode: 'signin' | 'signup' | 'forgot' | 'reset') => {
    setMode(newMode);
    setErrorMessage(null);
    setToastMessage(null);
    setSuccessMessage(null);
  };

  return (
    <div className="min-h-screen w-full flex flex-col justify-center items-center p-4 sm:p-6 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors relative">
      {/* Floating Error Toast Notification */}
      {toastMessage && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 flex items-center space-x-3 px-4 py-3 bg-rose-600 text-white rounded-2xl shadow-2xl border border-rose-500 animate-in fade-in slide-in-from-top-4 duration-200 max-w-sm sm:max-w-md">
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

      {/* Background Decorative Ambient Elements */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden flex items-center justify-center opacity-40 dark:opacity-25">
        <div className="w-[500px] h-[500px] bg-brand-500/20 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/4" />
        <div className="w-[450px] h-[450px] bg-purple-500/20 rounded-full blur-[120px] translate-x-1/2 translate-y-1/4" />
      </div>

      <div className="relative w-full max-w-md space-y-6 z-10">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex p-3 rounded-2xl bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20 shadow-md">
            <Cpu className="w-8 h-8" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Agentic Task Manager
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
            Autonomous AI Agent & Trello MCP Orchestration Platform
          </p>
        </div>

        {/* Auth Card */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/90 dark:border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl shadow-slate-200/50 dark:shadow-none space-y-6">
          {/* Mode Switch Tabs or Back Link */}
          {mode === 'signin' || mode === 'signup' ? (
            <div className="grid grid-cols-2 p-1 bg-slate-100 dark:bg-slate-800/80 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 text-xs font-semibold">
              <button
                type="button"
                onClick={() => switchMode('signin')}
                className={`py-2.5 rounded-xl transition ${
                  mode === 'signin'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs font-bold'
                    : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => switchMode('signup')}
                className={`py-2.5 rounded-xl transition ${
                  mode === 'signup'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs font-bold'
                    : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                Sign Up
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between pb-1 border-b border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => switchMode('signin')}
                className="inline-flex items-center space-x-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Sign In</span>
              </button>
              <span className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wider">
                Password Reset
              </span>
            </div>
          )}

          {/* Feedback Alerts */}
          {errorMessage && (
            <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/25 text-rose-700 dark:text-rose-400 text-xs flex items-start space-x-2.5 animate-fadeIn">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span className="flex-1 font-medium">{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/25 text-emerald-800 dark:text-emerald-300 text-xs flex items-start space-x-2.5 animate-fadeIn">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span className="flex-1 font-medium">{successMessage}</span>
            </div>
          )}

          {/* SIGN IN FORM */}
          {mode === 'signin' && (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Email Address
                </label>
                <div className="relative flex items-center">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="name@company.com"
                    autoComplete="email"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setForgotEmail(loginEmail);
                      switchMode('forgot');
                    }}
                    className="text-xs text-brand-600 dark:text-brand-400 hover:underline font-medium"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative flex items-center">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type={showLoginPassword ? 'text' : 'password'}
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="••••••••••••"
                    autoComplete="current-password"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowLoginPassword(!showLoginPassword)}
                    className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                    tabIndex={-1}
                  >
                    {showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center space-x-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="rounded border-slate-300 dark:border-slate-700 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-xs text-slate-600 dark:text-slate-400">Remember this device</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs shadow-md shadow-brand-500/25 flex items-center justify-center space-x-2 transition active:scale-[0.99] disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Signing in...</span>
                  </>
                ) : (
                  <>
                    <span>Sign In</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>

              <div className="text-center pt-2">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Don&apos;t have an account?{' '}
                  <button
                    type="button"
                    onClick={() => switchMode('signup')}
                    className="font-semibold text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Sign Up
                  </button>
                </p>
              </div>
            </form>
          )}

          {/* SIGN UP FORM */}
          {mode === 'signup' && (
            <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Full Name
                </label>
                <div className="relative flex items-center">
                  <User className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type="text"
                    required
                    value={regFullName}
                    onChange={(e) => setRegFullName(e.target.value)}
                    placeholder="Jane Doe"
                    autoComplete="name"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Work Email Address
                </label>
                <div className="relative flex items-center">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type="email"
                    required
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="jane@company.com"
                    autoComplete="email"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Department
                </label>
                <div className="relative flex items-center">
                  <Building className="w-4 h-4 text-slate-400 absolute left-3.5 pointer-events-none" />
                  <select
                    value={regDepartment}
                    onChange={(e) => setRegDepartment(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  >
                    <option value="Engineering">Engineering</option>
                    <option value="Product">Product</option>
                    <option value="Operations">Operations</option>
                    <option value="Marketing">Marketing</option>
                    <option value="Design">Design</option>
                    <option value="Human Resources">Human Resources</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Password
                </label>
                <div className="relative flex items-center">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type={showRegPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    autoComplete="new-password"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowRegPassword(!showRegPassword)}
                    className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                    tabIndex={-1}
                  >
                    {showRegPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Confirm Password
                </label>
                <div className="relative flex items-center">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type={showRegPassword ? 'text' : 'password'}
                    required
                    value={regConfirmPassword}
                    onChange={(e) => setRegConfirmPassword(e.target.value)}
                    placeholder="Repeat password"
                    autoComplete="new-password"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-3 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs shadow-md shadow-brand-500/25 flex items-center justify-center space-x-2 transition active:scale-[0.99] disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Signing up...</span>
                  </>
                ) : (
                  <>
                    <span>Sign Up</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>

              <div className="text-center pt-2 space-y-1">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => switchMode('signin')}
                    className="font-semibold text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Sign In
                  </button>
                </p>
                <p className="text-[11px] text-slate-400">
                  Forgot credentials?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setForgotEmail(regEmail);
                      switchMode('forgot');
                    }}
                    className="text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Reset Password
                  </button>
                </p>
              </div>
            </form>
          )}

          {/* FORGOT PASSWORD FORM (STEP 1: Request Code via SMTP) */}
          {mode === 'forgot' && (
            <form onSubmit={handleForgotPasswordSubmit} className="space-y-4">
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">Forgot Password?</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  Enter your registered work email address below. We will send a 6-digit verification code to your inbox via SMTP.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Registered Email Address
                </label>
                <div className="relative flex items-center">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type="email"
                    required
                    value={forgotEmail}
                    onChange={(e) => setForgotEmail(e.target.value)}
                    placeholder="name@company.com"
                    autoComplete="email"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs shadow-md shadow-brand-500/25 flex items-center justify-center space-x-2 transition active:scale-[0.99] disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Sending code via SMTP...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Send Verification Code</span>
                  </>
                )}
              </button>

              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="text-xs font-semibold text-slate-500 hover:text-slate-900 dark:hover:text-slate-200 transition"
                >
                  Cancel and return to Sign In
                </button>
              </div>
            </form>
          )}

          {/* RESET PASSWORD FORM (STEP 2: Enter Code & New Password) */}
          {mode === 'reset' && (
            <form onSubmit={handleResetPasswordSubmit} className="space-y-3.5">
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">Verify Code & Reset Password</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  Enter the 6-digit verification code sent to <strong className="text-slate-700 dark:text-slate-200">{forgotEmail}</strong> along with your new password.
                </p>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  6-Digit Verification Code
                </label>
                <div className="relative flex items-center">
                  <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type="text"
                    required
                    maxLength={10}
                    value={resetCode}
                    onChange={(e) => setResetCode(e.target.value)}
                    placeholder="123456"
                    className="w-full font-mono tracking-widest text-center bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl py-2.5 text-sm font-bold text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  New Password
                </label>
                <div className="relative flex items-center">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type={showResetPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={resetNewPassword}
                    onChange={(e) => setResetNewPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    autoComplete="new-password"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowResetPassword(!showResetPassword)}
                    className="absolute right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
                    tabIndex={-1}
                  >
                    {showResetPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold tracking-wider text-slate-700 dark:text-slate-300 uppercase block">
                  Confirm New Password
                </label>
                <div className="relative flex items-center">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5" />
                  <input
                    type={showResetPassword ? 'text' : 'password'}
                    required
                    value={resetConfirmPassword}
                    onChange={(e) => setResetConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                    autoComplete="new-password"
                    className="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/20 transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-3 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs shadow-md shadow-brand-500/25 flex items-center justify-center space-x-2 transition active:scale-[0.99] disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Resetting password...</span>
                  </>
                ) : (
                  <>
                    <KeyRound className="w-4 h-4" />
                    <span>Set New Password</span>
                  </>
                )}
              </button>

              <div className="flex items-center justify-between pt-2 text-xs">
                <button
                  type="button"
                  onClick={() => handleForgotPasswordSubmit({ preventDefault: () => {} } as any)}
                  disabled={isSubmitting}
                  className="text-brand-600 dark:text-brand-400 hover:underline"
                >
                  Resend code
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="text-slate-500 hover:text-slate-900 dark:hover:text-slate-200 transition"
                >
                  Back to Sign In
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Product Trust Features Footer */}
        <div className="grid grid-cols-3 gap-2 pt-2 text-center text-[10px] text-slate-500 dark:text-slate-400">
          <div className="flex flex-col items-center p-2 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60">
            <ShieldCheck className="w-3.5 h-3.5 text-brand-500 mb-1" />
            <span className="font-semibold">Argon2 & JWT</span>
            <span>Enterprise Security</span>
          </div>
          <div className="flex flex-col items-center p-2 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60">
            <Zap className="w-3.5 h-3.5 text-brand-500 mb-1" />
            <span className="font-semibold">Trello MCP</span>
            <span>Live Workspace Sync</span>
          </div>
          <div className="flex flex-col items-center p-2 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60">
            <Cpu className="w-3.5 h-3.5 text-brand-500 mb-1" />
            <span className="font-semibold">AI Assistant</span>
            <span>Safe Mutation Gate</span>
          </div>
        </div>
      </div>
    </div>
  );
};

