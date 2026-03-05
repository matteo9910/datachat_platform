import React, { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import { chatApi } from '../../api/chatApi';
import { chartsApi } from '../../api/chartsApi';
import { databaseApi, ConnectionStatus } from '../../api/databaseApi';
import { ChatMessage, LLMProvider, ThinkingStep } from '../../types';
import ChartViewer from '../Charts/ChartViewer';
import { Icons } from '../Layout/Icons';
import { Toast, useToast } from '../ui/toast';
import { ConfirmModal } from '../ui/modal';
import SaveToKBButton from '../Knowledge/SaveToKBButton';
import SaveAsViewButton from './SaveAsViewButton';
import VoiceMicButton from '../common/VoiceMicButton';

// Component for saved thinking step in completed messages
const SavedThinkingStepItem: React.FC<{ step: ThinkingStep; index: number }> = ({ step, index }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const getStepLabel = (stepName: string) => {
    const labels: Record<string, string> = {
      'schema_analysis': 'Analisi Schema DB',
      'query_understanding': 'Comprensione Domanda',
      'table_selection': 'Selezione Tabella',
      'column_selection': 'Selezione Colonne',
      'query_logic': 'Logica Query',
      'sql_generation': 'Costruzione Query SQL',
      'sql_execution': 'Esecuzione Query',
      'response_generation': 'Generazione Risposta',
      'chart_generation': 'Generazione Grafico',
      'reasoning_summary': 'Riepilogo Ragionamento'
    };
    return labels[stepName] || stepName;
  };

  const hasDetails = step.details && step.details.length > 0;

  return (
    <div className="rounded-lg bg-slate-50 border border-slate-100">
      <button
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
        className={`w-full flex items-center gap-3 px-3 py-2 text-left ${hasDetails ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <span className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center text-white text-[9px] font-bold">{index + 1}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-700">{getStepLabel(step.step)}</span>
            {step.duration_ms !== undefined && (
              <span className="text-[10px] text-slate-400">({(step.duration_ms / 1000).toFixed(2)}s)</span>
            )}
          </div>
          <p className="text-[10px] text-slate-500 truncate">{step.description}</p>
        </div>
        {hasDetails && (
          <svg className={`w-3 h-3 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
      
      {isExpanded && step.details && (
        <div className="px-3 pb-2 space-y-2 border-t border-slate-200 pt-2 mx-2 mb-1">
          {step.details.map((detail, i) => (
            <div key={i} className="text-[10px]">
              <span className="font-semibold text-slate-600">{detail.title}:</span>
              {typeof detail.content === 'string' ? (
                detail.title === 'Query generata' ? (
                  <pre className="mt-1 p-2 bg-slate-900 text-slate-100 rounded-lg text-[10px] overflow-x-auto whitespace-pre-wrap">{detail.content}</pre>
                ) : (
                  <span className="text-slate-500 ml-1">{detail.content}</span>
                )
              ) : Array.isArray(detail.content) ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {detail.content.map((item: any, j: number) => (
                    <span key={j} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[9px] text-slate-600">
                      {String(item)}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-slate-500 ml-1">{String(detail.content)}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

interface AssistantMessageProps {
  msg: ChatMessage;
  userQuestion?: string;
  onSave: (msg: ChatMessage) => void;
  onSaveSingleChart: (msg: ChatMessage, chartIndex: number) => void;
  onSaveAllCharts: (msg: ChatMessage) => void;
  onModifyChart: (msg: ChatMessage, modification: string) => void;
  onModifySingleChart: (msg: ChatMessage, chartIndex: number, modification: string) => void;
  modifyingMessageId?: string | null;
  modifyingChartIndex?: number | null;
}

const AssistantMessage: React.FC<AssistantMessageProps> = ({ msg, userQuestion, onSave, onSaveSingleChart, onSaveAllCharts, onModifyChart, onModifySingleChart, modifyingMessageId, modifyingChartIndex }) => {
  const [activePage, setActivePage] = useState<'insights' | 'sql'>('insights');
  const [copied, setCopied] = useState(false);
  const [showModifyPanel, setShowModifyPanel] = useState(false);
  const [modifyInput, setModifyInput] = useState('');
  const [activeModifyChartIndex, setActiveModifyChartIndex] = useState<number | null>(null);
  const [chartModifyInputs, setChartModifyInputs] = useState<{[key: number]: string}>({});
  const [showThinking, setShowThinking] = useState(false);
  
  const isModifying = modifyingMessageId === msg.id;

  const handleCopySQL = async () => {
    if (msg.sql) {
      await navigator.clipboard.writeText(msg.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm w-full overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-slate-100 bg-slate-50/50">
        <div className="flex gap-6">
          <button 
            onClick={() => setActivePage('insights')}
            className={`text-[10px] font-bold uppercase tracking-wider pb-1 border-b-2 transition-all ${activePage === 'insights' ? 'border-orange-600 text-orange-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
          >
            Insight e Grafico
          </button>
          <button 
            onClick={() => setActivePage('sql')}
            className={`text-[10px] font-bold uppercase tracking-wider pb-1 border-b-2 transition-all ${activePage === 'sql' ? 'border-orange-600 text-orange-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
          >
            Query SQL
          </button>
        </div>
        <div className="flex items-center gap-2">
           <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
           <span className="text-[10px] text-slate-400 font-mono">Generato in {((msg.executionTimeMs || 0) / 1000).toFixed(1)}s</span>
        </div>
      </div>

      <div className="px-5 py-4">
        {activePage === 'insights' ? (
          <div className="space-y-5">
            {/* CR4: Come ho ragionato - Expandable con Thought Process finale */}
            {(msg.thinkingSteps && msg.thinkingSteps.length > 0) || (msg.thoughtProcess && msg.thoughtProcess.length > 0) ? (
              <div className="mb-4">
                <button
                  onClick={() => setShowThinking(!showThinking)}
                  className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-all"
                >
                  <svg className={`w-3 h-3 transition-transform ${showThinking ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  <span className="font-semibold">Come ho ragionato</span>
                  <span className="text-slate-400">({(msg.thinkingSteps?.length || 0) + (msg.thoughtProcess ? 1 : 0)} sezioni)</span>
                </button>
                {showThinking && (
                  <div className="mt-3 space-y-2">
                    {/* Step tecnici */}
                    {msg.thinkingSteps?.map((step, i) => (
                      <SavedThinkingStepItem key={i} step={step} index={i} />
                    ))}
                    
                    {/* Thought Process - Come blocco standard espandibile */}
                    {msg.thoughtProcess && msg.thoughtProcess.length > 0 && (
                      <SavedThinkingStepItem 
                        step={{
                          step: "reasoning_summary",
                          description: "Riepilogo del ragionamento completo",
                          status: "completed",
                          details: msg.thoughtProcess.map((thought) => {
                            // Parse "TITLE: Description" format
                            const colonIndex = thought.indexOf(':');
                            if (colonIndex > 0 && colonIndex < 60) {
                              return {
                                title: thought.substring(0, colonIndex).trim(),
                                content: thought.substring(colonIndex + 1).trim()
                              };
                            }
                            return { title: "Step", content: thought };
                          })
                        }} 
                        index={(msg.thinkingSteps?.length || 0)} 
                      />
                    )}
                  </div>
                )}
              </div>
            ) : null}
            
            <div className="max-w-none text-slate-700 text-[13.5px] leading-[1.7]">
              {(() => {
                const parseBold = (text: string) => {
                  const parts = text.split(/(\*\*[^*]+\*\*|__[^_]+__)/g);
                  return parts.map((part, j) => {
                    if (part.startsWith('**') && part.endsWith('**')) {
                      return <strong key={j} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
                    }
                    if (part.startsWith('__') && part.endsWith('__')) {
                      return <strong key={j} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
                    }
                    return part;
                  });
                };

                return msg.text.split('\n').map((line, i) => {
                  const trimmed = line.trim();

                  // Numbered item (e.g. "1. **Product Name** — 73.690 units")
                  const isNumbered = /^\d+\.\s/.test(trimmed);
                  // Sub-bullet (e.g. "- Consumer: 28.144" or "• Consumer: 28.144")
                  const isSubBullet = trimmed.startsWith('- ') || trimmed.startsWith('• ');
                  // Empty line
                  if (trimmed === '') {
                    return <div key={i} className="h-3" />;
                  }

                  if (isNumbered) {
                    return (
                      <div key={i} className="mt-3 mb-1 font-medium text-slate-800">
                        {parseBold(trimmed)}
                      </div>
                    );
                  }

                  if (isSubBullet) {
                    const bulletText = trimmed.replace(/^[-•]\s*/, '');
                    return (
                      <div key={i} className="flex items-start gap-2 ml-5 py-[1px]">
                        <span className="text-orange-500 mt-[3px] text-[10px] flex-shrink-0">●</span>
                        <span className="text-slate-600">{parseBold(bulletText)}</span>
                      </div>
                    );
                  }

                  return <p key={i} className="mb-2">{parseBold(trimmed)}</p>;
                });
              })()}
            </div>
            {/* Multi-visualization support */}
            {msg.charts && msg.charts.length > 0 ? (
              <div className="space-y-6">
                <div className="flex justify-between items-center px-1">
                  <h3 className="text-[10px] font-bold text-slate-900 uppercase tracking-widest">
                    Visualizzazioni ({msg.charts.length})
                  </h3>
                  <button 
                    onClick={() => onSaveAllCharts(msg)}
                    className="px-4 py-1.5 bg-orange-600 text-white rounded-lg text-[10px] font-bold hover:bg-orange-700 transition-all shadow-md shadow-orange-100 flex items-center gap-2"
                  >
                    <Icons.Save /> Salva Tutti
                  </button>
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {msg.charts.map((chartItem: any, idx: number) => {
                    const isChartModifying = modifyingMessageId === msg.id && modifyingChartIndex === idx;
                    const showChartModifyPanel = activeModifyChartIndex === idx;
                    
                    return (
                      <div key={idx} className="p-4 bg-white border border-slate-200 rounded-2xl">
                        <div className="flex justify-between items-center mb-3">
                          <span className="text-[10px] font-bold text-slate-500 uppercase truncate flex-1">
                            {chartItem.chart_title || `Visualizzazione ${idx + 1}`}
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-[9px] px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">
                              {chartItem.chart_type}
                            </span>
                            <button
                              onClick={() => setActiveModifyChartIndex(showChartModifyPanel ? null : idx)}
                              className={`p-1.5 rounded-lg transition-all ${showChartModifyPanel ? 'text-orange-600 bg-orange-50' : 'text-slate-400 hover:text-blue-600 hover:bg-blue-50'}`}
                              title="Modifica grafico"
                            >
                              <Icons.Edit />
                            </button>
                            <button
                              onClick={() => onSaveSingleChart(msg, idx)}
                              className="p-1.5 text-slate-400 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all"
                              title="Salva questo grafico"
                            >
                              <Icons.Save />
                            </button>
                          </div>
                        </div>
                        
                        {showChartModifyPanel && (
                          <div className="mb-3 p-3 bg-slate-50 rounded-xl border border-slate-200">
                            <p className="text-[10px] text-slate-500 mb-2">
                              Descrivi come vuoi modificare questo grafico:
                            </p>
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={chartModifyInputs[idx] || ''}
                                onChange={(e) => setChartModifyInputs({...chartModifyInputs, [idx]: e.target.value})}
                                placeholder="Es: Trasforma in pie chart..."
                                className="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-orange-500"
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' && chartModifyInputs[idx]?.trim() && !isChartModifying) {
                                    onModifySingleChart(msg, idx, chartModifyInputs[idx].trim());
                                  }
                                }}
                                disabled={isChartModifying}
                              />
                              <button
                                onClick={() => {
                                  if (chartModifyInputs[idx]?.trim() && !isChartModifying) {
                                    onModifySingleChart(msg, idx, chartModifyInputs[idx].trim());
                                  }
                                }}
                                disabled={!chartModifyInputs[idx]?.trim() || isChartModifying}
                                className="px-3 py-2 bg-orange-600 text-white rounded-lg text-[10px] font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-1"
                              >
                                {isChartModifying ? (
                                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                ) : (
                                  <>
                                    <Icons.Edit /> Applica
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        )}
                        
                        {/* Se il chart è di tipo table, mostra tabella React invece di Plotly */}
                        {(chartItem.chart_type === 'table' || chartItem.plotly_config?.data?.[0]?.type === 'table') && msg.results && msg.results.length > 0 ? (
                          <div className="border border-slate-200 rounded-xl bg-white max-h-[300px] overflow-x-auto overflow-y-auto">
                            <table className="min-w-full text-left text-[11px]">
                              <thead className="bg-slate-800 sticky top-0 z-10">
                                <tr>
                                  {Object.keys(msg.results[0]).map(k => (
                                    <th key={k} className="px-4 py-3 font-bold text-white uppercase tracking-wide whitespace-nowrap">
                                      {k.replace(/_/g, ' ')}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-100">
                                {msg.results.map((row, ri) => (
                                  <tr key={ri} className={`hover:bg-slate-50 ${ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}`}>
                                    {Object.entries(row).map(([, v]: [string, any], j) => (
                                      <td key={j} className="px-4 py-3 text-slate-600 whitespace-nowrap">{typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('it-IT') : v.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) : String(v ?? '-')}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <ChartViewer 
                            config={chartItem.plotly_config} 
                            height={chartItem.chart_type === 'kpi' || chartItem.chart_type === 'indicator' ? 150 : chartItem.chart_type === 'pie_with_filter' ? 400 : 280} 
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : msg.chart && (
              <div className="space-y-4">
                <div className="flex justify-between items-center px-1">
                  <h3 className="text-[10px] font-bold text-slate-900 uppercase tracking-widest">Visualizzazione</h3>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => setShowModifyPanel(!showModifyPanel)}
                      className={`px-4 py-1.5 rounded-lg text-[10px] font-bold transition-all flex items-center gap-2 ${
                        showModifyPanel 
                          ? 'bg-slate-700 text-white' 
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                      }`}
                    >
                       <Icons.Edit /> Modifica Grafico
                    </button>
                    <button 
                      onClick={() => onSave(msg)}
                      className="px-4 py-1.5 bg-orange-600 text-white rounded-lg text-[10px] font-bold hover:bg-orange-700 transition-all shadow-md shadow-orange-100 flex items-center gap-2"
                    >
                       <Icons.Save /> Salva Grafico
                    </button>
                  </div>
                </div>
                
                {showModifyPanel && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <p className="text-xs text-slate-600">
                      Descrivi come vuoi modificare il grafico (es: "cambia in pie chart", "aggiungi etichette", "mostra i valori percentuali"):
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={modifyInput}
                        onChange={(e) => setModifyInput(e.target.value)}
                        placeholder="Es: Trasforma in pie chart con etichette..."
                        className="flex-1 bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && modifyInput.trim() && !isModifying) {
                            onModifyChart(msg, modifyInput.trim());
                          }
                        }}
                        disabled={isModifying}
                      />
                      <button
                        onClick={() => {
                          if (modifyInput.trim() && !isModifying) {
                            onModifyChart(msg, modifyInput.trim());
                          }
                        }}
                        disabled={!modifyInput.trim() || isModifying}
                        className="px-4 py-2 bg-orange-600 text-white rounded-lg text-xs font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
                      >
                        {isModifying ? (
                          <>
                            <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                            Modificando...
                          </>
                        ) : (
                          <>
                            <Icons.Refresh /> Applica
                          </>
                        )}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {['Cambia in pie chart', 'Aggiungi etichette sui valori', 'Mostra valori %', 'Cambia in line chart', 'Ordina decrescente'].map((suggestion) => (
                        <button
                          key={suggestion}
                          onClick={() => setModifyInput(suggestion)}
                          disabled={isModifying}
                          className="px-3 py-1 bg-white border border-slate-200 rounded-full text-[10px] text-slate-600 hover:bg-orange-50 hover:border-orange-300 hover:text-orange-700 transition-all disabled:opacity-50"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="p-4 bg-white border border-slate-100 rounded-2xl relative">
                  {isModifying && (
                    <div className="absolute inset-0 bg-white/80 backdrop-blur-sm rounded-2xl flex flex-col items-center justify-center z-10">
                      <div className="w-10 h-10 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin mb-3"></div>
                      <p className="text-sm font-bold text-slate-700">Modificando il grafico...</p>
                      <p className="text-xs text-slate-500 mt-1">Attendere prego</p>
                    </div>
                  )}
                  {/* Se il chart è di tipo table, mostra tabella React invece di Plotly */}
                  {(msg.chartType === 'table' || msg.chart?.data?.[0]?.type === 'table') && msg.results && msg.results.length > 0 ? (
                    <div className="border border-slate-200 rounded-xl overflow-hidden bg-white max-h-[400px] overflow-y-auto">
                      <table className="w-full text-left text-[11px]">
                        <thead className="bg-slate-800 sticky top-0">
                          <tr>
                            {Object.keys(msg.results[0]).map(k => (
                              <th key={k} className="px-4 py-3 font-bold text-white uppercase tracking-wide">
                                {k.replace(/_/g, ' ')}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {msg.results.map((row, i) => (
                            <tr key={i} className={`hover:bg-slate-50 ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}`}>
                              {Object.values(row).map((v: any, j) => (
                                <td key={j} className="px-4 py-3 text-slate-600">{String(v ?? '-')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <ChartViewer config={msg.chart} height={350} />
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-6">
             <div>
               <div className="flex items-center justify-between mb-3">
                 <h3 className="text-[10px] font-bold text-slate-900 uppercase tracking-widest">Query SQL Generata</h3>
                 {msg.sql && (
                   <div className="flex items-center gap-1">
                     <SaveToKBButton question={userQuestion || ''} sql={msg.sql} />
                     <SaveAsViewButton sql={msg.sql} />
                   </div>
                 )}
               </div>
               <div className="bg-slate-900 rounded-xl p-5 font-mono text-xs leading-relaxed text-slate-100 overflow-x-auto relative">
                 <button
                   onClick={handleCopySQL}
                   className="absolute top-3 right-3 p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-all"
                   title={copied ? 'Copiato!' : 'Copia SQL'}
                 >
                   {copied ? <Icons.Check /> : <Icons.Copy />}
                 </button>
                 <pre className="whitespace-pre-wrap pr-10">{msg.sql}</pre>
               </div>
             </div>
             {msg.results && msg.results.length > 0 && (
               <div className="space-y-3">
                  <h3 className="text-[10px] font-bold text-slate-900 uppercase tracking-widest">Risultato Query ({msg.results.length} righe)</h3>
                  <div className="border border-slate-200 rounded-xl bg-white max-h-[400px] overflow-x-auto overflow-y-auto">
                    <table className="min-w-full text-left text-[11px]">
                      <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                        <tr>{Object.keys(msg.results[0]).map(k => <th key={k} className="px-4 py-3 font-bold text-slate-700 uppercase whitespace-nowrap">{k}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {msg.results.map((row, i) => (
                          <tr key={i} className="hover:bg-slate-50">{Object.entries(row).map(([, v]: [string, any], j) => <td key={j} className="px-4 py-3 text-slate-600 whitespace-nowrap">{typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('it-IT') : v.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) : String(v ?? '-')}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
               </div>
             )}
          </div>
        )}
      </div>
    </div>
  );
};

// Component for live thinking step during loading
const LiveThinkingStepItem: React.FC<{ step: ThinkingStep; index: number }> = ({ step }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const getStepIcon = (status: string) => {
    if (status === 'running') {
      return <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />;
    }
    if (status === 'completed') {
      return <div className="w-4 h-4 bg-green-500 rounded-full flex items-center justify-center text-white text-[10px]">✓</div>;
    }
    if (status === 'error') {
      return <div className="w-4 h-4 bg-red-500 rounded-full flex items-center justify-center text-white text-[10px]">✗</div>;
    }
    return <div className="w-4 h-4 bg-slate-200 rounded-full" />;
  };

  const getStepLabel = (stepName: string) => {
    const labels: Record<string, string> = {
      'schema_analysis': 'Analisi Schema DB',
      'query_understanding': 'Comprensione Domanda',
      'table_selection': 'Selezione Tabella',
      'column_selection': 'Selezione Colonne',
      'query_logic': 'Logica Query',
      'sql_generation': 'Costruzione Query SQL',
      'sql_execution': 'Esecuzione Query',
      'response_generation': 'Generazione Risposta',
      'chart_generation': 'Generazione Grafico',
      'reasoning_summary': 'Riepilogo Ragionamento'
    };
    return labels[stepName] || stepName;
  };

  return (
    <div className={`rounded-xl transition-all ${step.status === 'running' ? 'bg-orange-50 border border-orange-200' : 'bg-slate-50 border border-slate-100'}`}>
      <button
        onClick={() => step.details && setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        {getStepIcon(step.status)}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold ${step.status === 'running' ? 'text-orange-700' : step.status === 'completed' ? 'text-slate-700' : 'text-slate-500'}`}>
              {getStepLabel(step.step)}
            </span>
            {step.duration_ms !== undefined && step.status === 'completed' && (
              <span className="text-[10px] text-slate-400">({(step.duration_ms / 1000).toFixed(2)}s)</span>
            )}
          </div>
          <p className={`text-[11px] ${step.status === 'running' ? 'text-orange-600' : 'text-slate-500'}`}>
            {step.description}
          </p>
        </div>
        {step.details && step.details.length > 0 && (
          <svg className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
      
      {isExpanded && step.details && (
        <div className="px-4 pb-3 space-y-2 border-t border-slate-200 pt-2 mx-3 mb-2">
          {step.details.map((detail, i) => (
            <div key={i} className="text-[11px]">
              <span className="font-semibold text-slate-600">{detail.title}:</span>
              {typeof detail.content === 'string' ? (
                <span className="text-slate-500 ml-1">{detail.content}</span>
              ) : Array.isArray(detail.content) ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {detail.content.map((item: any, j: number) => (
                    <span key={j} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[10px] text-slate-600">
                      {String(item)}
                    </span>
                  ))}
                </div>
              ) : (
                <pre className="mt-1 p-2 bg-slate-900 text-slate-100 rounded-lg text-[10px] overflow-x-auto">
                  {JSON.stringify(detail.content, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ChatInterface: React.FC = () => {
  const { sessions, currentSessionId, addMessage, newChat, switchSession, deleteSession, saveChart, isLoading, setLoading, llmProvider, updateSessionTitle, updateMessage, language, setLanguage } = useAppStore();
  const [input, setInput] = useState('');
  const [modifyingMessageId, setModifyingMessageId] = useState<string | null>(null);
  const [modifyingChartIndex, setModifyingChartIndex] = useState<number | null>(null);
  const [dbStatus, setDbStatus] = useState<ConnectionStatus | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState<string[]>([]);
  const [isLangDropdownOpen, setIsLangDropdownOpen] = useState(false);
  const [liveThinkingSteps, setLiveThinkingSteps] = useState<ThinkingStep[]>([]);
  const liveThinkingStepsRef = useRef<ThinkingStep[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const langDropdownRef = useRef<HTMLDivElement>(null);
  const { toast, showToast, hideToast } = useToast();

  // Close language dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (langDropdownRef.current && !langDropdownRef.current.contains(event.target as Node)) {
        setIsLangDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentSession = sessions.find(s => s.id === currentSessionId) || sessions[0];

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [currentSession?.messages]);

  useEffect(() => {
    const loadDbStatus = async () => {
      try {
        const status = await databaseApi.getStatus();
        setDbStatus(status);
      } catch (e) {
        console.error('Error loading db status:', e);
      }
    };
    loadDbStatus();
  }, []);

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLiveThinkingSteps([]);
    liveThinkingStepsRef.current = [];
    setLoading(false);
    addMessage({
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      text: 'Elaborazione interrotta.',
      timestamp: new Date()
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: input, timestamp: new Date() };
    addMessage(userMsg);
    
    if (currentSession.messages.length === 0) {
      updateSessionTitle(currentSessionId, input.slice(0, 40) + (input.length > 40 ? '...' : ''));
    }
    
    const queryText = input;
    setInput('');
    setLoading(true);
    setLiveThinkingSteps([]);
    liveThinkingStepsRef.current = [];
    
    const controller = new AbortController();
    abortControllerRef.current = controller;
    
    try {
      // Use streaming API for real-time thinking steps
      await chatApi.queryStream(
        {
          query: queryText,
          session_id: currentSessionId,
          llm_provider: llmProvider,
          include_chart: true
        },
        // onThinkingStep - update live thinking steps
        (step) => {
          setLiveThinkingSteps(prev => {
            const existing = prev.findIndex(s => s.step === step.step);
            let newSteps;
            if (existing >= 0) {
              // Update existing step
              newSteps = [...prev];
              newSteps[existing] = step;
            } else {
              newSteps = [...prev, step];
            }
            // Keep ref in sync for access in onResult callback
            liveThinkingStepsRef.current = newSteps;
            return newSteps;
          });
        },
        // onResult - final result
        (response) => {
          // Use ref to get the latest thinking steps (not stale closure value)
          const finalThinkingSteps = liveThinkingStepsRef.current;
          
          const assistantMsg: ChatMessage = {
            id: (Date.now() + 1).toString(),
            role: 'assistant',
            text: response.nl_response,
            sql: response.sql,
            results: response.results,
            chart: response.should_show_chart ? (response.chart as any)?.plotly_config : undefined,
            chartType: response.should_show_chart ? (response.chart as any)?.chart_type : undefined,
            charts: response.should_show_chart ? ((response.chart as any)?.charts || undefined) : undefined,
            timestamp: new Date(),
            executionTimeMs: response.execution_time_ms,
            thinkingSteps: finalThinkingSteps.length > 0 ? [...finalThinkingSteps] : undefined,
            thoughtProcess: response.thought_process,
            suggestedFollowups: response.suggested_followups
          };
          
          addMessage(assistantMsg);
          setLiveThinkingSteps([]);
          liveThinkingStepsRef.current = [];
          
          if (response.suggested_followups) {
            setSuggestedFollowups(response.suggested_followups);
          }
          setLoading(false);
        },
        // onError
        (error) => {
          const errorMsg: ChatMessage = {
            id: (Date.now() + 1).toString(),
            role: 'assistant',
            text: `Errore: ${error}`,
            timestamp: new Date()
          };
          addMessage(errorMsg);
          setLiveThinkingSteps([]);
          setLoading(false);
        },
        controller.signal
      );
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // L'utente ha interrotto - gia' gestito in handleStop
        return;
      }
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        text: `Errore: ${error.message || 'Impossibile elaborare la richiesta'}`,
        timestamp: new Date()
      };
      addMessage(errorMsg);
      setLiveThinkingSteps([]);
      setLoading(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleSaveChart = async (msg: ChatMessage) => {
    if (!msg.chart || !msg.sql) return;
    
    try {
      const chartTitle = msg.chart?.layout?.title?.text || msg.text.slice(0, 50);
      
      const result = await chartsApi.save({
        title: chartTitle,
        description: 'Auto-generato dalla chat',
        sql_template: msg.sql,
        parameters: {},
        plotly_config: msg.chart
      });
      
      saveChart({
        id: result.chart_id,
        title: chartTitle,
        description: 'Auto-generato dalla chat',
        sqlTemplate: msg.sql,
        parameters: {},
        plotlyConfig: msg.chart,
        createdAt: new Date()
      });
      
      showToast('Grafico salvato con successo!', 'success');
    } catch (error) {
      showToast('Errore nel salvataggio del grafico', 'error');
    }
  };

  const handleSaveSingleChart = async (msg: ChatMessage, chartIndex: number) => {
    if (!msg.charts || !msg.charts[chartIndex] || !msg.sql) return;
    
    const chartItem = msg.charts[chartIndex];
    const chartTitle = chartItem.chart_title || `Visualizzazione ${chartIndex + 1}`;
    
    try {
      const result = await chartsApi.save({
        title: chartTitle,
        description: 'Auto-generato dalla chat',
        sql_template: msg.sql,
        parameters: {},
        plotly_config: chartItem.plotly_config
      });
      
      saveChart({
        id: result.chart_id,
        title: chartTitle,
        description: 'Auto-generato dalla chat',
        sqlTemplate: msg.sql,
        parameters: {},
        plotlyConfig: chartItem.plotly_config,
        createdAt: new Date()
      });
      
      showToast(`Grafico "${chartTitle}" salvato!`, 'success');
    } catch (error) {
      showToast('Errore nel salvataggio del grafico', 'error');
    }
  };

  const handleSaveAllCharts = async (msg: ChatMessage) => {
    if (!msg.charts || msg.charts.length === 0 || !msg.sql) return;
    
    let savedCount = 0;
    
    for (let i = 0; i < msg.charts.length; i++) {
      const chartItem = msg.charts[i];
      const chartTitle = chartItem.chart_title || `Visualizzazione ${i + 1}`;
      
      try {
        const result = await chartsApi.save({
          title: chartTitle,
          description: 'Auto-generato dalla chat',
          sql_template: msg.sql,
          parameters: {},
          plotly_config: chartItem.plotly_config
        });
        
        saveChart({
          id: result.chart_id,
          title: chartTitle,
          description: 'Auto-generato dalla chat',
          sqlTemplate: msg.sql,
          parameters: {},
          plotlyConfig: chartItem.plotly_config,
          createdAt: new Date()
        });
        
        savedCount++;
      } catch (error) {
        console.error(`Errore salvataggio grafico ${i}:`, error);
      }
    }
    
    if (savedCount === msg.charts.length) {
      showToast(`Tutti i ${savedCount} grafici salvati!`, 'success');
    } else if (savedCount > 0) {
      showToast(`Salvati ${savedCount} di ${msg.charts.length} grafici`, 'info');
    } else {
      showToast('Errore nel salvataggio dei grafici', 'error');
    }
  };

  const handleModifyChart = async (msg: ChatMessage, modification: string) => {
    // Per le tabelle, accettiamo anche se msg.chart è undefined (usiamo i results)
    const isTable = msg.chartType === 'table' || msg.chart?.data?.[0]?.type === 'table';
    
    if (!isTable && !msg.chart) return;
    if (!msg.sql) return;
    
    setModifyingMessageId(msg.id);
    
    try {
      // Per le tabelle, costruisci una config Plotly table dai results
      let chartConfig = msg.chart;
      if (isTable && msg.results && msg.results.length > 0) {
        const headers = Object.keys(msg.results[0]);
        const cells = headers.map(h => msg.results!.map(r => r[h]));
        chartConfig = {
          data: [{
            type: 'table',
            header: { values: headers },
            cells: { values: cells }
          }],
          layout: { title: { text: 'Tabella Dati' } }
        };
      }
      
      const response = await chartsApi.modifyVisualization({
        current_plotly_config: chartConfig,
        modification_request: modification,
        sql_query: msg.sql,
        original_results: msg.results || [],
        llm_provider: llmProvider
      });
      
      if (response.plotly_config) {
        const updatedMsg: ChatMessage = {
          ...msg,
          chart: response.plotly_config,
          // Per le tabelle, aggiorna anche i results se modificati
          results: (response as any).modified_results || msg.results
        };
        updateMessage(msg.id, updatedMsg);
        showToast('Visualizzazione modificata!', 'success');
      } else {
        showToast('Impossibile modificare la visualizzazione', 'error');
      }
    } catch (error: any) {
      console.error('Modify chart error:', error);
      showToast('Errore nella modifica della visualizzazione', 'error');
    } finally {
      setModifyingMessageId(null);
    }
  };

  const handleModifySingleChart = async (msg: ChatMessage, chartIndex: number, modification: string) => {
    if (!msg.charts || !msg.charts[chartIndex]) return;
    
    const chartItem = msg.charts[chartIndex];
    
    setModifyingMessageId(msg.id);
    setModifyingChartIndex(chartIndex);
    
    try {
      const response = await chartsApi.modifyVisualization({
        current_plotly_config: chartItem.plotly_config,
        modification_request: modification,
        sql_query: chartItem.sql || msg.sql,
        original_results: msg.results || [],
        llm_provider: llmProvider
      });
      
      if (response.plotly_config) {
        const updatedCharts = [...msg.charts];
        updatedCharts[chartIndex] = {
          ...chartItem,
          plotly_config: response.plotly_config,
          chart_type: response.plotly_config?.data?.[0]?.type || chartItem.chart_type
        };
        
        const updatedMsg: ChatMessage = {
          ...msg,
          charts: updatedCharts
        };
        updateMessage(msg.id, updatedMsg);
        showToast('Grafico modificato!', 'success');
      } else {
        showToast('Impossibile modificare il grafico', 'error');
      }
    } catch (error: any) {
      console.error('Modify single chart error:', error);
      showToast('Errore nella modifica del grafico', 'error');
    } finally {
      setModifyingMessageId(null);
      setModifyingChartIndex(null);
    }
  };

  return (
    <div className="flex h-full bg-white relative">
      {/* Toast notification */}
      <Toast 
        message={toast.message} 
        type={toast.type} 
        isVisible={toast.isVisible} 
        onClose={hideToast} 
      />

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setSessionToDelete(null);
        }}
        onConfirm={() => {
          if (sessionToDelete) {
            deleteSession(sessionToDelete);
            showToast('Conversazione eliminata', 'success');
          }
          setSessionToDelete(null);
        }}
        title="Elimina Conversazione"
        message="Sei sicuro di voler eliminare questa conversazione? L'azione non può essere annullata."
        confirmText="Elimina"
        cancelText="Annulla"
        variant="danger"
      />
      
      {/* Session History Sidebar */}
      <div className={`border-r border-slate-100 flex flex-col bg-slate-50/30 transition-all duration-300 ${isSidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="p-4 border-b border-slate-100">
          <button 
            onClick={newChat}
            className="w-full flex items-center justify-center gap-2 py-3 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-700 hover:bg-slate-50 transition-all shadow-sm group"
          >
            <span className="text-orange-600 group-hover:scale-110 transition-transform"><Icons.Plus /></span>
            Nuova Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
           <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4 px-2">Cronologia</h4>
           {sessions.map(s => (
             <div
               key={s.id}
               className={`group w-full text-left p-3 rounded-xl transition-all cursor-pointer ${s.id === currentSessionId ? 'bg-white border border-slate-200 shadow-sm' : 'hover:bg-slate-100/50'}`}
               onClick={() => switchSession(s.id)}
             >
               <div className="flex items-start justify-between gap-2">
                 <div className="flex-1 min-w-0">
                   <p className={`text-[11px] font-bold truncate ${s.id === currentSessionId ? 'text-slate-900' : 'text-slate-500'}`}>{s.title}</p>
                   <p className="text-[9px] text-slate-400 mt-1">{new Date(s.updatedAt).toLocaleDateString()}</p>
                 </div>
                 <button
                   onClick={(e) => {
                     e.stopPropagation();
                     setSessionToDelete(s.id);
                     setDeleteModalOpen(true);
                   }}
                   className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-300 hover:text-red-500 transition-all rounded-lg hover:bg-red-50"
                   title="Elimina conversazione"
                 >
                   <Icons.Trash />
                 </button>
               </div>
             </div>
           ))}
        </div>
      </div>

      {/* Toggle Sidebar Button */}
      <button 
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`absolute bottom-4 z-20 w-8 h-8 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-md hover:bg-slate-50 transition-all ${isSidebarOpen ? 'left-[268px]' : 'left-4'}`}
      >
        <div className={`transition-transform duration-300 ${isSidebarOpen ? '' : 'rotate-180'}`}>
          <Icons.ChevronLeft />
        </div>
      </button>

      {/* Chat View */}
      <div className="flex-1 flex flex-col h-full bg-[#fdfdfd] relative">
        <div className="flex-1 overflow-y-auto py-6" ref={scrollRef}>
         <div className="max-w-3xl mx-auto px-6 space-y-5">
          {currentSession?.messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center opacity-40 select-none">
              <div className="w-20 h-20 bg-slate-100 rounded-3xl flex items-center justify-center mb-6">
                <Icons.MessageSquare />
              </div>
              <p className="text-sm font-bold uppercase tracking-widest text-slate-500">Chiedi un'analisi per iniziare</p>
              <p className="text-xs text-slate-400 mt-2">Es: "Vendite totali per regione"</p>
            </div>
          )}
          {currentSession?.messages.map((msg, idx) => {
            // Find the preceding user message for SaveToKB context
            const prevUserMsg = msg.role === 'assistant'
              ? currentSession.messages.slice(0, idx).reverse().find(m => m.role === 'user')
              : undefined;
            return (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'user' ? (
                <div className="bg-slate-900 text-white px-5 py-3 rounded-2xl rounded-tr-none shadow-lg shadow-slate-200 max-w-[85%]">
                  <p className="text-sm font-medium leading-relaxed">{msg.text}</p>
                </div>
              ) : (
                <AssistantMessage 
                  msg={msg}
                  userQuestion={prevUserMsg?.text}
                  onSave={handleSaveChart} 
                  onSaveSingleChart={handleSaveSingleChart}
                  onSaveAllCharts={handleSaveAllCharts}
                  onModifyChart={handleModifyChart}
                  onModifySingleChart={handleModifySingleChart}
                  modifyingMessageId={modifyingMessageId}
                  modifyingChartIndex={modifyingChartIndex}
                />
              )}
            </div>
            );
          })}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm w-full max-w-[95%] overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-orange-600 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                      <div className="w-2 h-2 bg-orange-600 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                      <div className="w-2 h-2 bg-orange-600 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
                    </div>
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">AI sta ragionando...</span>
                  </div>
                </div>
                {liveThinkingSteps.length > 0 && (
                  <div className="p-4 space-y-2">
                    {liveThinkingSteps.map((step, idx) => (
                      <LiveThinkingStepItem key={step.step} step={step} index={idx} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
         </div>
        </div>

        <div className="border-t border-slate-100 bg-white py-4 px-6">
         <div className="max-w-3xl mx-auto">
          {/* Status Bar */}
          <div className="flex items-center gap-3 mb-3">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 rounded-lg">
                <Icons.Database />
                {dbStatus?.connected && dbStatus?.active_database ? (
                  <>
                    <span className="text-xs font-semibold text-slate-700">{dbStatus.active_database}</span>
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  </>
                ) : (
                  <>
                    <span className="text-xs font-semibold text-red-600">Non connesso</span>
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                  </>
                )}
              </div>

              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
                llmProvider === LLMProvider.CLAUDE ? 'bg-orange-100 text-orange-700' :
                llmProvider === LLMProvider.AZURE ? 'bg-blue-100 text-blue-700' :
                'bg-purple-100 text-purple-700'
              }`}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
                <span className="text-xs font-semibold">
                  {llmProvider === LLMProvider.CLAUDE ? 'Claude Sonnet 4.6' :
                   llmProvider === LLMProvider.AZURE ? 'GPT-4.1' : 'GPT-5.2'}
                </span>
              </div>

              <div className="relative" ref={langDropdownRef}>
                <button
                  type="button"
                  onClick={() => setIsLangDropdownOpen(!isLangDropdownOpen)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl hover:border-slate-300 transition-all"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-500">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1 4-10 15.3 15.3 0 0 1 4-10z"/>
                  </svg>
                  <span className="text-xs font-semibold text-slate-700">
                    {language === 'it' ? 'Italiano' : 'English'}
                  </span>
                  <svg className={`w-3 h-3 text-slate-400 transition-transform ${isLangDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                
                {isLangDropdownOpen && (
                  <div className="absolute bottom-full left-0 mb-1 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden min-w-[120px]">
                    <button
                      type="button"
                      onClick={() => { setLanguage('it'); setIsLangDropdownOpen(false); }}
                      className={`w-full px-4 py-2.5 text-left text-xs font-semibold transition-all ${
                        language === 'it' ? 'bg-orange-50 text-orange-700' : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      Italiano
                    </button>
                    <button
                      type="button"
                      onClick={() => { setLanguage('en'); setIsLangDropdownOpen(false); }}
                      className={`w-full px-4 py-2.5 text-left text-xs font-semibold transition-all ${
                        language === 'en' ? 'bg-orange-50 text-orange-700' : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      English
                    </button>
                  </div>
                )}
              </div>
          </div>
          
          {/* CR3: Suggested Follow-ups */}
          {suggestedFollowups.length > 0 && !isLoading && (
            <div className="flex flex-wrap gap-2 mb-3">
              {suggestedFollowups.map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setInput(suggestion);
                    setSuggestedFollowups([]);
                  }}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-orange-100 text-slate-600 hover:text-orange-700 text-xs font-medium rounded-full transition-all border border-slate-200 hover:border-orange-300"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="relative">
            <textarea
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (input.trim() && !isLoading) {
                    handleSubmit(e as any);
                  }
                }
              }}
              placeholder={language === 'it' ? "Fai una domanda sui tuoi dati..." : "Ask a question about your data..."}
              className="w-full bg-slate-50 border border-slate-200 rounded-2xl pl-5 pr-24 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all resize-none overflow-hidden leading-relaxed"
              disabled={isLoading}
              rows={1}
            />
            <div className="absolute right-3 bottom-3 flex items-center gap-1.5">
              <VoiceMicButton
                onTranscribe={(text) => setInput((prev) => (prev ? prev + ' ' + text : text))}
                disabled={isLoading}
              />
              {isLoading ? (
                <button 
                  type="button"
                  onClick={handleStop}
                  className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 text-white hover:bg-slate-900 transition-all"
                  title="Interrompi elaborazione"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="4" y="4" width="16" height="16" rx="2"/>
                  </svg>
                </button>
              ) : (
                <button 
                  type="submit" 
                  disabled={!input.trim()}
                  className="w-8 h-8 flex items-center justify-center rounded-lg bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 19V5M5 12l7-7 7 7"/>
                  </svg>
                </button>
              )}
            </div>
          </form>
         </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;