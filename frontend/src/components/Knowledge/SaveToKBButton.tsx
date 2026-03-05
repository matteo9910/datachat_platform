import React, { useState } from 'react';
import { knowledgeApi } from '../../api/knowledgeApi';
import { useAuth } from '../../contexts/AuthContext';
import { Icons } from '../Layout/Icons';
import { AxiosError } from 'axios';

interface SaveToKBButtonProps {
  question: string;
  sql: string;
}

const SaveToKBButton: React.FC<SaveToKBButtonProps> = ({ question, sql }) => {
  const { hasRole } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [editQuestion, setEditQuestion] = useState('');
  const [editSql, setEditSql] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  // Only show for admin/analyst roles
  if (!hasRole(['admin', 'analyst'])) return null;

  const handleOpen = () => {
    setEditQuestion(question);
    setEditSql(sql);
    setError('');
    setSaved(false);
    setIsOpen(true);
  };

  const handleSave = async () => {
    if (!editQuestion.trim() || !editSql.trim()) {
      setError('Both question and SQL are required');
      return;
    }
    setError('');
    setSaving(true);
    try {
      await knowledgeApi.createPair({
        question: editQuestion.trim(),
        sql_query: editSql.trim(),
      });
      setSaved(true);
      setTimeout(() => setIsOpen(false), 1200);
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(axiosErr?.response?.data?.detail || 'Failed to save to Knowledge Base');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="p-1.5 text-slate-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-all"
        title="Save to Knowledge Base"
      >
        <Icons.BookOpen />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={() => setIsOpen(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">
                Save to Knowledge Base
              </h3>
              <button onClick={() => setIsOpen(false)} className="text-slate-400 hover:text-slate-600 transition-colors p-1">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div className="p-6">
              {saved ? (
                <div className="text-center py-8">
                  <div className="w-14 h-14 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Icons.Check />
                  </div>
                  <p className="text-sm font-bold text-slate-900">Saved to Knowledge Base!</p>
                  <p className="text-xs text-slate-500 mt-1">This pair will improve future AI responses.</p>
                </div>
              ) : (
                <>
                  {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>}
                  <p className="text-xs text-slate-500 mb-4">
                    Save this question-SQL pair to the Knowledge Base to train the AI system. You can edit both fields before saving.
                  </p>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">Question</label>
                      <input
                        value={editQuestion}
                        onChange={e => setEditQuestion(e.target.value)}
                        className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">SQL Query</label>
                      <textarea
                        value={editSql}
                        onChange={e => setEditSql(e.target.value)}
                        rows={6}
                        className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 resize-y"
                      />
                    </div>
                    <div className="flex gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setIsOpen(false)}
                        className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 transition-all"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={handleSave}
                        disabled={saving}
                        className="flex-1 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                      >
                        {saving ? 'Saving...' : (
                          <><Icons.Save /> Save to KB</>
                        )}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default SaveToKBButton;
