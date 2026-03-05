import React, { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import ChartViewer from '../Charts/ChartViewer';
import { Icons } from '../Layout/Icons';
import { Modal, ConfirmModal } from '../ui/modal';
import { Toast, useToast } from '../ui/toast';
import { dashboardApi, DashboardListItem, FilterOption, ChartSpec } from '../../api/dashboardApi';

// ============================================================
// Types
// ============================================================

interface DashboardChart {
  title: string;
  sql: string;
  chart_type: string;
  plotly_config?: any;
  data?: any[];
}

interface GridPosition {
  index: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

// ============================================================
// FilterBar Component
// ============================================================

interface FilterBarProps {
  filters: FilterOption[];
  filterValues: Record<string, any>;
  onFilterChange: (column: string, value: any) => void;
  onApply: () => void;
  onClear: () => void;
  isApplying: boolean;
}

const FilterBar: React.FC<FilterBarProps> = ({
  filters, filterValues, onFilterChange, onApply, onClear, isApplying,
}) => {
  if (filters.length === 0) return null;

  return (
    <div className="bg-white border-b border-slate-200 px-6 py-3 flex items-center gap-4 flex-wrap">
      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest shrink-0">
        Filtri
      </span>
      {filters.map((f) => (
        <div key={f.column} className="flex items-center gap-2">
          <label className="text-[10px] font-medium text-slate-600">{f.label}:</label>
          {f.filter_type === 'categorical' && (
            <select
              value={filterValues[f.column] ?? ''}
              onChange={(e) => onFilterChange(f.column, e.target.value || undefined)}
              className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-orange-400"
            >
              <option value="">Tutti</option>
              {(f.values || []).map((v: string) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          )}
          {f.filter_type === 'date' && (
            <input
              type="date"
              value={filterValues[f.column] ?? ''}
              onChange={(e) => onFilterChange(f.column, e.target.value || undefined)}
              className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-orange-400"
            />
          )}
          {f.filter_type === 'numeric' && (
            <div className="flex items-center gap-1">
              <input
                type="number"
                placeholder="Min"
                value={filterValues[f.column]?.min ?? ''}
                onChange={(e) => {
                  const cur = filterValues[f.column] || {};
                  onFilterChange(f.column, { ...cur, min: e.target.value ? Number(e.target.value) : undefined });
                }}
                className="w-20 text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-orange-400"
              />
              <span className="text-slate-400 text-[10px]">-</span>
              <input
                type="number"
                placeholder="Max"
                value={filterValues[f.column]?.max ?? ''}
                onChange={(e) => {
                  const cur = filterValues[f.column] || {};
                  onFilterChange(f.column, { ...cur, max: e.target.value ? Number(e.target.value) : undefined });
                }}
                className="w-20 text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-orange-400"
              />
            </div>
          )}
        </div>
      ))}
      <button
        onClick={onApply}
        disabled={isApplying}
        className="px-4 py-1.5 bg-orange-600 text-white rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-orange-700 disabled:opacity-50 transition-all"
      >
        {isApplying ? 'Applicando...' : 'Applica'}
      </button>
      <button
        onClick={onClear}
        className="px-4 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-slate-200 transition-all"
      >
        Reset
      </button>
    </div>
  );
};

// ============================================================
// Main DashboardManager
// ============================================================

const DashboardManager: React.FC = () => {
  const { savedCharts } = useAppStore();
  const { toast, showToast, hideToast } = useToast();

  // --- NL Generation state ---
  const [nlInput, setNlInput] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  // --- Current dashboard state ---
  const [dashboardName, setDashboardName] = useState('');
  const [charts, setCharts] = useState<DashboardChart[]>([]);
  const [, setGridPositions] = useState<GridPosition[]>([]);
  const [currentDashboardId, setCurrentDashboardId] = useState<string | null>(null);

  // --- Saved dashboards ---
  const [savedDashboards, setSavedDashboards] = useState<DashboardListItem[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // --- Filters ---
  const [availableFilters, setAvailableFilters] = useState<FilterOption[]>([]);
  const [filterValues, setFilterValues] = useState<Record<string, any>>({});
  const [isApplyingFilters, setIsApplyingFilters] = useState(false);

  // --- Modals ---
  const [chartSelectorOpen, setChartSelectorOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [dashToDelete, setDashToDelete] = useState<string | null>(null);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');

  const canvasRef = useRef<HTMLDivElement>(null);

  // --- Load saved dashboards on mount ---
  useEffect(() => {
    loadSavedDashboards();
  }, []);

  const loadSavedDashboards = async () => {
    try {
      const list = await dashboardApi.list();
      setSavedDashboards(list);
    } catch {
      // Silently fail if not authenticated yet
    }
  };

  // --- NL Generate ---
  const handleGenerate = async () => {
    if (!nlInput.trim() || isGenerating) return;
    setIsGenerating(true);
    try {
      const result = await dashboardApi.generate(nlInput.trim());
      const newCharts: DashboardChart[] = result.charts.map((c: ChartSpec) => ({
        title: c.title,
        sql: c.sql,
        chart_type: c.chart_type,
        plotly_config: c.plotly_config,
        data: c.data,
      }));
      setCharts(newCharts);
      setGridPositions(result.layout.positions || buildDefaultGrid(newCharts.length));
      setDashboardName(result.suggested_name);
      setCurrentDashboardId(null);
      setFilterValues({});
      setAvailableFilters([]);
      showToast('Dashboard generata con successo!', 'success');
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Errore nella generazione', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  // --- Add chart from Gallery ---
  const handleAddFromGallery = (chart: any) => {
    const newChart: DashboardChart = {
      title: chart.title,
      sql: chart.sqlTemplate || '',
      chart_type: chart.plotlyConfig?.data?.[0]?.type || 'bar',
      plotly_config: chart.plotlyConfig,
      data: [],
    };
    setCharts((prev) => [...prev, newChart]);
    setChartSelectorOpen(false);
    showToast('Grafico aggiunto!', 'success');
  };

  // --- Remove chart ---
  const handleRemoveChart = (idx: number) => {
    setCharts((prev) => prev.filter((_, i) => i !== idx));
  };

  // --- Save dashboard ---
  const handleSave = async () => {
    const name = saveName.trim() || dashboardName.trim() || 'Dashboard';
    try {
      const payload = {
        name,
        layout: { columns: 2, positions: buildDefaultGrid(charts.length) },
        charts: charts.map((c) => ({
          title: c.title,
          sql: c.sql,
          chart_type: c.chart_type,
          plotly_config: c.plotly_config,
        })),
        filters: filterValues,
      };

      if (currentDashboardId) {
        await dashboardApi.update(currentDashboardId, payload);
        showToast('Dashboard aggiornata!', 'success');
      } else {
        const resp = await dashboardApi.save(payload);
        setCurrentDashboardId(resp.id);
        showToast('Dashboard salvata!', 'success');
      }
      setDashboardName(name);
      setSaveModalOpen(false);
      setSaveName('');
      loadSavedDashboards();
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Errore nel salvataggio', 'error');
    }
  };

  // --- Load dashboard ---
  const handleLoadDashboard = async (id: string) => {
    try {
      const dash = await dashboardApi.get(id);
      setCurrentDashboardId(id);
      setDashboardName(dash.name);
      setCharts(dash.charts || []);
      setGridPositions(dash.layout?.positions || buildDefaultGrid((dash.charts || []).length));
      setFilterValues(dash.filters || {});
      try {
        const filters = await dashboardApi.getAvailableFilters(id);
        setAvailableFilters(filters);
      } catch {
        setAvailableFilters([]);
      }
      showToast('Dashboard caricata!', 'success');
    } catch {
      showToast('Errore nel caricamento', 'error');
    }
  };

  // --- Delete dashboard ---
  const handleDeleteDashboard = async () => {
    if (!dashToDelete) return;
    try {
      await dashboardApi.remove(dashToDelete);
      if (currentDashboardId === dashToDelete) {
        setCurrentDashboardId(null);
        setCharts([]);
        setGridPositions([]);
        setDashboardName('');
        setAvailableFilters([]);
        setFilterValues({});
      }
      loadSavedDashboards();
      showToast('Dashboard eliminata', 'success');
    } catch {
      showToast('Errore durante eliminazione', 'error');
    }
    setDashToDelete(null);
  };

  // --- Filters ---
  const handleFilterChange = (column: string, value: any) => {
    if (value === undefined || value === '') {
      const next = { ...filterValues };
      delete next[column];
      setFilterValues(next);
    } else {
      setFilterValues({ ...filterValues, [column]: value });
    }
  };

  const handleApplyFilters = async () => {
    if (!currentDashboardId) {
      showToast('Salva la dashboard prima di applicare i filtri', 'info');
      return;
    }
    setIsApplyingFilters(true);
    try {
      const resp = await dashboardApi.applyFilters(currentDashboardId, filterValues);
      setCharts(resp.charts);
      showToast('Filtri applicati!', 'success');
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Errore nei filtri', 'error');
    } finally {
      setIsApplyingFilters(false);
    }
  };

  const handleClearFilters = () => {
    setFilterValues({});
    if (currentDashboardId) {
      handleLoadDashboard(currentDashboardId);
    }
  };

  const handleLoadFilters = async () => {
    if (!currentDashboardId) return;
    try {
      const filters = await dashboardApi.getAvailableFilters(currentDashboardId);
      setAvailableFilters(filters);
      showToast(`${filters.length} filtri disponibili`, 'success');
    } catch {
      setAvailableFilters([]);
    }
  };

  // --- Export ---
  const handleExportImage = async () => {
    if (!canvasRef.current) return;
    showToast('Generazione immagine...', 'info');
    try {
      const html2canvas = (await import('html2canvas')).default;
      const canvas = await html2canvas(canvasRef.current, {
        scale: 2, backgroundColor: '#f8fafc', logging: false,
      });
      const link = document.createElement('a');
      link.download = `${(dashboardName || 'dashboard').replace(/\s+/g, '_')}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      showToast('Immagine esportata!', 'success');
    } catch {
      showToast('Errore export immagine', 'error');
    }
  };

  const handleExportPDF = async () => {
    if (!canvasRef.current) return;
    showToast('Generazione PDF...', 'info');
    try {
      const html2canvas = (await import('html2canvas')).default;
      const { jsPDF } = await import('jspdf');
      const canvas = await html2canvas(canvasRef.current, {
        scale: 2, backgroundColor: '#f8fafc', logging: false,
      });
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        orientation: canvas.width > canvas.height ? 'landscape' : 'portrait',
        unit: 'px',
        format: [canvas.width, canvas.height],
      });
      pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
      pdf.save(`${(dashboardName || 'dashboard').replace(/\s+/g, '_')}.pdf`);
      showToast('PDF esportato!', 'success');
    } catch {
      showToast('Errore export PDF', 'error');
    }
  };

  // --- New dashboard ---
  const handleNewDashboard = () => {
    setCurrentDashboardId(null);
    setCharts([]);
    setGridPositions([]);
    setDashboardName('');
    setNlInput('');
    setAvailableFilters([]);
    setFilterValues({});
  };

  const hasCharts = charts.length > 0;

  return (
    <div className="flex h-full bg-slate-100 overflow-hidden relative">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />

      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={handleDeleteDashboard}
        title="Elimina Dashboard"
        message="Sei sicuro di voler eliminare questa dashboard?"
        confirmText="Elimina"
        variant="danger"
      />

      {/* Save Modal */}
      <Modal isOpen={saveModalOpen} onClose={() => setSaveModalOpen(false)} title="Salva Dashboard" size="sm">
        <div className="space-y-4">
          <div>
            <label className="text-xs font-bold text-slate-600 block mb-2">Nome Dashboard</label>
            <input
              type="text"
              value={saveName || dashboardName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Es: Sales Overview 2024"
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
          </div>
          <button
            onClick={handleSave}
            className="w-full py-3 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:from-orange-600 hover:to-amber-600 transition-all"
          >
            {currentDashboardId ? 'Aggiorna' : 'Salva'}
          </button>
        </div>
      </Modal>

      {/* Chart Selector Modal */}
      <Modal isOpen={chartSelectorOpen} onClose={() => setChartSelectorOpen(false)} title="Seleziona Grafico dalla Galleria" size="lg">
        <div className="grid grid-cols-2 gap-4 max-h-[500px] overflow-y-auto p-1">
          {savedCharts.length === 0 ? (
            <div className="col-span-2 text-center py-8 text-slate-400">
              <p className="text-sm">Nessun grafico salvato</p>
              <p className="text-xs mt-1">Salva grafici dalla Chat per aggiungerli qui</p>
            </div>
          ) : (
            savedCharts.map((c) => (
              <button
                key={c.id}
                onClick={() => handleAddFromGallery(c)}
                className="w-full text-left bg-slate-50 hover:bg-orange-50 rounded-xl transition-all border-2 border-transparent hover:border-orange-300 overflow-hidden group"
              >
                <div className="h-32 bg-white border-b border-slate-100 p-2">
                  {c.plotlyConfig ? (
                    <ChartViewer config={c.plotlyConfig} height={110} />
                  ) : (
                    <div className="h-full flex items-center justify-center text-slate-300">
                      <Icons.BarChart />
                    </div>
                  )}
                </div>
                <div className="p-3">
                  <p className="text-xs font-bold text-slate-800 truncate group-hover:text-orange-700">{c.title}</p>
                  <p className="text-[10px] text-slate-500 mt-1 truncate">{c.description}</p>
                </div>
              </button>
            ))
          )}
        </div>
      </Modal>

      {/* Sidebar - Saved Dashboards */}
      <div className={`border-r border-slate-200 flex flex-col bg-white transition-all duration-300 ${isSidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="p-4 border-b border-slate-100 shrink-0">
          <button
            onClick={handleNewDashboard}
            className="w-full py-3 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:from-orange-600 hover:to-amber-600 transition-all shadow-lg shadow-orange-100 flex items-center justify-center gap-2"
          >
            <Icons.Plus /> Nuova Dashboard
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4 px-2">Dashboard Salvate</h4>
          {savedDashboards.length === 0 ? (
            <p className="text-xs text-slate-400 px-2">Nessuna dashboard salvata</p>
          ) : (
            savedDashboards.map((d) => (
              <div
                key={d.id}
                className={`group w-full flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${
                  d.id === currentDashboardId
                    ? 'bg-orange-50 border border-orange-200 shadow-sm'
                    : 'hover:bg-slate-50 border border-transparent'
                }`}
                onClick={() => handleLoadDashboard(d.id)}
              >
                <div className="flex-1 min-w-0">
                  <span className={`text-[11px] font-bold truncate block ${
                    d.id === currentDashboardId ? 'text-orange-700' : 'text-slate-600'
                  }`}>{d.name}</span>
                  <span className="text-[9px] text-slate-400">{d.charts_count} grafici</span>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDashToDelete(d.id); setDeleteModalOpen(true); }}
                  className="p-1 hover:text-red-500 hover:bg-red-50 rounded transition-all text-slate-400 opacity-0 group-hover:opacity-100"
                  title="Elimina"
                >
                  <Icons.Trash />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Toggle Sidebar */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`absolute bottom-4 z-20 w-8 h-8 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-md hover:bg-slate-50 transition-all ${
          isSidebarOpen ? 'left-[268px]' : 'left-4'
        }`}
      >
        <div className={`transition-transform duration-300 ${isSidebarOpen ? '' : 'rotate-180'}`}>
          <Icons.ChevronLeft />
        </div>
      </button>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* NL Input Bar */}
        <div className="bg-white border-b border-slate-200 px-6 py-4 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <input
                type="text"
                value={nlInput}
                onChange={(e) => setNlInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
                placeholder="Descrivi la dashboard che vuoi creare... (es: 'Dashboard vendite per regione con trend mensile e top prodotti')"
                className="w-full px-5 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent pr-12"
                disabled={isGenerating}
              />
              {isGenerating && (
                <div className="absolute right-4 top-1/2 -translate-y-1/2">
                  <div className="w-5 h-5 border-2 border-orange-200 border-t-orange-600 rounded-full animate-spin" />
                </div>
              )}
            </div>
            <button
              onClick={handleGenerate}
              disabled={!nlInput.trim() || isGenerating}
              className="px-6 py-3 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:from-orange-600 hover:to-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-orange-100"
            >
              {isGenerating ? 'Generando...' : 'Genera Dashboard'}
            </button>
          </div>
        </div>

        {/* Toolbar (shown when charts present) */}
        {hasCharts && (
          <div className="bg-white border-b border-slate-200 px-6 py-3 flex justify-between items-center shrink-0">
            <div className="flex items-center gap-4">
              <h2 className="text-lg font-black text-slate-900">
                {dashboardName || 'Dashboard'}
              </h2>
              <span className="text-[10px] text-slate-400 bg-slate-100 px-3 py-1 rounded-full font-bold">
                {charts.length} grafici
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setChartSelectorOpen(true)}
                className="px-4 py-2 bg-orange-600 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-orange-700 transition-all flex items-center gap-2"
              >
                <Icons.Plus /> Aggiungi
              </button>
              {currentDashboardId && (
                <button
                  onClick={handleLoadFilters}
                  className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-200 transition-all flex items-center gap-2"
                >
                  <Icons.Settings /> Filtri
                </button>
              )}
              <button
                onClick={() => { setSaveName(dashboardName); setSaveModalOpen(true); }}
                className="px-4 py-2 bg-green-600 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-green-700 transition-all flex items-center gap-2"
              >
                <Icons.Save /> Salva
              </button>
              <div className="relative group">
                <button
                  className="px-4 py-2 bg-slate-800 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-900 transition-all flex items-center gap-2"
                >
                  <Icons.Download /> Esporta
                </button>
                <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-30 min-w-[140px]">
                  <button
                    onClick={handleExportPDF}
                    className="w-full px-4 py-2.5 text-left text-xs font-bold text-slate-700 hover:bg-slate-50 rounded-t-xl"
                  >
                    Esporta PDF
                  </button>
                  <button
                    onClick={handleExportImage}
                    className="w-full px-4 py-2.5 text-left text-xs font-bold text-slate-700 hover:bg-slate-50 rounded-b-xl"
                  >
                    Esporta Immagine
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Filter Bar */}
        {hasCharts && (
          <FilterBar
            filters={availableFilters}
            filterValues={filterValues}
            onFilterChange={handleFilterChange}
            onApply={handleApplyFilters}
            onClear={handleClearFilters}
            isApplying={isApplyingFilters}
          />
        )}

        {/* Canvas / Empty State */}
        {!hasCharts ? (
          <div className="flex-1 flex flex-col items-center justify-center opacity-60">
            <div className="w-20 h-20 bg-white rounded-3xl flex items-center justify-center mb-6 shadow-sm">
              <Icons.Layout />
            </div>
            <p className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-2">
              Crea la tua Dashboard
            </p>
            <p className="text-xs text-slate-400 max-w-md text-center leading-relaxed">
              Usa la barra di ricerca sopra per descrivere la dashboard che vuoi generare con AI,
              oppure seleziona una dashboard salvata dalla sidebar.
            </p>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setChartSelectorOpen(true)}
                className="px-5 py-2.5 bg-white border border-slate-200 rounded-xl text-[10px] font-bold text-slate-600 uppercase tracking-widest hover:bg-slate-50 transition-all flex items-center gap-2"
              >
                <Icons.Plus /> Aggiungi da Galleria
              </button>
            </div>
          </div>
        ) : (
          <div
            ref={canvasRef}
            className="flex-1 relative overflow-auto bg-[#f1f5f9] p-6"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-[1400px] mx-auto">
              {charts.map((chart, idx) => {
                const hasData =
                  chart.plotly_config?.data &&
                  chart.plotly_config.data.length > 0 &&
                  chart.plotly_config.data.some((d: any) => {
                    if (d.type === 'indicator') return d.value != null;
                    return (d.x && d.x.length > 0) || (d.y && d.y.length > 0) ||
                           (d.labels && d.labels.length > 0) || (d.values && d.values.length > 0);
                  });

                return (
                  <div
                    key={`chart-${idx}`}
                    className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col hover:shadow-lg transition-shadow"
                  >
                    <div className="px-4 py-3 border-b border-slate-100 flex justify-between items-center bg-slate-50 shrink-0">
                      <h3 className="text-[11px] font-bold text-slate-700 truncate flex-1 uppercase tracking-wide">
                        {chart.title || 'Grafico'}
                      </h3>
                      <button
                        onClick={() => handleRemoveChart(idx)}
                        className="p-1.5 text-slate-400 hover:text-red-500 transition-colors"
                        title="Rimuovi"
                      >
                        <Icons.Trash />
                      </button>
                    </div>
                    <div className="flex-1 p-3 flex items-center justify-center min-h-[280px]">
                      {hasData ? (
                        <ChartViewer config={chart.plotly_config} height={260} />
                      ) : (
                        <div className="text-center text-slate-400">
                          <Icons.BarChart />
                          <p className="text-xs mt-2 font-medium">Nessun dato disponibile</p>
                          <p className="text-[10px] mt-1">Prova a modificare i filtri</p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================
// Helpers
// ============================================================

function buildDefaultGrid(count: number): GridPosition[] {
  const positions: GridPosition[] = [];
  const colWidth = 400;
  const rowHeight = 350;
  const gap = 20;
  for (let i = 0; i < count; i++) {
    const col = i % 2;
    const row = Math.floor(i / 2);
    positions.push({
      index: i,
      x: gap + col * (colWidth + gap),
      y: gap + row * (rowHeight + gap),
      width: colWidth,
      height: rowHeight - gap,
    });
  }
  return positions;
}

export default DashboardManager;
