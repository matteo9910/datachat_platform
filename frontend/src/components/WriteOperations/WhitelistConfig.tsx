import React, { useState, useEffect, useCallback } from 'react';
import { writeApi } from '../../api/writeApi';
import type { WhitelistEntry, AvailableTable } from '../../api/writeApi';

const WhitelistConfig: React.FC = () => {
  const [whitelist, setWhitelist] = useState<WhitelistEntry[]>([]);
  const [availableTables, setAvailableTables] = useState<AvailableTable[]>([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [wl, tables] = await Promise.all([
        writeApi.getWhitelist(),
        writeApi.getAvailableTables(),
      ]);
      setWhitelist(wl);
      setAvailableTables(tables);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to load whitelist data.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddEntries = async () => {
    if (!selectedTable || selectedColumns.length === 0) return;
    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const entries = selectedColumns.map(col => ({
        table_name: selectedTable,
        column_name: col,
      }));
      await writeApi.saveWhitelist({ entries });
      setSelectedTable('');
      setSelectedColumns([]);
      setSuccess(`Added ${entries.length} whitelist entries.`);
      await loadData();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to save whitelist.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (entryId: string) => {
    setError(null);
    setSuccess(null);
    try {
      await writeApi.deleteWhitelistEntry(entryId);
      setSuccess('Entry removed.');
      await loadData();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to delete entry.');
    }
  };

  const selectedTableColumns = availableTables.find(t => t.table_name === selectedTable)?.columns || [];

  const toggleColumn = (col: string) => {
    setSelectedColumns(prev =>
      prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]
    );
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-8 h-full overflow-y-auto">
      <h1 className="text-xl font-bold text-slate-900 mb-6">Whitelist Configuration</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
          <p className="text-sm text-green-700">{success}</p>
        </div>
      )}

      {/* Add new entries */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
        <h2 className="text-sm font-bold text-slate-700 mb-4">Add Table/Columns to Whitelist</h2>

        {availableTables.length === 0 ? (
          <p className="text-sm text-slate-500">
            No tables available. Connect to a client database first.
          </p>
        ) : (
          <>
            <div className="mb-4">
              <label className="block text-xs font-bold text-slate-500 mb-1 uppercase tracking-wide">Table</label>
              <select
                className="w-full border border-slate-200 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                value={selectedTable}
                onChange={e => { setSelectedTable(e.target.value); setSelectedColumns([]); }}
              >
                <option value="">Select table...</option>
                {availableTables.map(t => (
                  <option key={t.table_name} value={t.table_name}>{t.table_name}</option>
                ))}
              </select>
            </div>

            {selectedTable && (
              <div className="mb-4">
                <label className="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wide">
                  Columns ({selectedColumns.length} selected)
                </label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-48 overflow-y-auto">
                  {selectedTableColumns.map(col => (
                    <label
                      key={col.column_name}
                      className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer text-sm transition-all ${
                        selectedColumns.includes(col.column_name)
                          ? 'border-orange-300 bg-orange-50 text-orange-800'
                          : 'border-slate-100 bg-slate-50 text-slate-600 hover:border-slate-200'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedColumns.includes(col.column_name)}
                        onChange={() => toggleColumn(col.column_name)}
                        className="accent-orange-600"
                      />
                      <span className="truncate">{col.column_name}</span>
                      <span className="text-[10px] text-slate-400 ml-auto">{col.data_type}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <button
              onClick={handleAddEntries}
              disabled={isSaving || !selectedTable || selectedColumns.length === 0}
              className="px-5 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isSaving ? 'Saving...' : 'Add to Whitelist'}
            </button>
          </>
        )}
      </div>

      {/* Current whitelist */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h2 className="text-sm font-bold text-slate-700 mb-4">
          Current Whitelist ({whitelist.length} entries)
        </h2>

        {whitelist.length === 0 ? (
          <p className="text-sm text-slate-500">No entries yet. Add tables and columns above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Table</th>
                  <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Column</th>
                  <th className="text-left py-2 px-3 font-bold text-slate-500 text-xs uppercase">Added</th>
                  <th className="text-right py-2 px-3 font-bold text-slate-500 text-xs uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                {whitelist.map(entry => (
                  <tr key={entry.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 px-3 text-slate-800 font-medium">{entry.table_name}</td>
                    <td className="py-2 px-3 text-slate-600">{entry.column_name}</td>
                    <td className="py-2 px-3 text-slate-400 text-xs">
                      {entry.created_at ? new Date(entry.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <button
                        onClick={() => entry.id && handleDelete(entry.id)}
                        className="text-red-500 hover:text-red-700 text-xs font-bold"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default WhitelistConfig;
