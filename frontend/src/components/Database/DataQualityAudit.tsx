import React, { useState, useEffect } from 'react';
import { auditApi, AuditReportResponse, AuditDimension, AuditHistoryItem } from '../../api/auditApi';

const DIMENSION_LABELS: Record<string, { label: string; icon: string }> = {
  completeness:   { label: 'Completezza',       icon: 'C' },
  consistency:    { label: 'Coerenza',           icon: 'K' },
  naming:         { label: 'Naming',             icon: 'N' },
  normalization:  { label: 'Normalizzazione',    icon: 'R' },
  performance:    { label: 'Performance',        icon: 'P' },
  documentation:  { label: 'Documentazione',     icon: 'D' },
};

const scoreColor = (score: number) => {
  if (score >= 70) return 'text-emerald-600';
  if (score >= 40) return 'text-amber-500';
  return 'text-red-500';
};

const scoreBg = (score: number) => {
  if (score >= 70) return 'bg-emerald-500';
  if (score >= 40) return 'bg-amber-400';
  return 'bg-red-500';
};

const scoreGradient = (score: number) => {
  if (score >= 70) return 'from-emerald-500 to-emerald-600';
  if (score >= 40) return 'from-amber-400 to-amber-500';
  return 'from-red-500 to-red-600';
};

const severityColor: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-slate-100 text-slate-600',
};

/* ----- Gauge SVG component ----- */
const ScoreGauge: React.FC<{ score: number }> = ({ score }) => {
  const radius = 80;
  const stroke = 12;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444';

  return (
    <svg width="200" height="200" viewBox="0 0 200 200" className="mx-auto">
      <circle cx="100" cy="100" r={radius} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
      <circle
        cx="100" cy="100" r={radius} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={circumference - progress}
        strokeLinecap="round"
        transform="rotate(-90 100 100)"
        className="transition-all duration-1000"
      />
      <text x="100" y="92" textAnchor="middle" className="fill-slate-900 text-4xl font-bold" fontSize="40" fontWeight="700">{score}</text>
      <text x="100" y="118" textAnchor="middle" className="fill-slate-400" fontSize="12" fontWeight="600">/100</text>
    </svg>
  );
};

