import React, { useState, useCallback, useRef, useEffect } from 'react';
import { importsApi, ColumnSchemaResponse, ColumnOverride, UploadResponse, ConfirmResponse, ImportHistoryItem, ERPTemplateItem } from '../../api/importsApi';

// ---------------------------------------------------------------------------
// PG type options for column type dropdown
// ---------------------------------------------------------------------------
const PG_TYPES = [
  'VARCHAR(100)', 'VARCHAR(500)', 'TEXT',
  'INTEGER', 'BIGINT', 'NUMERIC(18,4)',
  'BOOLEAN', 'DATE', 'TIMESTAMP',
];

// ---------------------------------------------------------------------------
// Wizard steps
// ---------------------------------------------------------------------------
type WizardStep = 'source' | 'upload' | 'preview' | 'table_name' | 'confirm' | 'result';

// ERP icons/colors per brand
const ERP_BRANDS: Record<string, { color: string; bg: string; icon: string }> = {
  'SAP Business One': { color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200 hover:border-blue-400', icon: 'SAP' },
  'Zucchetti':        { color: 'text-purple-700', bg: 'bg-purple-50 border-purple-200 hover:border-purple-400', icon: 'ZUC' },
  'Danea Easyfatt':   { color: 'text-teal-700', bg: 'bg-teal-50 border-teal-200 hover:border-teal-400', icon: 'DNE' },
};

const FileImportWizard: React.FC = () => {
  const [step, setStep] = useState<WizardStep>('source');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Source selection
  const [sourceType, setSourceType] = useState<'generic' | 'erp'>('generic');
  const [erpTemplates, setErpTemplates] = useState<ERPTemplateItem[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<ERPTemplateItem | null>(null);

  // Upload state
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload response
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);

  // Editable columns (user can override suggested names/types)
  const [columns, setColumns] = useState<ColumnOverride[]>([]);

  // Table name
  const [tableName, setTableName] = useState('');

  // Import result
  const [importResult, setImportResult] = useState<ConfirmResponse | null>(null);

  // History
  const [history, setHistory] = useState<ImportHistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Load ERP templates on mount
  useEffect(() => {
    importsApi.getERPTemplates().then(setErpTemplates).catch(() => {});
  }, []);

  // ------------------------------------------------------------------
  // Step 1: Upload
  // ------------------------------------------------------------------

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setLoading(true);
    try {
      if (sourceType === 'erp' && selectedTemplate) {
        // ERP template upload
        const data = await importsApi.uploadERP(selectedTemplate.id, file);
        // Convert ERPUploadResponse to UploadResponse shape for shared wizard steps
        setUploadData({
          import_id: data.import_id,
          filename: data.filename,
          file_type: data.file_type,
          total_rows: data.total_rows,
          columns: data.columns.map(c => ({
            original_name: c.original_name,
            suggested_name: c.suggested_name,
            pg_type: c.pg_type,
            nullable: c.nullable,
            sample_values: [],
          })),
          preview_rows: data.preview_rows,
        });
        setColumns(
          data.columns.map(c => ({
            original_name: c.original_name,
            suggested_name: c.suggested_name,
            pg_type: c.pg_type,
            nullable: c.nullable,
          }))
        );
        // Suggest table name from template export type
        const baseName = selectedTemplate.export_type.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_');
        setTableName(baseName.substring(0, 63));
      } else {
        // Generic upload
        const data = await importsApi.upload(file);
        setUploadData(data);
        setColumns(
          data.columns.map((c: ColumnSchemaResponse) => ({
            original_name: c.original_name,
            suggested_name: c.suggested_name,
            pg_type: c.pg_type,
            nullable: c.nullable,
          }))
        );
        const baseName = file.name.replace(/\.\w+$/, '').replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase();
        setTableName(baseName.substring(0, 63));
      }
      setStep('preview');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  }, [sourceType, selectedTemplate]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, [handleFile]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      handleFile(e.target.files[0]);
    }
  }, [handleFile]);

  // ------------------------------------------------------------------
  // Step 2: Preview — edit columns
  // ------------------------------------------------------------------

  const updateColumn = (idx: number, field: keyof ColumnOverride, value: any) => {
    setColumns(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  // ------------------------------------------------------------------
  // Step 4: Confirm — execute import
  // ------------------------------------------------------------------

  const handleConfirm = async () => {
    if (!uploadData) return;
    setError(null);
    setLoading(true);
    try {
      const result = await importsApi.confirm(uploadData.import_id, tableName, columns);
      setImportResult(result);
      setStep('result');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Import failed');
    } finally {
      setLoading(false);
    }
  };

  // ------------------------------------------------------------------
  // History
  // ------------------------------------------------------------------

  const loadHistory = async () => {
    try {
      const data = await importsApi.getHistory();
      setHistory(data);
      setShowHistory(true);
    } catch {
      setHistory([]);
      setShowHistory(true);
    }
  };

  // ------------------------------------------------------------------
  // Reset
  // ------------------------------------------------------------------

  const resetWizard = () => {
    setStep('source');
    setSourceType('generic');
    setSelectedTemplate(null);
    setUploadData(null);
    setColumns([]);
    setTableName('');
    setImportResult(null);
    setError(null);
    setShowHistory(false);
  };

  // ------------------------------------------------------------------
  // Step indicator
  // ------------------------------------------------------------------

  const steps: { key: WizardStep; label: string }[] = [
    { key: 'source', label: 'Sorgente' },
    { key: 'upload', label: 'Upload' },
    { key: 'preview', label: 'Preview & Schema' },
    { key: 'table_name', label: 'Nome Tabella' },
    { key: 'confirm', label: 'Conferma' },
    { key: 'result', label: 'Risultato' },
  ];

  const currentStepIdx = steps.findIndex(s => s.key === step);

  // Build DDL preview
  const ddlPreview = tableName && columns.length > 0
    ? `CREATE TABLE "${tableName}" (\n${columns.map(c => `  "${c.suggested_name}" ${c.pg_type}${c.nullable ? '' : ' NOT NULL'}`).join(',\n')}\n);`
    : '';

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Importa Dati</h2>
            <p className="text-sm text-slate-500 mt-1">
              Carica un file CSV o Excel per creare una tabella nel database
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={loadHistory}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              Storico Import
            </button>
            {step !== 'upload' && (
              <button
                onClick={resetWizard}
                className="px-3 py-1.5 text-xs font-medium text-orange-600 bg-orange-50 hover:bg-orange-100 rounded-lg transition-colors"
              >
                Nuovo Import
              </button>
            )}
          </div>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1 mb-8">
          {steps.map((s, i) => (
            <React.Fragment key={s.key}>
              <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide ${
                i < currentStepIdx ? 'bg-green-100 text-green-700' :
                i === currentStepIdx ? 'bg-orange-600 text-white' :
                'bg-slate-100 text-slate-400'
              }`}>
                <span className="w-5 h-5 flex items-center justify-center rounded-full bg-white/20 text-[10px]">
                  {i < currentStepIdx ? '\u2713' : i + 1}
                </span>
                {s.label}
              </div>
              {i < steps.length - 1 && (
                <div className={`flex-1 h-0.5 ${i < currentStepIdx ? 'bg-green-300' : 'bg-slate-200'}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 font-bold">&times;</button>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Source Selection */}
        {/* ============================================================ */}
        {step === 'source' && (
          <div className="space-y-6">
            <h3 className="text-sm font-bold text-slate-700">Seleziona la sorgente dei dati</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Generic CSV/Excel */}
              <button
                onClick={() => { setSourceType('generic'); setSelectedTemplate(null); setStep('upload'); }}
                className="border-2 border-slate-200 hover:border-orange-400 rounded-2xl p-6 text-left transition-colors group"
              >
                <div className="w-12 h-12 bg-orange-100 rounded-xl flex items-center justify-center mb-3 group-hover:bg-orange-200 transition-colors">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ea580c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                </div>
                <h4 className="font-bold text-slate-900 mb-1">File Generico</h4>
                <p className="text-xs text-slate-400">CSV o Excel generico con auto-rilevamento schema</p>
              </button>

              {/* ERP Templates grouped by brand */}
              {Object.entries(
                erpTemplates.reduce<Record<string, ERPTemplateItem[]>>((acc, t) => {
                  (acc[t.erp_name] = acc[t.erp_name] || []).push(t);
                  return acc;
                }, {})
              ).map(([erpName, templates]) => {
                const brand = ERP_BRANDS[erpName] || { color: 'text-slate-700', bg: 'bg-slate-50 border-slate-200 hover:border-slate-400', icon: '?' };
                return (
                  <div key={erpName} className={`border-2 rounded-2xl p-6 transition-colors ${brand.bg}`}>
                    <div className="flex items-center gap-3 mb-3">
                      <div className={`w-12 h-12 rounded-xl bg-white border flex items-center justify-center font-bold text-sm ${brand.color}`}>
                        {brand.icon}
                      </div>
                      <div>
                        <h4 className={`font-bold ${brand.color}`}>{erpName}</h4>
                        <p className="text-xs text-slate-400">{templates.length} template disponibili</p>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {templates.map(t => (
                        <button
                          key={t.id}
                          onClick={() => { setSourceType('erp'); setSelectedTemplate(t); setStep('upload'); }}
                          className="w-full text-left px-3 py-2 bg-white/80 hover:bg-white rounded-lg text-sm transition-colors border border-transparent hover:border-slate-300"
                        >
                          <span className="font-semibold text-slate-700">{t.export_type}</span>
                          <span className="text-slate-400 ml-2 text-xs">({t.column_count} colonne)</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Upload */}
        {/* ============================================================ */}
        {step === 'upload' && (
          <div className="space-y-4">
            {/* ERP template info banner */}
            {sourceType === 'erp' && selectedTemplate && (
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-widest text-blue-600">{selectedTemplate.erp_name}</span>
                  <span className="text-blue-300">|</span>
                  <span className="text-sm font-semibold text-blue-800">{selectedTemplate.export_type}</span>
                </div>
                {selectedTemplate.instructions && (
                  <p className="text-xs text-blue-600 mt-1">{selectedTemplate.instructions}</p>
                )}
              </div>
            )}

            <div
              className={`border-2 border-dashed rounded-2xl p-16 text-center transition-colors cursor-pointer ${
                dragActive ? 'border-orange-400 bg-orange-50' : 'border-slate-300 hover:border-orange-300 hover:bg-slate-50'
              }`}
              onDragOver={e => { e.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={handleFileInput}
              />
              {loading ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-slate-600 text-sm">Analisi del file in corso...</p>
                </div>
              ) : (
                <>
                  <div className="mx-auto w-16 h-16 bg-orange-100 rounded-2xl flex items-center justify-center mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ea580c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                  </div>
                  <p className="text-slate-700 font-semibold mb-1">Trascina un file qui o clicca per selezionare</p>
                  <p className="text-slate-400 text-xs">Formati supportati: CSV, Excel (.xlsx, .xls) &mdash; Max 50 MB</p>
                </>
              )}
            </div>

            <div className="flex justify-start">
              <button
                onClick={() => setStep('source')}
                className="px-4 py-2 text-slate-600 bg-slate-100 rounded-lg font-bold text-xs hover:bg-slate-200 transition-colors"
              >
                Cambia sorgente
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Preview & Schema */}
        {/* ============================================================ */}
        {step === 'preview' && uploadData && (
          <div className="space-y-6">
            {/* File info */}
            <div className="flex items-center gap-4 p-3 bg-slate-50 rounded-lg text-sm">
              <span className="font-bold text-slate-700">{uploadData.filename}</span>
              <span className="text-slate-400">|</span>
              <span className="text-slate-500">{uploadData.total_rows.toLocaleString()} righe</span>
              <span className="text-slate-400">|</span>
              <span className="text-slate-500">{uploadData.columns.length} colonne</span>
              <span className="text-slate-400">|</span>
              <span className="text-slate-500 uppercase">{uploadData.file_type}</span>
            </div>

            {/* Columns editor */}
            <div>
              <h3 className="text-sm font-bold text-slate-700 mb-3">Schema Colonne</h3>
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 uppercase">Originale</th>
                      <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 uppercase">Nome Colonna</th>
                      <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 uppercase">Tipo PG</th>
                      <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 uppercase">Nullable</th>
                      <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 uppercase">Esempi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns.map((col, i) => {
                      const orig = uploadData.columns[i];
                      return (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-3 py-2 text-slate-400 text-xs font-mono">{col.original_name}</td>
                          <td className="px-3 py-2">
                            <input
                              value={col.suggested_name}
                              onChange={e => updateColumn(i, 'suggested_name', e.target.value)}
                              className="w-full px-2 py-1 text-xs border border-slate-200 rounded focus:outline-none focus:border-orange-400 font-mono"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <select
                              value={col.pg_type}
                              onChange={e => updateColumn(i, 'pg_type', e.target.value)}
                              className="px-2 py-1 text-xs border border-slate-200 rounded focus:outline-none focus:border-orange-400 bg-white"
                            >
                              {PG_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                              {!PG_TYPES.includes(col.pg_type) && <option value={col.pg_type}>{col.pg_type}</option>}
                            </select>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <input
                              type="checkbox"
                              checked={col.nullable}
                              onChange={e => updateColumn(i, 'nullable', e.target.checked)}
                              className="accent-orange-600"
                            />
                          </td>
                          <td className="px-3 py-2 text-xs text-slate-400 truncate max-w-[200px]">
                            {orig?.sample_values?.slice(0, 3).map(v => String(v)).join(', ')}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Data preview */}
            <div>
              <h3 className="text-sm font-bold text-slate-700 mb-3">Anteprima Dati (prime 20 righe)</h3>
              <div className="border border-slate-200 rounded-lg overflow-auto max-h-64">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 sticky top-0">
                      {uploadData.columns.map((c, i) => (
                        <th key={i} className="text-left px-2 py-1.5 text-slate-500 font-bold whitespace-nowrap">
                          {c.original_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {uploadData.preview_rows.map((row, ri) => (
                      <tr key={ri} className="border-b border-slate-50 hover:bg-slate-50">
                        {uploadData.columns.map((c, ci) => (
                          <td key={ci} className="px-2 py-1 text-slate-600 whitespace-nowrap max-w-[200px] truncate">
                            {row[c.original_name] != null ? String(row[c.original_name]) : <span className="text-slate-300">NULL</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setStep('table_name')}
                className="px-6 py-2 bg-orange-600 text-white rounded-lg font-bold text-sm hover:bg-orange-700 transition-colors"
              >
                Avanti
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Table Name */}
        {/* ============================================================ */}
        {step === 'table_name' && (
          <div className="max-w-lg mx-auto space-y-6">
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-2">Nome Tabella</label>
              <input
                value={tableName}
                onChange={e => setTableName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_').substring(0, 63))}
                className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:border-orange-400"
                placeholder="es. fatture_2024"
              />
              <p className="text-xs text-slate-400 mt-1">Solo lettere minuscole, numeri e underscore. Max 63 caratteri.</p>
            </div>

            <div className="flex justify-between">
              <button
                onClick={() => setStep('preview')}
                className="px-6 py-2 text-slate-600 bg-slate-100 rounded-lg font-bold text-sm hover:bg-slate-200 transition-colors"
              >
                Indietro
              </button>
              <button
                onClick={() => setStep('confirm')}
                disabled={!tableName.trim()}
                className="px-6 py-2 bg-orange-600 text-white rounded-lg font-bold text-sm hover:bg-orange-700 transition-colors disabled:opacity-40"
              >
                Avanti
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Confirm */}
        {/* ============================================================ */}
        {step === 'confirm' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-bold text-slate-700 mb-3">DDL che verrà eseguito</h3>
              <pre className="bg-slate-900 text-green-400 p-4 rounded-lg text-xs font-mono overflow-auto max-h-64 whitespace-pre-wrap">
                {ddlPreview}
              </pre>
            </div>

            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
              <strong>{uploadData?.total_rows.toLocaleString()}</strong> righe verranno inserite nella tabella <strong>"{tableName}"</strong>.
            </div>

            <div className="flex justify-between">
              <button
                onClick={() => setStep('table_name')}
                className="px-6 py-2 text-slate-600 bg-slate-100 rounded-lg font-bold text-sm hover:bg-slate-200 transition-colors"
              >
                Indietro
              </button>
              <button
                onClick={handleConfirm}
                disabled={loading}
                className="px-6 py-2 bg-orange-600 text-white rounded-lg font-bold text-sm hover:bg-orange-700 transition-colors disabled:opacity-40 flex items-center gap-2"
              >
                {loading && <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                {loading ? 'Importazione...' : 'Conferma Import'}
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Result */}
        {/* ============================================================ */}
        {step === 'result' && importResult && (
          <div className="max-w-lg mx-auto text-center space-y-6">
            {importResult.success ? (
              <>
                <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                  <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">Import Completato</h3>
                  <p className="text-sm text-slate-500">
                    <strong>{importResult.rows_imported.toLocaleString()}</strong> righe importate nella tabella <strong>"{importResult.table_name}"</strong>
                  </p>
                </div>
                <p className="text-xs text-slate-400">
                  Ora puoi interrogare questa tabella dalla Chat con i Dati.
                </p>
              </>
            ) : (
              <>
                <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto">
                  <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">Import Fallito</h3>
                  {importResult.errors.map((err, i) => (
                    <p key={i} className="text-sm text-red-600">{err}</p>
                  ))}
                </div>
              </>
            )}

            <button
              onClick={resetWizard}
              className="px-6 py-2 bg-orange-600 text-white rounded-lg font-bold text-sm hover:bg-orange-700 transition-colors"
            >
              Nuovo Import
            </button>
          </div>
        )}

        {/* ============================================================ */}
        {/* History panel */}
        {/* ============================================================ */}
        {showHistory && (
          <div className="mt-8 border border-slate-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-700">Storico Import</h3>
              <button onClick={() => setShowHistory(false)} className="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
            </div>
            {history.length === 0 ? (
              <p className="text-sm text-slate-400">Nessun import effettuato.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">File</th>
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">Tabella</th>
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">Righe</th>
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">Colonne</th>
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">Tipo</th>
                    <th className="text-left px-2 py-1 text-slate-500 font-bold">Data</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map(h => (
                    <tr key={h.id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="px-2 py-1.5 text-slate-600">{h.original_filename}</td>
                      <td className="px-2 py-1.5 font-mono text-slate-700">{h.table_name}</td>
                      <td className="px-2 py-1.5 text-slate-500">{h.row_count.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-slate-500">{h.column_count}</td>
                      <td className="px-2 py-1.5 text-slate-500 uppercase">{h.source_type}</td>
                      <td className="px-2 py-1.5 text-slate-400">{h.created_at ? new Date(h.created_at).toLocaleDateString('it-IT') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default FileImportWizard;
