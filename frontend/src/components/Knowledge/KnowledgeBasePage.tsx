import React, { useState, useEffect, useCallback } from 'react';
import { knowledgeApi, KBPair, CreateKBPairRequest, UpdateKBPairRequest } from '../../api/knowledgeApi';
import { AxiosError } from 'axios';
import { Icons } from '../Layout/Icons';

// ---- Create/Edit Modal ----
interface PairModalProps {
  isOpen: boolean;
  pair: KBPair | null; // null = create mode
  onClose: () => void;
  onSaved: () => void;
}

const PairModal: React.FC<PairModalProps> = ({ isOpen, pair, onClose, onSaved }) => {
  const [question, setQuestion] = useState('');
  const [sqlQuery, setSqlQuery] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isEdit = !!pair;

  useEffect(() => {
    if (pair) {
      setQuestion(pair.question);
      setSqlQuery(pair.sql_query);
    } else {
      setQuestion('');
      setSqlQuery('');
    }
    setError('');
  }, [pair, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !sqlQuery.trim()) {
      setError('Both question and SQL query are required');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      if (isEdit && pair) {
        const body: UpdateKBPairRequest = { question: question.trim(), sql_query: sqlQuery.trim() };
        await knowledgeApi.updatePair(pair.id, body);
      } else {
        const body: CreateKBPairRequest = { question: question.trim(), sql_query: sqlQuery.trim() };
        await knowledgeApi.createPair(body);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(axiosErr?.response?.data?.detail || `Failed to ${isEdit ? 'update' : 'create'} pair`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">
            {isEdit ? 'Edit KB Pair' : 'Add KB Pair'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors p-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div className="p-6">
          {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">Question</label>
              <input
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder="e.g. What are the total sales by region?"
                required
                className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">SQL Query</label>
              <textarea
                value={sqlQuery}
                onChange={e => setSqlQuery(e.target.value)}
                placeholder="SELECT region, SUM(amount) FROM sales GROUP BY region"
                required
                rows={6}
                className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 resize-y"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button type="button" onClick={onClose} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 transition-all">
                Cancel
              </button>
              <button type="submit" disabled={submitting} className="flex-1 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all">
                {submitting ? (isEdit ? 'Saving...' : 'Creating...') : (isEdit ? 'Save Changes' : 'Create Pair')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

// ---- Delete Confirmation Modal ----
interface DeleteModalProps {
  isOpen: boolean;
  pairQuestion: string;
  onClose: () => void;
  onConfirm: () => void;
}

const DeleteModal: React.FC<DeleteModalProps> = ({ isOpen, pairQuestion, onClose, onConfirm }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-sm w-full mx-4 overflow-hidden">
        <div className="p-6 text-center">
          <div className="w-14 h-14 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </div>
          <h3 className="text-lg font-black text-slate-900 mb-2">Delete KB Pair</h3>
          <p className="text-sm text-slate-500 mb-1">Are you sure you want to delete this pair?</p>
          <p className="text-xs text-slate-400 mb-6 italic truncate px-4">&quot;{pairQuestion}&quot;</p>
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 px-4 py-3 bg-slate-100 text-slate-700 rounded-xl text-sm font-bold hover:bg-slate-200 transition-colors">
              Cancel
            </button>
            <button onClick={() => { onConfirm(); onClose(); }} className="flex-1 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-bold transition-colors shadow-lg">
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---- Main Component ----
const KnowledgeBasePage: React.FC = () => {
  const [pairs, setPairs] = useState<KBPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editPair, setEditPair] = useState<KBPair | null>(null);
  const [deletePair, setDeletePair] = useState<KBPair | null>(null);

  const fetchPairs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await knowledgeApi.getPairs();
      setPairs(data);
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPairs(); }, [fetchPairs]);

  const handleDelete = async () => {
    if (!deletePair) return;
    try {
      await knowledgeApi.deletePair(deletePair.id);
      fetchPairs();
    } catch {
      // handled by interceptor
    }
  };

  const filteredPairs = pairs.filter(p => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return p.question.toLowerCase().includes(q) || p.sql_query.toLowerCase().includes(q);
  });

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Knowledge Base</h1>
          <p className="text-xs text-slate-500 mt-1">Manage question-SQL pairs to train the AI system</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 transition-all shadow-lg shadow-orange-100 flex items-center gap-2"
        >
          <Icons.Plus /> Add Pair
        </button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative max-w-md">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search questions or SQL..."
            className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin mx-auto" />
        </div>
      ) : filteredPairs.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Icons.BookOpen />
          </div>
          <h2 className="text-lg font-bold text-slate-700 mb-2">
            {search ? 'No matching pairs found' : 'No KB pairs yet'}
          </h2>
          <p className="text-sm text-slate-500 mb-6">
            {search
              ? 'Try a different search term'
              : 'Add question-SQL pairs to train the AI and improve query accuracy.'}
          </p>
          {!search && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-6 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 transition-all"
            >
              Add First Pair
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs text-slate-400 font-bold uppercase tracking-widest mb-2">
            {filteredPairs.length} pair{filteredPairs.length !== 1 ? 's' : ''}{search ? ' found' : ''}
          </div>
          {filteredPairs.map(pair => (
            <div key={pair.id} className="bg-white rounded-2xl border border-slate-200 p-5 hover:border-slate-300 transition-all group">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900 mb-2">{pair.question}</p>
                  <pre className="bg-slate-900 text-slate-100 rounded-xl p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {pair.sql_query}
                  </pre>
                  <div className="flex items-center gap-4 mt-3">
                    {pair.created_at && (
                      <span className="text-[10px] text-slate-400">
                        Created: {new Date(pair.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {pair.updated_at && (
                      <span className="text-[10px] text-slate-400">
                        Updated: {new Date(pair.updated_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <button
                    onClick={() => setEditPair(pair)}
                    className="p-2 text-slate-400 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all"
                    title="Edit pair"
                  >
                    <Icons.Edit />
                  </button>
                  <button
                    onClick={() => setDeletePair(pair)}
                    className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                    title="Delete pair"
                  >
                    <Icons.Trash />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <PairModal
        isOpen={showCreateModal}
        pair={null}
        onClose={() => setShowCreateModal(false)}
        onSaved={fetchPairs}
      />
      <PairModal
        isOpen={!!editPair}
        pair={editPair}
        onClose={() => setEditPair(null)}
        onSaved={fetchPairs}
      />
      <DeleteModal
        isOpen={!!deletePair}
        pairQuestion={deletePair?.question || ''}
        onClose={() => setDeletePair(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
};

export default KnowledgeBasePage;
