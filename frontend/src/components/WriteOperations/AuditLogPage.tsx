import React, { useState, useEffect, useCallback } from 'react';
import { writeApi } from '../../api/writeApi';
import type { AuditLogEntry } from '../../api/writeApi';

const AuditLogPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pageSize = 20;

  const loadLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await writeApi.getAuditLogs(page, pageSize);
      setLogs(resp.logs);
      setTotal(resp.total);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to load audit logs.');
    } finally {
      setIsLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const totalPages = Math.ceil(total / pageSize);

  const formatDetails = (details: Record<string, unknown> | null): string => {
    if (!details) return '—';
    const sql = details.sql as string | undefined;
    if (sql) return sql.length > 80 ? sql.substring(0, 80) + '...' : sql;
    return JSON.stringify(details).substring(0, 80);
  };

  if (isLoading && logs.length === 0) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-8 h-full overflow-y-auto">
      <h1 className="text-xl font-bold text-slate-900 mb-6">Audit Log</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        {logs.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-3xl mb-3">📋</div>
            <p className="text-sm text-slate-500">No audit log entries yet.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Timestamp</th>
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Action</th>
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Table</th>
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">SQL / Details</th>
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Rows</th>
                    <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">User ID</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(entry => (
                    <tr key={entry.id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="py-2 px-3 text-slate-600 text-xs whitespace-nowrap">
                        {entry.created_at
                          ? new Date(entry.created_at).toLocaleString()
                          : '—'}
                      </td>
                      <td className="py-2 px-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${
                          entry.action === 'write_execute'
                            ? 'bg-green-100 text-green-700'
                            : entry.action === 'write_execute_failed'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-slate-100 text-slate-600'
                        }`}>
                          {entry.action}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-slate-700 font-medium">{entry.resource || '—'}</td>
                      <td className="py-2 px-3 text-slate-500 text-xs font-mono max-w-xs truncate">
                        {formatDetails(entry.details)}
                      </td>
                      <td className="py-2 px-3 text-slate-600">
                        {entry.details && typeof entry.details === 'object' && 'rows_affected' in entry.details
                          ? String(entry.details.rows_affected)
                          : '—'}
                      </td>
                      <td className="py-2 px-3 text-slate-400 text-xs truncate max-w-[120px]">
                        {entry.user_id ? entry.user_id.substring(0, 8) + '...' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
              <p className="text-xs text-slate-500">
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <span className="px-3 py-1.5 text-xs text-slate-500">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AuditLogPage;