/* ----- Dimension Card ----- */
const DimensionCard: React.FC<{
  name: string;
  dim: AuditDimension;
  expanded: boolean;
  onToggle: () => void;
}> = ({ name, dim, expanded, onToggle }) => {
  const meta = DIMENSION_LABELS[name] || { label: name, icon: '?' };
  const roundedScore = Math.round(dim.score);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
      <button onClick={onToggle} className="w-full p-4 flex items-center gap-4 hover:bg-slate-50 transition-colors">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${scoreGradient(roundedScore)} text-white flex items-center justify-center font-bold text-sm`}>
          {meta.icon}
        </div>
        <div className="flex-1 text-left">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-900">{meta.label}</span>
            <span className={`text-sm font-bold ${scoreColor(roundedScore)}`}>{roundedScore}</span>
          </div>
          <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${scoreBg(roundedScore)} transition-all duration-700`} style={{ width: `${roundedScore}%` }} />
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[10px] text-slate-400 font-bold">Peso {(dim.weight * 100).toFixed(0)}%</span>
            <span className="text-[10px] text-slate-400 font-bold">{dim.issues_count} issue</span>
          </div>
        </div>
        <svg className={`w-4 h-4 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      {expanded && dim.issues.length > 0 && (
        <div className="border-t border-slate-100 p-4 space-y-2 max-h-64 overflow-y-auto">
          {dim.issues.map((issue, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${severityColor[issue.severity]}`}>{issue.severity}</span>
              <span className="text-slate-600">{issue.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ----- Main Component ----- */
const DataQualityAudit: React.FC = () => {
  const [report, setReport] = useState<AuditReportResponse | null>(null);
  const [history, setHistory] = useState<AuditHistoryItem[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [expandedDim, setExpandedDim] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadLatest();
    loadHistory();
  }, []);

  const loadLatest = async () => {
    try {
      const data = await auditApi.getLatest();
      if (data) setReport(data);
    } catch {
      // no cached report
    }
  };

  const loadHistory = async () => {
    try {
      const data = await auditApi.getHistory();
      setHistory(data);
    } catch {
      // ignore
    }
  };

  const runAudit = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const data = await auditApi.runAudit();
      setReport(data);
      loadHistory();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Errore durante l\'audit');
    } finally {
      setIsRunning(false);
    }
  };

  const loadHistoricReport = async (id: string) => {
    // For now, just find it from history metadata — full report from latest or re-run
    // We show the summary from history
    const item = history.find(h => h.id === id);
    if (item) {
      // Load the full report via latest (if same id) or show partial info
      try {
        const data = await auditApi.getLatest();
        if (data && data.id === id) {
          setReport(data);
        }
      } catch {
        // ignore
      }
    }
  };

  const dimEntries = report
    ? Object.entries(report.dimensions).sort((a, b) => a[1].score - b[1].score)
    : [];

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Data Quality Audit</h3>
          <p className="text-xs text-slate-400 mt-0.5">Analisi automatica della qualita del database su 6 dimensioni</p>
        </div>
        <div className="flex items-center gap-3">
          {history.length > 0 && (
            <select
              onChange={(e) => loadHistoricReport(e.target.value)}
              className="text-xs border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-600"
              defaultValue=""
            >
              <option value="" disabled>Storico audit</option>
              {history.map(h => (
                <option key={h.id} value={h.id}>
                  {h.created_at ? new Date(h.created_at).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'N/A'} — Score {h.overall_score}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={runAudit}
            disabled={isRunning}
            className="px-5 py-2.5 bg-orange-600 text-white text-xs font-bold uppercase tracking-widest rounded-xl hover:bg-orange-700 disabled:opacity-50 transition-all flex items-center gap-2"
          >
            {isRunning ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Audit in corso...
              </>
            ) : (
              report ? 'Riesegui Audit' : 'Esegui Audit'
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{error}</div>
      )}

      {/* Loading state */}
      {isRunning && !report && (
        <div className="text-center py-20">
          <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm text-slate-500">Analisi in corso... Potrebbe richiedere qualche minuto.</p>
        </div>
      )}

      {/* Report */}
      {report && (
        <div className="space-y-6">
          {/* Score + Summary row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Gauge */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 flex flex-col items-center justify-center">
              <ScoreGauge score={report.overall_score} />
              <p className="mt-2 text-xs font-bold uppercase tracking-widest text-slate-400">
                Data Health Score
              </p>
              <p className="text-[10px] text-slate-400 mt-1">
                {report.table_count} tabelle analizzate
              </p>
            </div>

            {/* Summary */}
            <div className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-6">
              <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Executive Summary</h4>
              <p className="text-sm text-slate-700 leading-relaxed">{report.summary}</p>
              {report.generated_at && (
                <p className="text-[10px] text-slate-400 mt-4">
                  Generato il {new Date(report.generated_at).toLocaleString('it-IT')}
                </p>
              )}
            </div>
          </div>

          {/* Dimensions grid */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Dimensioni di Qualita</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {dimEntries.map(([name, dim]) => (
                <DimensionCard
                  key={name}
                  name={name}
                  dim={dim}
                  expanded={expandedDim === name}
                  onToggle={() => setExpandedDim(expandedDim === name ? null : name)}
                />
              ))}
            </div>
          </div>

          {/* Recommendations */}
          {report.recommendations.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-2xl p-6">
              <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Raccomandazioni</h4>
              <div className="space-y-3">
                {report.recommendations.map((rec, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                      {i + 1}
                    </span>
                    <p className="text-sm text-slate-700">{rec}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!report && !isRunning && (
        <div className="text-center py-20 bg-white border border-slate-200 rounded-2xl">
          <div className="w-16 h-16 rounded-2xl bg-orange-100 flex items-center justify-center mx-auto mb-4">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ea580c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <h4 className="text-lg font-bold text-slate-900 mb-2">Nessun Audit Disponibile</h4>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            Esegui un audit per analizzare la qualita dei dati su 6 dimensioni: completezza, coerenza, naming, normalizzazione, performance e documentazione.
          </p>
        </div>
      )}
    </div>
  );
};

export default DataQualityAudit;
