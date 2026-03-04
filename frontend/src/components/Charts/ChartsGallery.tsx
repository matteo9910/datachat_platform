import React, { useEffect, useState } from 'react';
import { useAppStore } from '../../store/appStore';
import { chartsApi } from '../../api/chartsApi';
import ChartViewer from './ChartViewer';
import { Icons } from '../Layout/Icons';
import { Modal, ConfirmModal } from '../ui/modal';
import { Toast, useToast } from '../ui/toast';

interface ChartDetailModalProps {
  chart: any;
  isOpen: boolean;
  onClose: () => void;
  onModified: (chartId: string, newConfig: any, newSql: string, newTitle?: string) => void;
}

const ChartDetailModal: React.FC<ChartDetailModalProps> = ({ chart, isOpen, onClose, onModified }) => {
  const [activeTab, setActiveTab] = useState<'chart' | 'sql'>('chart');
  const [modifyInput, setModifyInput] = useState('');
  const [isModifying, setIsModifying] = useState(false);
  const [isModifyingVisual, setIsModifyingVisual] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(chart?.plotlyConfig);
  const [currentSql, setCurrentSql] = useState(chart?.sqlTemplate);
  const [currentTitle, setCurrentTitle] = useState(chart?.title);
  const [currentResults, setCurrentResults] = useState<any[]>([]);
  const { toast, showToast, hideToast } = useToast();
  const { llmProvider } = useAppStore();

  useEffect(() => {
    if (chart) {
      setCurrentConfig(chart.plotlyConfig);
      setCurrentSql(chart.sqlTemplate);
      setCurrentTitle(chart.title);
      setCurrentResults([]);
    }
  }, [chart]);

  const handleModify = async () => {
    if (!modifyInput.trim() || isModifying) return;
    
    setIsModifying(true);
    try {
      const result = await chartsApi.modifyWithNL(chart.id, modifyInput, llmProvider);
      if (result.success) {
        setCurrentConfig(result.plotly_config);
        setCurrentSql(result.sql);
        setCurrentResults(result.results || []);
        const newTitle = result.chart_title || result.plotly_config?.layout?.title?.text;
        if (newTitle) {
          setCurrentTitle(newTitle);
        }
        onModified(chart.id, result.plotly_config, result.sql, newTitle);
        showToast('Grafico modificato con successo!', 'success');
        setModifyInput('');
      }
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Errore nella modifica', 'error');
    } finally {
      setIsModifying(false);
    }
  };

  const handleVisualModify = async (request: string) => {
    setIsModifyingVisual(true);
    try {
      const result = await chartsApi.modifyVisualization({
        current_plotly_config: currentConfig,
        modification_request: request,
        sql_query: currentSql,
        original_results: currentResults.length > 0 ? currentResults : [],
        llm_provider: llmProvider
      });
      
      if (result.success && result.plotly_config) {
        setCurrentConfig(result.plotly_config);
        onModified(chart.id, result.plotly_config, currentSql, currentTitle);
        showToast('Grafico modificato!', 'success');
        setModifyInput('');
      }
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Errore nella modifica', 'error');
    } finally {
      setIsModifyingVisual(false);
    }
  };

  const isVisualModification = (text: string): boolean => {
    const visualKeywords = [
      'pie chart', 'bar chart', 'line chart', 'scatter', 'istogramma',
      'etichett', 'label', 'colori', 'color', 'titolo', 'legenda',
      'cambia in', 'trasforma in', 'converti in', 'mostra come',
      'orizzontale', 'verticale', 'percentual', '%', 'ordina'
    ];
    const lowerText = text.toLowerCase();
    return visualKeywords.some(kw => lowerText.includes(kw));
  };

  const handleSmartModify = async () => {
    if (!modifyInput.trim() || isModifying || isModifyingVisual) return;
    
    const request = modifyInput.trim();
    
    if (isVisualModification(request)) {
      await handleVisualModify(request);
    } else {
      await handleModify();
    }
  };

  if (!chart) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={currentTitle || chart.title} size="xl">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />
      
      <div className="flex gap-4 mb-4 border-b border-slate-100 pb-4">
        <button
          onClick={() => setActiveTab('chart')}
          className={`text-xs font-bold uppercase tracking-widest pb-2 border-b-2 transition-all ${
            activeTab === 'chart' ? 'border-orange-600 text-orange-600' : 'border-transparent text-slate-400 hover:text-slate-600'
          }`}
        >
          Grafico
        </button>
        <button
          onClick={() => setActiveTab('sql')}
          className={`text-xs font-bold uppercase tracking-widest pb-2 border-b-2 transition-all ${
            activeTab === 'sql' ? 'border-orange-600 text-orange-600' : 'border-transparent text-slate-400 hover:text-slate-600'
          }`}
        >
          Query SQL
        </button>
      </div>

      {activeTab === 'chart' ? (
        <div className="space-y-4">
          <div className="h-[320px] bg-slate-50 rounded-xl p-4 relative">
            {(isModifyingVisual || isModifying) && (
              <div className="absolute inset-0 bg-white/80 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center z-10">
                <div className="w-8 h-8 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin mb-2"></div>
                <p className="text-sm font-bold text-slate-700">Modificando il grafico...</p>
              </div>
            )}
            <ChartViewer config={currentConfig} height={290} />
          </div>
          
          {/* Pannello unificato Modifica con AI */}
          <div className="bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl p-4 border border-orange-100">
            <h4 className="text-xs font-black text-orange-800 uppercase tracking-widest mb-3 flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              Modifica con AI
            </h4>
            <p className="text-xs text-orange-700 mb-3">Modifica visualizzazione o filtra i dati in linguaggio naturale:</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {['Cambia in pie chart', 'Aggiungi etichette', 'mostrami il 2017', 'ultimi 6 mesi', 'ordina decrescente'].map(suggestion => (
                <button
                  key={suggestion}
                  onClick={() => setModifyInput(suggestion)}
                  disabled={isModifying || isModifyingVisual}
                  className="text-[10px] px-3 py-1.5 bg-white border border-orange-200 rounded-full text-orange-700 hover:bg-orange-100 transition-colors disabled:opacity-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={modifyInput}
                onChange={(e) => setModifyInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSmartModify()}
                placeholder="Es: cambia in pie chart, mostrami il 2018, aggiungi etichette..."
                className="flex-1 px-4 py-3 bg-white border border-orange-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                disabled={isModifying || isModifyingVisual}
              />
              <button
                onClick={handleSmartModify}
                disabled={!modifyInput.trim() || isModifying || isModifyingVisual}
                className="px-6 py-3 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {(isModifying || isModifyingVisual) ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Elaboro...
                  </>
                ) : (
                  'Applica'
                )}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Query SQL</h4>
            <div className="bg-slate-900 rounded-xl p-5 font-mono text-xs leading-relaxed text-slate-100 overflow-x-auto max-h-[200px]">
              <pre className="whitespace-pre-wrap">{currentSql}</pre>
            </div>
            <button
              onClick={() => {
                navigator.clipboard.writeText(currentSql);
                showToast('Query copiata!', 'success');
              }}
              className="mt-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-xl text-xs font-bold hover:bg-slate-200 transition-colors flex items-center gap-2"
            >
              <Icons.Copy /> Copia Query
            </button>
          </div>
          
          {currentResults && currentResults.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                Risultati ({currentResults.length} righe)
              </h4>
              <div className="border border-slate-200 rounded-xl overflow-hidden bg-white max-h-[250px] overflow-y-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="bg-slate-50 border-b border-slate-200 sticky top-0">
                    <tr>
                      {Object.keys(currentResults[0]).map(key => (
                        <th key={key} className="px-4 py-3 font-bold text-slate-700 uppercase whitespace-nowrap">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {currentResults.map((row, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        {Object.values(row).map((value: any, j) => (
                          <td key={j} className="px-4 py-3 text-slate-600 whitespace-nowrap">
                            {String(value)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          
          {currentResults.length === 0 && (
            <div className="text-center py-6 text-slate-400 text-xs">
              <p>Modifica il grafico per visualizzare i risultati della query</p>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

const ChartsGallery: React.FC = () => {
  const { savedCharts, deleteChart, setSavedCharts, updateChart } = useAppStore();
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [chartToDelete, setChartToDelete] = useState<string | null>(null);
  const [selectedChart, setSelectedChart] = useState<any>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const { toast, showToast, hideToast } = useToast();

  useEffect(() => {
    const loadCharts = async () => {
      try {
        const apiCharts = await chartsApi.list();
        const apiChartsMap = new Map(apiCharts.map(c => [c.chart_id, c]));
        
        // Merge: mantieni le modifiche locali, aggiungi nuovi grafici dall'API
        const mergedCharts = savedCharts.map(localChart => {
          // Se il grafico esiste nell'API, mantieni la versione locale (con le modifiche)
          // ma aggiorna solo i campi che non sono stati modificati localmente
          if (apiChartsMap.has(localChart.id)) {
            apiChartsMap.delete(localChart.id); // Rimuovi dalla mappa per tracciare i nuovi
            return localChart; // Mantieni la versione locale con le modifiche
          }
          return localChart;
        });
        
        // Aggiungi i grafici nuovi dall'API che non esistono localmente
        apiChartsMap.forEach((apiChart) => {
          mergedCharts.push({
            id: apiChart.chart_id,
            title: apiChart.title,
            description: apiChart.description || '',
            sqlTemplate: apiChart.sql_template,
            parameters: apiChart.parameters,
            plotlyConfig: apiChart.plotly_config,
            createdAt: new Date(apiChart.created_at)
          });
        });
        
        setSavedCharts(mergedCharts);
      } catch (error) {
        console.error('Error loading charts:', error);
      }
    };
    loadCharts();
  }, []); // Rimuovo setSavedCharts dalle dipendenze per evitare loop

  const handleDeleteClick = (id: string) => {
    setChartToDelete(id);
    setDeleteModalOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!chartToDelete) return;
    try {
      await chartsApi.delete(chartToDelete);
      deleteChart(chartToDelete);
      showToast('Grafico eliminato', 'success');
    } catch (error) {
      showToast('Errore durante eliminazione', 'error');
    }
    setChartToDelete(null);
  };

  const handleViewChart = (chart: any) => {
    setSelectedChart(chart);
    setDetailModalOpen(true);
  };

  const handleChartModified = (chartId: string, newConfig: any, newSql: string, newTitle?: string) => {
    if (updateChart) {
      const updates: any = { plotlyConfig: newConfig, sqlTemplate: newSql };
      if (newTitle) {
        updates.title = newTitle;
      }
      updateChart(chartId, updates);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-8 h-full overflow-y-auto">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />
      
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={handleConfirmDelete}
        title="Elimina Grafico"
        message="Sei sicuro di voler eliminare questo grafico? L'azione non può essere annullata."
        confirmText="Elimina"
        cancelText="Annulla"
        variant="danger"
      />

      <ChartDetailModal
        chart={selectedChart}
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        onModified={handleChartModified}
      />

      <div className="flex justify-between items-center mb-10">
        <div>
          <h2 className="text-3xl font-black text-slate-900 tracking-tight">Galleria Analisi</h2>
          <p className="text-slate-500 text-sm mt-1">Archivio storico di tutti i grafici generati tramite AI.</p>
        </div>
        <div className="flex gap-3">
           <button className="px-5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50 transition-all shadow-sm flex items-center gap-2">
             <Icons.Download /> Scarica Tutti (.zip)
           </button>
        </div>
      </div>

      {savedCharts.length === 0 ? (
        <div className="h-96 flex flex-col items-center justify-center border-2 border-dashed border-slate-200 rounded-[2.5rem] bg-slate-50 text-slate-400">
           <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mb-6 shadow-sm"><Icons.BarChart /></div>
           <p className="text-sm font-bold uppercase tracking-widest">Nessun grafico salvato</p>
           <p className="text-xs mt-2">I grafici salvati dalla chat appariranno qui</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {savedCharts.map((chart) => (
            <div key={chart.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col hover:shadow-xl transition-all duration-500 group">
              <div className="p-5 border-b border-slate-50 flex justify-between items-start">
                <div className="flex-1 cursor-pointer" onClick={() => handleViewChart(chart)}>
                  <h3 className="font-black text-slate-900 text-xs tracking-tight uppercase mb-1 hover:text-orange-600 transition-colors">{chart.title}</h3>
                  <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Creato il {new Date(chart.createdAt).toLocaleDateString()}</p>
                </div>
                <button 
                  onClick={() => handleDeleteClick(chart.id)}
                  className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-600 transition-all p-1.5"
                >
                  <Icons.Trash />
                </button>
              </div>
              <div 
                className="p-6 h-[300px] flex items-center justify-center bg-white cursor-pointer"
                onClick={() => handleViewChart(chart)}
              >
                <ChartViewer config={chart.plotlyConfig} height={250} />
              </div>
              <div className="p-5 bg-slate-50/50 border-t border-slate-100 flex justify-between items-center">
                 <span className="text-[9px] font-bold text-orange-600 bg-orange-100 px-2.5 py-1 rounded-full uppercase">SQL Native</span>
                 <button 
                   onClick={() => handleViewChart(chart)}
                   className="text-[10px] font-bold text-slate-500 hover:text-orange-600 transition-colors uppercase tracking-widest underline decoration-2 underline-offset-4"
                 >
                   Vedi Dettagli
                 </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChartsGallery;