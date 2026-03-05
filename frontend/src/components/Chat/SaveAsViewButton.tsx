import React, { useState } from 'react';
import { viewsApi } from '../../api/viewsApi';
import { useAuth } from '../../contexts/AuthContext';
import { Icons } from '../Layout/Icons';
import { AxiosError } from 'axios';

interface SaveAsViewButtonProps {
  sql: string;
}

const SQL_RESERVED_WORDS = new Set([
  'select', 'insert', 'update', 'delete', 'drop', 'create', 'alter',
  'table', 'view', 'index', 'from', 'where', 'join', 'inner', 'outer',
  'left', 'right', 'on', 'and', 'or', 'not', 'null', 'is', 'in',
  'between', 'like', 'order', 'by', 'group', 'having', 'limit',
  'offset', 'union', 'all', 'distinct', 'as', 'case', 'when', 'then',
  'else', 'end', 'exists', 'into', 'values', 'set', 'begin', 'commit',
  'rollback', 'grant', 'revoke', 'primary', 'key', 'foreign',
  'references', 'constraint', 'check', 'default', 'unique',
  'cascade', 'restrict', 'trigger', 'procedure', 'function',
  'database', 'schema', 'exec', 'execute', 'declare', 'cursor',
  'fetch', 'open', 'close', 'truncate', 'replace', 'with',
]);

function validateViewName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return 'View name cannot be empty';
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmed)) {
    return 'Only letters, numbers, and underscores allowed (must start with letter or underscore)';
  }
  if (SQL_RESERVED_WORDS.has(trimmed.toLowerCase())) {
    return `"${trimmed}" is a SQL reserved word`;
  }
  return null;
}

const SaveAsViewButton: React.FC<SaveAsViewButtonProps> = ({ sql }) => {
  const { hasRole } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [viewName, setViewName] = useState('');
  const [editSql, setEditSql] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [nameError, setNameError] = useState('');
  const [saved, setSaved] = useState(false);

  // Only show for admin/analyst roles
  if (!hasRole(['admin', 'analyst'])) return null;

  const handleOpen = () => {
    setViewName('');
    setEditSql(sql);
    setError('');
    setNameError('');
    setSaved(false);
    setIsOpen(true);
  };

  const handleNameChange = (value: string) => {
    setViewName(value);
    const validationError = validateViewName(value);
    setNameError(validationError || '');
  };

  const handleSave = async () => {
    const validationError = validateViewName(viewName);
    if (validationError) {
      setNameError(validationError);
      return;
    }
    if (!editSql.trim()) {
      setError('SQL query cannot be empty');
      return;
    }
    setError('');
    setNameError('');
    setSaving(true);
    try {
      await viewsApi.createView({
        view_name: viewName.trim(),
        sql_query: editSql.trim(),
      });
      setSaved(true);
      setTimeout(() => setIsOpen(false), 1200);
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(axiosErr?.response?.data?.detail || 'Failed to save view');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
        title="Save as View"
      >
        <Icons.Database />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={() => setIsOpen(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">
                Save as SQL View
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
                  <p className="text-sm font-bold text-slate-900">View created successfully!</p>
                  <p className="text-xs text-slate-500 mt-1">The view is now available in the schema browser.</p>
                </div>
              ) : (
                <>
                  {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>}
                  <p className="text-xs text-slate-500 mb-4">
                    Create a SQL view on the database. The view will appear in the schema browser and can be queried like a table.
                  </p>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">View Name</label>
                      <input
                        value={viewName}
                        onChange={e => handleNameChange(e.target.value)}
                        placeholder="e.g. sales_summary"
                        className={`w-full px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 ${
                          nameError ? 'border-red-300 bg-red-50' : 'border-slate-200'
                        }`}
                      />
                      {nameError && <p className="text-xs text-red-500 mt-1">{nameError}</p>}
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
                        disabled={saving || !!nameError}
                        className="flex-1 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                      >
                        {saving ? 'Creating...' : (
                          <><Icons.Save /> Create View</>
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

export default SaveAsViewButton;