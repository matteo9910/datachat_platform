import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { writeApi } from '../../api/writeApi';
import type { GenerateWriteResponse, WhitelistEntry } from '../../api/writeApi';

const WriteOperationsPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [nlText, setNlText] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [generated, setGenerated] = useState<GenerateWriteResponse | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [bulkConfirmText, setBulkConfirmText] = useState('');
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [whitelist, setWhitelist] = useState<WhitelistEntry[]>([]);

  const loadWhitelist = useCallback(async () => {
    try {
      const entries = await writeApi.getWhitelist();
      setWhitelist(entries);
    } catch {
      // Whitelist load may fail if not connected
    }
  }, []);

  useEffect(() => {
    loadWhitelist();
  }, [loadWhitelist]);

  const handleGenerate = async () => {
    if (!nlText.trim()) return;
    setIsGenerating(true);
    setError(null);
    setResult(null);
    setGenerated(null);

    try {
      const resp = await writeApi.generateSQL({ nl_text: nlText });
      setGenerated(resp);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'SQL generation failed.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExecute = async () => {
    if (!generated) return;

    if (generated.is_bulk && bulkConfirmText !== 'CONFIRM') {
      setError('Type CONFIRM to execute a bulk operation.');
      return;
    }

    setIsExecuting(true);
    setError(null);

    try {
      const resp = await writeApi.executeSQL({
        sql: generated.sql,
        extra_confirmation: generated.is_bulk,
      });
      setResult({ success: resp.success, message: resp.message });
      setShowConfirmModal(false);
      setGenerated(null);
      setNlText('');
      setBulkConfirmText('');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'SQL execution failed.');
      setShowConfirmModal(false);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleCancel = () => {
    setShowConfirmModal(false);
    setBulkConfirmText('');
  };

  // Empty whitelist warning
  if (whitelist.length === 0) {
    return (
      <div className="p-8 h-full overflow-y-auto">
        <h1 className="text-xl font-bold text-slate-900 mb-4">Write Operations</h1>
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-lg font-bold text-slate-700 mb-2">No Tables Whitelisted</h2>
          <p className="text-sm text-slate-500 mb-4">
            No tables or columns are configured for write operations.
            {isAdmin
              ? ' Go to the Whitelist Config tab to configure writable tables.'
              : ' Ask an admin to configure the write whitelist.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 h-full overflow-y-auto">
      <h1 className="text-xl font-bold text-slate-900 mb-6">Write Operations</h1>

      {/* NL Input */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
        <label className="block text-sm font-bold text-slate-700 mb-2">
          Describe the write operation in natural language
        </label>
        <textarea
          className="w-full border border-slate-200 rounded-xl p-4 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none"
          rows={3}
          placeholder="e.g. Set the status of order #1234 to 'shipped'"
          value={nlText}
          onChange={e => setNlText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleGenerate(); } }}
        />
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-slate-400">
            Whitelisted: {[...new Set(whitelist.map(w => w.table_name))].join(', ')}
          </p>
          <button
            onClick={handleGenerate}
            disabled={isGenerating || !nlText.trim()}
            className="px-5 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isGenerating ? 'Generating...' : 'Generate SQL'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <p className="text-sm text-red-700 font-medium">{error}</p>
        </div>
      )}

      {/* Success */}
      {result && (
        <div className={`rounded-xl p-4 mb-6 border ${result.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
          <p className={`text-sm font-medium ${result.success ? 'text-green-700' : 'text-red-700'}`}>
            {result.message}
          </p>
        </div>
      )}

      {/* Generated SQL Display */}
      {generated && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
          <h2 className="text-sm font-bold text-slate-700 mb-3">Generated SQL</h2>
          <pre className="bg-slate-900 text-green-400 rounded-xl p-4 text-sm overflow-x-auto whitespace-pre-wrap mb-4">
            {generated.sql}
          </pre>
          <div className="flex flex-wrap gap-4 text-xs text-slate-500 mb-4">
            <span><strong>Tables:</strong> {generated.target_tables.join(', ')}</span>
            <span><strong>Columns:</strong> {generated.target_columns.join(', ')}</span>
            {generated.is_bulk && (
              <span className="text-amber-600 font-bold">⚠️ BULK OPERATION</span>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowConfirmModal(true)}
              className="px-5 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 transition-all"
            >
              Execute
            </button>
            <button
              onClick={() => { setGenerated(null); setError(null); }}
              className="px-5 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-sm font-bold hover:bg-slate-200 transition-all"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && generated && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Confirm Execution</h3>
            <p className="text-sm text-slate-600 mb-3">The following SQL will be executed on your database:</p>
            <pre className="bg-slate-900 text-green-400 rounded-xl p-4 text-sm overflow-x-auto whitespace-pre-wrap mb-4">
              {generated.sql}
            </pre>
            <div className="text-xs text-slate-500 mb-4">
              <p>Tables: {generated.target_tables.join(', ')}</p>
              <p>Columns: {generated.target_columns.join(', ')}</p>
            </div>

            {generated.is_bulk && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4">
                <p className="text-sm text-amber-800 font-bold mb-2">
                  ⚠️ This is a bulk operation that may affect many rows.
                </p>
                <label className="block text-sm text-amber-700 mb-1">
                  Type <strong>CONFIRM</strong> to proceed:
                </label>
                <input
                  type="text"
                  className="w-full border border-amber-300 rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  value={bulkConfirmText}
                  onChange={e => setBulkConfirmText(e.target.value)}
                  placeholder="CONFIRM"
                />
              </div>
            )}

            <div className="flex gap-3 justify-end">
              <button
                onClick={handleCancel}
                className="px-5 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-sm font-bold hover:bg-slate-200 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleExecute}
                disabled={isExecuting || (generated.is_bulk && bulkConfirmText !== 'CONFIRM')}
                className="px-5 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isExecuting ? 'Executing...' : 'Execute'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WriteOperationsPage;
