import React, { useState, useEffect, useMemo } from 'react';
import {
  FileText,
  Plus,
  Trash2,
  Edit3,
  Search,
  Sparkles,
  Lock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Tag,
  Layers,
  HelpCircle,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '../common/Card';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';
import { TaskTemplate } from '../../types';
import {
  fetchTaskTemplates,
  createTaskTemplate,
  updateTaskTemplate,
  deleteTaskTemplate,
} from '../../services/api';

interface TaskTemplatesManagerProps {
  className?: string;
}

export const TaskTemplatesManager: React.FC<TaskTemplatesManagerProps> = ({ className = '' }) => {
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  // Modal form state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('CUSTOM');
  const [keywordsInput, setKeywordsInput] = useState('');
  const [descriptionTemplate, setDescriptionTemplate] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete confirmation
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Feedback Toast
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadTemplates = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await fetchTaskTemplates();
      setTemplates(res.templates || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load task templates.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), 4000);
    return () => clearTimeout(timer);
  }, [feedback]);

  const openCreateModal = () => {
    setModalMode('create');
    setEditingId(null);
    setName('');
    setCategory('CUSTOM');
    setKeywordsInput('');
    setDescriptionTemplate(
      "Implement and test deliverables for '{title}'. Ensure code quality, comprehensive test coverage, and smooth integration."
    );
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (tmpl: TaskTemplate) => {
    if (tmpl.is_builtin) return;
    setModalMode('edit');
    setEditingId(tmpl.id);
    setName(tmpl.name);
    setCategory(tmpl.category);
    setKeywordsInput(tmpl.keywords.join(', '));
    setDescriptionTemplate(tmpl.description_template);
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError('Please enter a template name.');
      return;
    }

    const keywords = keywordsInput
      .split(/[,;\n]+/)
      .map((k) => k.trim().toLowerCase())
      .filter(Boolean);

    if (keywords.length === 0) {
      setFormError('Please provide at least one trigger keyword.');
      return;
    }

    const trimmedDesc = descriptionTemplate.trim();
    if (!trimmedDesc) {
      setFormError('Please provide a description template text.');
      return;
    }

    try {
      setIsSubmitting(true);
      if (modalMode === 'create') {
        const res = await createTaskTemplate({
          name: trimmedName,
          category: category.trim().toUpperCase() || 'CUSTOM',
          keywords,
          description_template: trimmedDesc,
        });
        setTemplates((prev) => [res.template, ...prev]);
        setFeedback({ type: 'success', text: `Template "${trimmedName}" created successfully!` });
      } else if (modalMode === 'edit' && editingId) {
        const res = await updateTaskTemplate(editingId, {
          name: trimmedName,
          category: category.trim().toUpperCase() || 'CUSTOM',
          keywords,
          description_template: trimmedDesc,
        });
        setTemplates((prev) => prev.map((t) => (t.id === editingId ? res.template : t)));
        setFeedback({ type: 'success', text: `Template "${trimmedName}" updated successfully!` });
      }
      setIsModalOpen(false);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || err.message || 'Failed to save template.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      setIsDeleting(true);
      await deleteTaskTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      setDeleteId(null);
      setFeedback({ type: 'success', text: 'Custom template deleted successfully.' });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        text: err?.response?.data?.detail || err.message || 'Failed to delete template.',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  // Filter categories
  const categories = useMemo(() => {
    const set = new Set<string>();
    templates.forEach((t) => {
      if (t.category) set.add(t.category);
    });
    return Array.from(set).sort();
  }, [templates]);

  // Filtered templates
  const filteredTemplates = useMemo(() => {
    return templates.filter((t) => {
      // Category filter
      if (selectedCategory === 'BUILTIN' && !t.is_builtin) return false;
      if (selectedCategory === 'CUSTOM' && t.is_builtin) return false;
      if (
        selectedCategory !== 'ALL' &&
        selectedCategory !== 'BUILTIN' &&
        selectedCategory !== 'CUSTOM' &&
        t.category !== selectedCategory
      ) {
        return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = t.name.toLowerCase().includes(q);
        const matchesCategory = t.category.toLowerCase().includes(q);
        const matchesDesc = t.description_template.toLowerCase().includes(q);
        const matchesKeywords = t.keywords.some((k) => k.toLowerCase().includes(q));
        return matchesName || matchesCategory || matchesDesc || matchesKeywords;
      }

      return true;
    });
  }, [templates, selectedCategory, searchQuery]);

  const customCount = templates.filter((t) => !t.is_builtin).length;
  const builtinCount = templates.filter((t) => t.is_builtin).length;

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Toast Feedback */}
      {feedback && (
        <div
          className={`flex items-center space-x-2 p-3 rounded-xl text-xs font-medium animate-in fade-in duration-200 ${
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
          <span className="flex-1">{feedback.text}</span>
        </div>
      )}

      {/* Main Card */}
      <Card>
        <CardHeader
          title={
            <div className="flex items-center space-x-2">
              <FileText className="w-5 h-5 text-brand-600 dark:text-brand-400" />
              <span>Task Description Templates</span>
            </div>
          }
          subtitle="Configure intelligent domain-aware description templates. Matching keywords dynamically populate card descriptions in AI commands and task drafts without wasting LLM tokens."
          action={
            <Button
              variant="primary"
              size="sm"
              onClick={openCreateModal}
              className="flex items-center space-x-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>New Template</span>
            </Button>
          }
        />
        <CardContent className="space-y-4">
          {/* Quick Stats & Explanation */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-500 dark:text-slate-400 font-medium">Total Templates</p>
                <p className="text-lg font-bold text-slate-800 dark:text-slate-100 mt-0.5">
                  {templates.length}
                </p>
              </div>
              <div className="p-2.5 rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                <Layers className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-500 dark:text-slate-400 font-medium">Built-in Defaults</p>
                <p className="text-lg font-bold text-slate-800 dark:text-slate-100 mt-0.5">
                  {builtinCount}
                </p>
              </div>
              <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                <Lock className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-500 dark:text-slate-400 font-medium">Custom User Templates</p>
                <p className="text-lg font-bold text-slate-800 dark:text-slate-100 mt-0.5">
                  {customCount}
                </p>
              </div>
              <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <Sparkles className="w-5 h-5" />
              </div>
            </div>
          </div>

          {/* Search Bar & Category Filter Pills */}
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
            {/* Search Input */}
            <div className="relative w-full sm:w-72">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search templates or keywords..."
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500"
              />
            </div>

            {/* Filter Pills */}
            <div className="flex flex-wrap items-center gap-1.5 w-full sm:w-auto">
              <button
                type="button"
                onClick={() => setSelectedCategory('ALL')}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                  selectedCategory === 'ALL'
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                All ({templates.length})
              </button>
              <button
                type="button"
                onClick={() => setSelectedCategory('CUSTOM')}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                  selectedCategory === 'CUSTOM'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                Custom ({customCount})
              </button>
              <button
                type="button"
                onClick={() => setSelectedCategory('BUILTIN')}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                  selectedCategory === 'BUILTIN'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                Built-in ({builtinCount})
              </button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                    selectedCategory === cat
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Loading / Error / Empty States */}
          {isLoading && (
            <div className="py-12 flex flex-col items-center justify-center space-y-2 text-slate-500 text-xs">
              <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
              <span>Loading task description templates...</span>
            </div>
          )}

          {error && !isLoading && (
            <div className="p-4 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
              <Button size="sm" variant="outline" onClick={loadTemplates}>
                Retry
              </Button>
            </div>
          )}

          {!isLoading && !error && filteredTemplates.length === 0 && (
            <div className="py-10 text-center space-y-3 border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl">
              <FileText className="w-8 h-8 text-slate-400 mx-auto" />
              <div>
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  No templates match your criteria
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Try adjusting your search query or create a new custom template.
                </p>
              </div>
              <Button size="sm" variant="primary" onClick={openCreateModal}>
                <Plus className="w-4 h-4 mr-1" /> Create Template
              </Button>
            </div>
          )}

          {/* Templates Grid */}
          {!isLoading && !error && filteredTemplates.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredTemplates.map((tmpl) => (
                <div
                  key={tmpl.id}
                  className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 hover:border-slate-300 dark:hover:border-slate-700 transition flex flex-col justify-between space-y-3"
                >
                  <div className="space-y-2">
                    {/* Top Row: Category Badge & Built-in indicator / Action buttons */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                        <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                          {tmpl.name}
                        </span>
                        <Badge
                          variant={
                            tmpl.category === 'SECURITY'
                              ? 'danger'
                              : tmpl.category === 'BACKEND'
                              ? 'purple'
                              : tmpl.category === 'FRONTEND'
                              ? 'info'
                              : tmpl.category === 'DATABASE'
                              ? 'warning'
                              : tmpl.category === 'QA'
                              ? 'success'
                              : 'default'
                          }
                        >
                          {tmpl.category}
                        </Badge>
                        {tmpl.is_builtin ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                            <Lock className="w-2.5 h-2.5" />
                            <span>Built-in</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                            <Sparkles className="w-2.5 h-2.5" />
                            <span>Custom</span>
                          </span>
                        )}
                      </div>

                      {/* Action buttons for custom templates */}
                      {!tmpl.is_builtin && (
                        <div className="flex items-center space-x-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => openEditModal(tmpl)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-brand-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                            title="Edit template"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteId(tmpl.id)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition"
                            title="Delete template"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Trigger Keywords */}
                    <div className="flex items-center flex-wrap gap-1">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mr-1 flex items-center">
                        <Tag className="w-2.5 h-2.5 mr-0.5" /> Keywords:
                      </span>
                      {tmpl.keywords.map((kw) => (
                        <span
                          key={kw}
                          className="px-1.5 py-0.5 rounded-md text-[11px] font-mono bg-slate-100 dark:bg-slate-800/80 text-slate-700 dark:text-slate-300 border border-slate-200/60 dark:border-slate-700/60"
                        >
                          #{kw}
                        </span>
                      ))}
                    </div>

                    {/* Template Description Body Preview */}
                    <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-[11.5px] leading-relaxed text-slate-700 dark:text-slate-300 font-sans">
                      {tmpl.description_template.split('{title}').map((part, idx, arr) => (
                        <React.Fragment key={idx}>
                          {part}
                          {idx < arr.length - 1 && (
                            <span className="px-1 py-0.5 mx-0.5 font-mono text-[10.5px] font-semibold rounded bg-brand-500/15 text-brand-700 dark:text-brand-300 border border-brand-500/30">
                              {'{title}'}
                            </span>
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                  </div>

                  {/* Card Footer: Metadata info */}
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[10.5px] text-slate-400">
                    <span className="font-mono">ID: {tmpl.id}</span>
                    <span>
                      {tmpl.is_builtin
                        ? 'Active System Rule'
                        : `Custom Rule${tmpl.created_by_email ? ` • ${tmpl.created_by_email}` : ''}`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal: Create or Edit Template */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => !isSubmitting && setIsModalOpen(false)}
        title={modalMode === 'create' ? 'Create Task Template' : 'Edit Task Template'}
        subtitle={
          modalMode === 'create'
            ? 'Define trigger keywords and domain description format for newly drafted cards'
            : 'Update keywords or description text for this custom template'
        }
        maxWidth="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {formError && (
            <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{formError}</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Template Name *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Payment Gateway, Mobile UI"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
            </div>

            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Category
              </label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. PAYMENT, SECURITY, INTEGRATION"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 uppercase focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
              Trigger Keywords * (Comma-separated)
            </label>
            <input
              type="text"
              required
              value={keywordsInput}
              onChange={(e) => setKeywordsInput(e.target.value)}
              placeholder="e.g. stripe, payment, razorpay, checkout, invoice"
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 font-mono text-xs"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Whenever a task title contains any of these words, this template automatically populates the card description.
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-slate-700 dark:text-slate-300 font-semibold">
                Description Template *
              </label>
              <span className="text-[11px] text-slate-400 font-mono">
                Use <code className="text-brand-600 dark:text-brand-400">{'{title}'}</code> placeholder
              </span>
            </div>
            <textarea
              required
              rows={4}
              value={descriptionTemplate}
              onChange={(e) => setDescriptionTemplate(e.target.value)}
              placeholder="e.g. Integrate secure checkout and payment processing for '{title}'. Validate webhook signatures..."
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 font-sans leading-relaxed text-xs"
            />
          </div>

          {/* Live Preview */}
          <div className="p-3 bg-brand-50/40 dark:bg-brand-950/20 rounded-xl border border-brand-200/50 dark:border-brand-800/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-brand-700 dark:text-brand-300 font-semibold">
              <span className="flex items-center space-x-1">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Live Preview with Title &ldquo;{name || 'SampleTask'}&rdquo;</span>
              </span>
            </div>
            <p className="text-[11.5px] leading-relaxed text-slate-700 dark:text-slate-300 italic">
              &ldquo;
              {descriptionTemplate.replace('{title}', name || 'SampleTask') || 'Your description preview will appear here.'}
              &rdquo;
            </p>
          </div>

          {/* Action Buttons */}
          <div className="pt-2 flex items-center justify-end space-x-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={() => setIsModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSubmitting}
              className="flex items-center space-x-1.5"
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
              <span>{modalMode === 'create' ? 'Create Template' : 'Save Changes'}</span>
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteId}
        onClose={() => !isDeleting && setDeleteId(null)}
        title="Delete Custom Template"
        maxWidth="sm"
      >
        <div className="space-y-4 text-xs">
          <p className="text-slate-600 dark:text-slate-300">
            Are you sure you want to delete this custom template? Built-in fallback templates will resume for its keywords.
          </p>
          <div className="flex items-center justify-end space-x-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isDeleting}
              onClick={() => setDeleteId(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={isDeleting}
              onClick={() => deleteId && handleDelete(deleteId)}
              className="flex items-center space-x-1"
            >
              {isDeleting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
              <span>Delete Template</span>
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
