import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import ChartViewer from '../Charts/ChartViewer';
import { Icons } from '../Layout/Icons';
import { DashboardLayout, UserDashboard, SavedChart } from '../../types';
import { Modal, ConfirmModal } from '../ui/modal';
import { Toast, useToast } from '../ui/toast';

// Colori preset per i grafici
const COLOR_PRESETS = [
  '#FF6B35', '#F7931E', '#FFD23F', '#06D6A0', '#118AB2', '#073B4C',
  '#EF476F', '#8338EC', '#3A86FF', '#FB5607', '#FF006E', '#8AC926',
  '#1982C4', '#6A4C93', '#E63946', '#2A9D8F', '#E9C46A', '#264653'
];

interface ChartStyleConfig {
  fontSize: number;
  titleFontSize: number;
  showLabels: boolean;
  showLegend: boolean;
  primaryColor: string;
  colorScheme: string[];
  titleAlignment: 'left' | 'center' | 'right';
  legendPosition: 'top' | 'bottom' | 'left' | 'right';
  showGrid: boolean;
  showPercentage: boolean;
  showValues: boolean;
  borderRadius: number;
  categoryColors: { [key: string]: string };
  backgroundColor: string;
  titleColor: string;
  labelColor: string;
  xAxisTitle: string;
  yAxisTitle: string;
}

interface ChartConfigPanelProps {
  chart: SavedChart;
  onUpdate: (updatedConfig: any) => void;
  onClose: () => void;
  onPreview: (previewConfig: any) => void;
}

const ChartConfigPanel: React.FC<ChartConfigPanelProps> = ({ chart, onUpdate, onClose, onPreview }) => {
  const getInitialConfig = (): ChartStyleConfig => {
    const layout = chart.plotlyConfig?.layout || {};
    const data = chart.plotlyConfig?.data?.[0] || {};
    
    const labels = data.labels || data.x || [];
    const colors = Array.isArray(data.marker?.colors) ? data.marker.colors : COLOR_PRESETS.slice(0, labels.length);
    const categoryColors: { [key: string]: string } = {};
    labels.forEach((label: string, i: number) => {
      categoryColors[label] = colors[i] || COLOR_PRESETS[i % COLOR_PRESETS.length];
    });

    let titleAlign: 'left' | 'center' | 'right' = 'center';
    if (layout.title?.xanchor === 'left') titleAlign = 'left';
    else if (layout.title?.xanchor === 'right') titleAlign = 'right';

    let legendPos: 'top' | 'bottom' | 'left' | 'right' = 'right';
    if (layout.legend?.orientation === 'h') {
      legendPos = layout.legend?.y > 0.5 ? 'top' : 'bottom';
    } else {
      legendPos = layout.legend?.x > 0.5 ? 'right' : 'left';
    }
    
    // Determina se le etichette sono visibili
    // Per bar chart: textposition deve essere 'auto', 'inside', 'outside' (non 'none' o undefined)
    // Per pie chart: textinfo deve contenere 'label', 'percent', 'value' (non 'none')
    let showLabels = false;
    if (data.type === 'pie') {
      showLabels = data.textinfo && data.textinfo !== 'none';
    } else if (data.type === 'bar') {
      showLabels = data.textposition && data.textposition !== 'none';
    } else {
      showLabels = (data.textinfo && data.textinfo !== 'none') || (data.textposition && data.textposition !== 'none');
    }
    
    return {
      fontSize: layout.font?.size || 12,
      titleFontSize: layout.title?.font?.size || 16,
      showLabels,
      showLegend: layout.showlegend !== false,
      primaryColor: data.marker?.color || COLOR_PRESETS[0],
      colorScheme: colors,
      titleAlignment: titleAlign,
      legendPosition: legendPos,
      showGrid: layout.xaxis?.showgrid !== false && layout.yaxis?.showgrid !== false,
      showPercentage: data.textinfo?.includes('percent') || false,
      showValues: data.textinfo?.includes('value') || data.textinfo?.includes('label') || false,
      borderRadius: 0,
      categoryColors,
      backgroundColor: layout.paper_bgcolor || '#ffffff',
      titleColor: layout.title?.font?.color || '#1e293b',
      labelColor: layout.font?.color || '#64748b',
      xAxisTitle: layout.xaxis?.title?.text || '',
      yAxisTitle: layout.yaxis?.title?.text || '',
    };
  };

  const [config, setConfig] = useState<ChartStyleConfig>(getInitialConfig());
  const [expandedSections, setExpandedSections] = useState<string[]>(['titolo', 'colori']);

  const categories = chart.plotlyConfig?.data?.[0]?.labels || chart.plotlyConfig?.data?.[0]?.x || [];

  const buildPlotlyConfig = useCallback((cfg: ChartStyleConfig) => {
    const updatedPlotly = JSON.parse(JSON.stringify(chart.plotlyConfig));
    
    if (!updatedPlotly.layout) updatedPlotly.layout = {};
    if (!updatedPlotly.layout.font) updatedPlotly.layout.font = {};
    if (!updatedPlotly.layout.title) updatedPlotly.layout.title = {};
    if (!updatedPlotly.layout.title.font) updatedPlotly.layout.title.font = {};
    
    updatedPlotly.layout.font.size = cfg.fontSize;
    updatedPlotly.layout.font.color = cfg.labelColor;
    updatedPlotly.layout.title.font.size = cfg.titleFontSize;
    updatedPlotly.layout.title.font.color = cfg.titleColor;
    updatedPlotly.layout.showlegend = cfg.showLegend;
    updatedPlotly.layout.paper_bgcolor = cfg.backgroundColor;
    updatedPlotly.layout.plot_bgcolor = cfg.backgroundColor;

    const titleAlignMap = { left: 0, center: 0.5, right: 1 };
    updatedPlotly.layout.title.x = titleAlignMap[cfg.titleAlignment];
    updatedPlotly.layout.title.xanchor = cfg.titleAlignment;

    if (!updatedPlotly.layout.legend) updatedPlotly.layout.legend = {};
    switch (cfg.legendPosition) {
      case 'top':
        updatedPlotly.layout.legend = { orientation: 'h', x: 0.5, xanchor: 'center', y: 1.1 };
        break;
      case 'bottom':
        updatedPlotly.layout.legend = { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.15 };
        break;
      case 'left':
        updatedPlotly.layout.legend = { orientation: 'v', x: -0.15, y: 0.5 };
        break;
      case 'right':
        updatedPlotly.layout.legend = { orientation: 'v', x: 1.02, y: 0.5 };
        break;
    }

    if (!updatedPlotly.layout.xaxis) updatedPlotly.layout.xaxis = {};
    if (!updatedPlotly.layout.yaxis) updatedPlotly.layout.yaxis = {};
    updatedPlotly.layout.xaxis.showgrid = cfg.showGrid;
    updatedPlotly.layout.yaxis.showgrid = cfg.showGrid;
    updatedPlotly.layout.xaxis.gridcolor = '#e2e8f0';
    updatedPlotly.layout.yaxis.gridcolor = '#e2e8f0';
    
    // Titoli assi
    if (cfg.xAxisTitle) {
      if (!updatedPlotly.layout.xaxis.title) updatedPlotly.layout.xaxis.title = {};
      updatedPlotly.layout.xaxis.title.text = cfg.xAxisTitle;
    }
    if (cfg.yAxisTitle) {
      if (!updatedPlotly.layout.yaxis.title) updatedPlotly.layout.yaxis.title = {};
      updatedPlotly.layout.yaxis.title.text = cfg.yAxisTitle;
    }
    
    if (updatedPlotly.data && updatedPlotly.data.length > 0) {
      const trace = updatedPlotly.data[0];
      
      if (trace.type === 'pie') {
        trace.marker = trace.marker || {};
        const labels = trace.labels || [];
        trace.marker.colors = labels.map((label: string) => cfg.categoryColors[label] || cfg.colorScheme[0]);
        
        let textInfo = '';
        if (cfg.showValues) textInfo += 'label';
        if (cfg.showPercentage) textInfo += textInfo ? '+percent' : 'percent';
        trace.textinfo = textInfo || 'none';
        trace.textfont = { size: cfg.fontSize, color: cfg.labelColor };
        trace.hoverinfo = 'label+percent+value';
      } else if (trace.type === 'bar') {
        trace.marker = trace.marker || {};
        if (trace.x && Array.isArray(trace.x)) {
          trace.marker.color = trace.x.map((x: string) => cfg.categoryColors[x] || cfg.primaryColor);
        } else {
          trace.marker.color = cfg.primaryColor;
        }
        trace.textposition = cfg.showLabels ? 'auto' : 'none';
        trace.textfont = { size: cfg.fontSize, color: cfg.labelColor };
      } else if (trace.type === 'indicator') {
        trace.number = trace.number || {};
        trace.number.font = { size: cfg.fontSize * 3, color: cfg.primaryColor };
        trace.title = trace.title || {};
        trace.title.font = { size: cfg.titleFontSize, color: cfg.titleColor };
      } else if (trace.type === 'scatter') {
        trace.marker = trace.marker || {};
        trace.marker.color = cfg.primaryColor;
        trace.line = trace.line || {};
        trace.line.color = cfg.primaryColor;
      } else {
        trace.marker = trace.marker || {};
        trace.marker.color = cfg.primaryColor;
      }
    }
    
    return updatedPlotly;
  }, [chart.plotlyConfig]);

  const updateConfigAndPreview = useCallback((newConfig: ChartStyleConfig) => {
    setConfig(newConfig);
    onPreview(buildPlotlyConfig(newConfig));
  }, [buildPlotlyConfig, onPreview]);

  const applyChanges = () => {
    onUpdate(buildPlotlyConfig(config));
  };

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => 
      prev.includes(sectionId) 
        ? prev.filter(s => s !== sectionId)
        : [...prev, sectionId]
    );
  };

  const chartType = chart.plotlyConfig?.data?.[0]?.type || 'unknown';
  const isKPI = chartType === 'indicator';
  const isPie = chartType === 'pie';
  const isBar = chartType === 'bar';
  const isLine = chartType === 'scatter';

  const colorSchemes = [
    { name: 'Vivace', colors: ['#FF6B35', '#F7931E', '#FFD23F', '#06D6A0', '#118AB2', '#073B4C'] },
    { name: 'Pastello', colors: ['#FFB5A7', '#FCD5CE', '#F8EDEB', '#D8E2DC', '#E8E8E4', '#ECE4DB'] },
    { name: 'Corporate', colors: ['#003049', '#D62828', '#F77F00', '#FCBF49', '#EAE2B7', '#457B9D'] },
    { name: 'Oceano', colors: ['#0077B6', '#00B4D8', '#90E0EF', '#CAF0F8', '#48CAE4', '#023E8A'] },
    { name: 'Natura', colors: ['#2D6A4F', '#40916C', '#52B788', '#74C69D', '#95D5B2', '#B7E4C7'] },
    { name: 'Tramonto', colors: ['#D00000', '#DC2F02', '#E85D04', '#F48C06', '#FAA307', '#FFBA08'] },
  ];

  const handleCategoryColorChange = (category: string, color: string) => {
    const newConfig = {
      ...config,
      categoryColors: { ...config.categoryColors, [category]: color }
    };
    updateConfigAndPreview(newConfig);
  };

  const applyColorSchemeToCategories = (colors: string[]) => {
    const newCategoryColors: { [key: string]: string } = {};
    categories.forEach((cat: string, i: number) => {
      newCategoryColors[cat] = colors[i % colors.length];
    });
    updateConfigAndPreview({ ...config, colorScheme: colors, categoryColors: newCategoryColors });
  };

  const AccordionSection = ({ id, title, children }: { id: string; title: string; children: React.ReactNode }) => {
    const isExpanded = expandedSections.includes(id);
    return (
      <div className="border border-slate-200 rounded-xl overflow-hidden">
        <button
          onClick={() => toggleSection(id)}
          className={`w-full px-4 py-3 flex items-center justify-between text-left transition-all ${
            isExpanded ? 'bg-orange-50 border-b border-orange-200' : 'bg-white hover:bg-slate-50'
          }`}
        >
          <span className={`text-[11px] font-bold uppercase tracking-wide ${isExpanded ? 'text-orange-700' : 'text-slate-600'}`}>
            {title}
          </span>
          <svg
            className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180 text-orange-500' : 'text-slate-400'}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {isExpanded && (
          <div className="p-4 space-y-4 bg-white">
            {children}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="w-80 bg-slate-50 border-l border-slate-200 flex flex-col h-full shadow-xl">
      <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-white">
        <div>
          <h3 className="text-sm font-bold text-slate-800">Configura Grafico</h3>
          <p className="text-[10px] text-slate-400 capitalize mt-0.5">Tipo: {chartType}</p>
        </div>
        <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all">
          <Icons.Close />
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* TITOLO */}
        <AccordionSection id="titolo" title="Titolo">
          <div>
            <label className="text-[10px] font-medium text-slate-500 block mb-2">Dimensione</label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="10"
                max="32"
                value={config.titleFontSize}
                onChange={(e) => updateConfigAndPreview({ ...config, titleFontSize: parseInt(e.target.value) })}
                className="flex-1 accent-orange-500"
              />
              <input
                type="number"
                min="10"
                max="32"
                step="1"
                value={config.titleFontSize}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (!isNaN(val)) {
                    updateConfigAndPreview({ ...config, titleFontSize: Math.min(32, Math.max(10, val)) });
                  }
                }}
                onFocus={(e) => e.target.select()}
                className="w-16 px-2 py-1.5 text-xs font-bold text-slate-700 text-center border border-slate-200 rounded-lg focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-200 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] font-medium text-slate-500 block mb-2">Allineamento</label>
            <div className="flex gap-1">
              {[
                { value: 'left', label: 'Sinistra' },
                { value: 'center', label: 'Centro' },
                { value: 'right', label: 'Destra' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => updateConfigAndPreview({ ...config, titleAlignment: opt.value as 'left' | 'center' | 'right' })}
                  className={`flex-1 py-2 rounded-lg text-[10px] font-bold transition-all ${
                    config.titleAlignment === opt.value
                      ? 'bg-orange-500 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-[10px] font-medium text-slate-500 block mb-2">Colore</label>
            <div className="flex gap-2 flex-wrap">
              {['#1e293b', '#334155', '#475569', '#64748b', '#0f172a', '#ea580c'].map((color) => (
                <button
                  key={color}
                  onClick={() => updateConfigAndPreview({ ...config, titleColor: color })}
                  className={`w-7 h-7 rounded-lg border-2 transition-all ${
                    config.titleColor === color ? 'border-orange-500 scale-110' : 'border-slate-200 hover:scale-105'
                  }`}
                  style={{ backgroundColor: color }}
                />
              ))}
              <input
                type="color"
                value={config.titleColor}
                onChange={(e) => updateConfigAndPreview({ ...config, titleColor: e.target.value })}
                className="w-7 h-7 rounded-lg border-2 border-dashed border-slate-300 cursor-pointer"
                title="Colore personalizzato"
              />
            </div>
          </div>
        </AccordionSection>

        {/* COLORI */}
        <AccordionSection id="colori" title="Colori">
          {!isPie && !isKPI && (
            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Colore Principale</label>
              <div className="flex gap-2 flex-wrap">
                {COLOR_PRESETS.slice(0, 12).map((color) => (
                  <button
                    key={color}
                    onClick={() => updateConfigAndPreview({ ...config, primaryColor: color })}
                    className={`w-7 h-7 rounded-lg transition-all ${
                      config.primaryColor === color ? 'ring-2 ring-offset-1 ring-orange-500 scale-110' : 'hover:scale-105'
                    }`}
                    style={{ backgroundColor: color }}
                  />
                ))}
                <input
                  type="color"
                  value={config.primaryColor}
                  onChange={(e) => updateConfigAndPreview({ ...config, primaryColor: e.target.value })}
                  className="w-7 h-7 rounded-lg border-2 border-dashed border-slate-300 cursor-pointer"
                  title="Colore personalizzato"
                />
              </div>
            </div>
          )}

          <div>
            <label className="text-[10px] font-medium text-slate-500 block mb-2">Schema Colori</label>
            <div className="space-y-1.5">
              {colorSchemes.map((scheme) => (
                <button
                  key={scheme.name}
                  onClick={() => applyColorSchemeToCategories(scheme.colors)}
                  className={`w-full flex items-center gap-2 p-2 rounded-lg transition-all ${
                    JSON.stringify(config.colorScheme) === JSON.stringify(scheme.colors)
                      ? 'bg-orange-100 border border-orange-300'
                      : 'bg-slate-50 border border-transparent hover:bg-slate-100'
                  }`}
                >
                  <span className="text-[10px] font-medium text-slate-600 w-14">{scheme.name}</span>
                  <div className="flex gap-0.5 flex-1">
                    {scheme.colors.map((c, i) => (
                      <div key={i} className="w-4 h-4 rounded" style={{ backgroundColor: c }} />
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {(isPie || isBar) && categories.length > 0 && (
            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Colore per Categoria</label>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {categories.map((cat: string, idx: number) => (
                  <div key={cat} className="flex items-center gap-2 p-2 bg-slate-50 rounded-lg">
                    <input
                      type="color"
                      value={config.categoryColors[cat] || COLOR_PRESETS[idx % COLOR_PRESETS.length]}
                      onChange={(e) => handleCategoryColorChange(cat, e.target.value)}
                      className="w-6 h-6 rounded border-0 cursor-pointer"
                    />
                    <span className="text-[10px] font-medium text-slate-700 flex-1 truncate">{cat}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="text-[10px] font-medium text-slate-500 block mb-2">Sfondo</label>
            <div className="flex gap-2 flex-wrap">
              {['#ffffff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#1e293b', '#0f172a'].map((color) => (
                <button
                  key={color}
                  onClick={() => updateConfigAndPreview({ ...config, backgroundColor: color })}
                  className={`w-7 h-7 rounded-lg border-2 transition-all ${
                    config.backgroundColor === color ? 'border-orange-500 scale-110' : 'border-slate-200 hover:scale-105'
                  }`}
                  style={{ backgroundColor: color }}
                />
              ))}
            </div>
          </div>
        </AccordionSection>

        {/* ETICHETTE */}
        {!isKPI && (
          <AccordionSection id="etichette" title="Etichette e Testo">
            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Dimensione Testo</label>
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min="8"
                  max="24"
                  value={config.fontSize}
                  onChange={(e) => updateConfigAndPreview({ ...config, fontSize: parseInt(e.target.value) })}
                  className="flex-1 accent-orange-500"
                />
                <input
                  type="number"
                  min="8"
                  max="24"
                  step="1"
                  value={config.fontSize}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val)) {
                      updateConfigAndPreview({ ...config, fontSize: Math.min(24, Math.max(8, val)) });
                    }
                  }}
                  onFocus={(e) => e.target.select()}
                  className="w-16 px-2 py-1.5 text-xs font-bold text-slate-700 text-center border border-slate-200 rounded-lg focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-200 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
              </div>
            </div>

            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Colore Etichette</label>
              <div className="flex gap-2 flex-wrap">
                {['#1e293b', '#334155', '#475569', '#64748b', '#94a3b8', '#ffffff'].map((color) => (
                  <button
                    key={color}
                    onClick={() => updateConfigAndPreview({ ...config, labelColor: color })}
                    className={`w-7 h-7 rounded-lg border-2 transition-all ${
                      config.labelColor === color ? 'border-orange-500 scale-110' : 'border-slate-200 hover:scale-105'
                    }`}
                    style={{ backgroundColor: color }}
                  />
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between py-2">
              <label className="text-[10px] font-medium text-slate-600">Mostra Etichette</label>
              <button
                onClick={() => updateConfigAndPreview({ ...config, showLabels: !config.showLabels })}
                className={`w-10 h-5 rounded-full transition-all ${config.showLabels ? 'bg-orange-500' : 'bg-slate-300'}`}
              >
                <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${config.showLabels ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
            </div>

            {isPie && (
              <>
                <div className="flex items-center justify-between py-2">
                  <label className="text-[10px] font-medium text-slate-600">Mostra Valori</label>
                  <button
                    onClick={() => updateConfigAndPreview({ ...config, showValues: !config.showValues })}
                    className={`w-10 h-5 rounded-full transition-all ${config.showValues ? 'bg-orange-500' : 'bg-slate-300'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${config.showValues ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>

                <div className="flex items-center justify-between py-2">
                  <label className="text-[10px] font-medium text-slate-600">Mostra Percentuali</label>
                  <button
                    onClick={() => updateConfigAndPreview({ ...config, showPercentage: !config.showPercentage })}
                    className={`w-10 h-5 rounded-full transition-all ${config.showPercentage ? 'bg-orange-500' : 'bg-slate-300'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${config.showPercentage ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
              </>
            )}
          </AccordionSection>
        )}

        {/* LEGENDA */}
        <AccordionSection id="legenda" title="Legenda">
          <div className="flex items-center justify-between py-2">
            <label className="text-[10px] font-medium text-slate-600">Mostra Legenda</label>
            <button
              onClick={() => updateConfigAndPreview({ ...config, showLegend: !config.showLegend })}
              className={`w-10 h-5 rounded-full transition-all ${config.showLegend ? 'bg-orange-500' : 'bg-slate-300'}`}
            >
              <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${config.showLegend ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>

          {config.showLegend && (
            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Posizione</label>
              <div className="grid grid-cols-2 gap-1">
                {[
                  { value: 'top', label: 'Alto' },
                  { value: 'bottom', label: 'Basso' },
                  { value: 'left', label: 'Sinistra' },
                  { value: 'right', label: 'Destra' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => updateConfigAndPreview({ ...config, legendPosition: opt.value as 'top' | 'bottom' | 'left' | 'right' })}
                    className={`py-2 rounded-lg text-[10px] font-bold transition-all ${
                      config.legendPosition === opt.value
                        ? 'bg-orange-500 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </AccordionSection>

        {/* ASSI (solo per bar e line) */}
        {(isBar || isLine) && (
          <AccordionSection id="assi" title="Assi e Griglia">
            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Titolo Asse X</label>
              <input
                type="text"
                value={config.xAxisTitle}
                onChange={(e) => updateConfigAndPreview({ ...config, xAxisTitle: e.target.value })}
                placeholder="Es: Categoria, Mese, Regione..."
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-200"
              />
            </div>

            <div>
              <label className="text-[10px] font-medium text-slate-500 block mb-2">Titolo Asse Y</label>
              <input
                type="text"
                value={config.yAxisTitle}
                onChange={(e) => updateConfigAndPreview({ ...config, yAxisTitle: e.target.value })}
                placeholder="Es: Vendite, Quantita, Valore..."
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-200"
              />
            </div>

            <div className="flex items-center justify-between py-2">
              <label className="text-[10px] font-medium text-slate-600">Mostra Griglia</label>
              <button
                onClick={() => updateConfigAndPreview({ ...config, showGrid: !config.showGrid })}
                className={`w-10 h-5 rounded-full transition-all ${config.showGrid ? 'bg-orange-500' : 'bg-slate-300'}`}
              >
                <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${config.showGrid ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
            </div>
          </AccordionSection>
        )}
      </div>

      {/* Actions */}
      <div className="p-3 border-t border-slate-200 space-y-2 bg-white">
        <button
          onClick={applyChanges}
          className="w-full py-3 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:from-orange-600 hover:to-amber-600 transition-all shadow-lg"
        >
          Salva Modifiche
        </button>
        <button
          onClick={onClose}
          className="w-full py-2 text-slate-500 text-[10px] font-bold uppercase tracking-widest hover:text-slate-700"
        >
          Annulla
        </button>
      </div>
    </div>
  );
};

interface DraggableChartProps {
  layout: DashboardLayout;
  chart: any;
  chartConfig: any;
  onUpdate: (updates: Partial<DashboardLayout>) => void;
  onRemove: () => void;
  isSelected: boolean;
  onSelect: () => void;
  onConfigure: () => void;
  onDoubleClick: () => void;
}

const DraggableChart: React.FC<DraggableChartProps> = ({ layout, chart, chartConfig, onUpdate, onRemove, isSelected, onSelect, onConfigure, onDoubleClick }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const elementRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.resize-handle')) return;
    e.preventDefault();
    onSelect();
    setIsDragging(true);
    setDragStart({ x: e.clientX - layout.x, y: e.clientY - layout.y });
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (isDragging) {
      const newX = Math.max(0, e.clientX - dragStart.x);
      const newY = Math.max(0, e.clientY - dragStart.y);
      onUpdate({ x: newX, y: newY });
    }
  }, [isDragging, dragStart, onUpdate]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    setIsResizing(false);
  }, []);

  React.useEffect(() => {
    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, handleMouseMove, handleMouseUp]);

  const handleResizeStart = (e: React.MouseEvent, direction: string) => {
    e.preventDefault();
    e.stopPropagation();
    onSelect();
    setIsResizing(true);
    
    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = layout.width;
    const startHeight = layout.height;
    const startLeft = layout.x;
    const startTop = layout.y;

    const handleResize = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      
      let newWidth = startWidth;
      let newHeight = startHeight;
      let newX = startLeft;
      let newY = startTop;

      if (direction.includes('e')) newWidth = Math.max(200, startWidth + deltaX);
      if (direction.includes('w')) { newWidth = Math.max(200, startWidth - deltaX); newX = startLeft + deltaX; }
      if (direction.includes('s')) newHeight = Math.max(150, startHeight + deltaY);
      if (direction.includes('n')) { newHeight = Math.max(150, startHeight - deltaY); newY = startTop + deltaY; }

      onUpdate({ width: newWidth, height: newHeight, x: Math.max(0, newX), y: Math.max(0, newY) });
    };

    const handleResizeEnd = () => {
      setIsResizing(false);
      window.removeEventListener('mousemove', handleResize);
      window.removeEventListener('mouseup', handleResizeEnd);
    };

    window.addEventListener('mousemove', handleResize);
    window.addEventListener('mouseup', handleResizeEnd);
  };

  return (
    <div
      ref={elementRef}
      className={`absolute bg-white rounded-2xl border-2 shadow-lg overflow-hidden flex flex-col transition-shadow ${
        isSelected ? 'border-orange-500 shadow-orange-100' : 'border-slate-200 hover:border-slate-300'
      } ${isDragging ? 'cursor-grabbing shadow-2xl z-50' : 'cursor-grab'}`}
      style={{ left: layout.x, top: layout.y, width: layout.width, height: layout.height }}
      onMouseDown={handleMouseDown}
      onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(); }}
    >
      <div className="px-4 py-3 border-b border-slate-100 flex justify-between items-center bg-slate-50 shrink-0">
        <h3 className="text-[11px] font-bold text-slate-700 truncate flex-1 uppercase tracking-wide">
          {chart?.title || 'Grafico non trovato'}
        </h3>
        <div className="flex items-center gap-1">
          <button 
            onClick={(e) => { e.stopPropagation(); onConfigure(); }}
            className="p-1.5 text-slate-400 hover:text-orange-500 transition-colors"
            title="Configura grafico"
          >
            <Icons.Settings />
          </button>
          <button 
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="p-1.5 text-slate-400 hover:text-red-500 transition-colors"
            title="Rimuovi"
          >
            <Icons.Trash />
          </button>
        </div>
      </div>
      <div className="flex-1 p-3 flex items-center justify-center overflow-hidden">
        {chart ? (
          <ChartViewer config={chartConfig || chart.plotlyConfig} height={layout.height - 80} />
        ) : (
          <span className="text-slate-400 text-xs">Grafico non disponibile</span>
        )}
      </div>
      
      {isSelected && (
        <>
          <div className="resize-handle absolute top-0 left-0 w-3 h-3 bg-orange-500 cursor-nw-resize rounded-br" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
          <div className="resize-handle absolute top-0 right-0 w-3 h-3 bg-orange-500 cursor-ne-resize rounded-bl" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
          <div className="resize-handle absolute bottom-0 left-0 w-3 h-3 bg-orange-500 cursor-sw-resize rounded-tr" onMouseDown={(e) => handleResizeStart(e, 'sw')} />
          <div className="resize-handle absolute bottom-0 right-0 w-3 h-3 bg-orange-500 cursor-se-resize rounded-tl" onMouseDown={(e) => handleResizeStart(e, 'se')} />
          <div className="resize-handle absolute top-0 left-1/2 -translate-x-1/2 w-6 h-2 bg-orange-500 cursor-n-resize rounded-b" onMouseDown={(e) => handleResizeStart(e, 'n')} />
          <div className="resize-handle absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-2 bg-orange-500 cursor-s-resize rounded-t" onMouseDown={(e) => handleResizeStart(e, 's')} />
          <div className="resize-handle absolute left-0 top-1/2 -translate-y-1/2 w-2 h-6 bg-orange-500 cursor-w-resize rounded-r" onMouseDown={(e) => handleResizeStart(e, 'w')} />
          <div className="resize-handle absolute right-0 top-1/2 -translate-y-1/2 w-2 h-6 bg-orange-500 cursor-e-resize rounded-l" onMouseDown={(e) => handleResizeStart(e, 'e')} />
        </>
      )}
    </div>
  );
};

const DashboardManager: React.FC = () => {
  const { dashboards, savedCharts, saveDashboard, deleteDashboard, updateChart } = useAppStore();
  const [activeDashId, setActiveDashId] = useState<string | null>(dashboards[0]?.id || null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isEditingName, setIsEditingName] = useState(false);
  const [selectedChartIndex, setSelectedChartIndex] = useState<number | null>(null);
  const [configuringChartId, setConfiguringChartId] = useState<string | null>(null);
  const [chartSelectorOpen, setChartSelectorOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [dashToDelete, setDashToDelete] = useState<string | null>(null);
  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [editingSidebarDashId, setEditingSidebarDashId] = useState<string | null>(null);
  const [editingSidebarName, setEditingSidebarName] = useState('');
  const [previewConfig, setPreviewConfig] = useState<{ [chartId: string]: any }>({});
  const { toast, showToast, hideToast } = useToast();
  const canvasRef = useRef<HTMLDivElement>(null);
  const sidebarInputRef = useRef<HTMLInputElement>(null);

  const currentDash = dashboards.find(d => d.id === activeDashId);

  // Sincronizza activeDashId quando lo store viene idratato o cambia
  useEffect(() => {
    if (dashboards.length > 0 && !activeDashId) {
      setActiveDashId(dashboards[0].id);
    } else if (activeDashId && !dashboards.find(d => d.id === activeDashId)) {
      // Se la dashboard attiva non esiste più, seleziona la prima
      setActiveDashId(dashboards[0]?.id || null);
    }
  }, [dashboards, activeDashId]);

  const handleCreateDashboard = () => {
    const id = `dash-${Date.now()}`;
    const newDash: UserDashboard = { id, name: 'Nuova Dashboard', layouts: [], createdAt: new Date() };
    saveDashboard(newDash);
    setActiveDashId(id);
    showToast('Dashboard creata!', 'success');
  };

  const handleAddChartToDash = (chartId: string) => {
    if (!currentDash) return;
    const existingCount = currentDash.layouts.length;
    const col = existingCount % 2;
    const row = Math.floor(existingCount / 2);
    
    const newLayout: DashboardLayout = { 
      chartId, 
      x: 20 + col * 420, 
      y: 20 + row * 350, 
      width: 400, 
      height: 320 
    };
    const updated = { ...currentDash, layouts: [...currentDash.layouts, newLayout], updatedAt: new Date() };
    saveDashboard(updated);
    setChartSelectorOpen(false);
    showToast('Grafico aggiunto!', 'success');
  };

  const handleUpdateLayout = (index: number, updates: Partial<DashboardLayout>) => {
    if (!currentDash) return;
    const newLayouts = [...currentDash.layouts];
    newLayouts[index] = { ...newLayouts[index], ...updates };
    saveDashboard({ ...currentDash, layouts: newLayouts, updatedAt: new Date() });
    setHasUnsavedChanges(true);
  };

  const handleSaveDashboard = () => {
    if (!currentDash) return;
    saveDashboard({ ...currentDash, updatedAt: new Date() });
    setHasUnsavedChanges(false);
    setIsPreviewMode(true);
    setSelectedChartIndex(null);
    showToast('Dashboard salvata!', 'success');
  };

  const handleExitPreview = () => {
    setIsPreviewMode(false);
  };

  const handleRemoveFromDash = (index: number) => {
    if (!currentDash) return;
    const newLayouts = [...currentDash.layouts];
    newLayouts.splice(index, 1);
    saveDashboard({ ...currentDash, layouts: newLayouts, updatedAt: new Date() });
    setSelectedChartIndex(null);
  };

  const handleDeleteDashboard = (id: string) => {
    setDashToDelete(id);
    setDeleteModalOpen(true);
  };

  const handleStartRenameSidebar = (d: UserDashboard, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSidebarDashId(d.id);
    setEditingSidebarName(d.name);
    setTimeout(() => sidebarInputRef.current?.focus(), 50);
  };

  const handleSaveRenameSidebar = () => {
    if (editingSidebarDashId && editingSidebarName.trim()) {
      const dash = dashboards.find(d => d.id === editingSidebarDashId);
      if (dash) {
        saveDashboard({ ...dash, name: editingSidebarName.trim(), updatedAt: new Date() });
        showToast('Dashboard rinominata!', 'success');
      }
    }
    setEditingSidebarDashId(null);
    setEditingSidebarName('');
  };

  const handleCancelRenameSidebar = () => {
    setEditingSidebarDashId(null);
    setEditingSidebarName('');
  };

  const confirmDeleteDashboard = () => {
    if (dashToDelete) {
      deleteDashboard(dashToDelete);
      if (activeDashId === dashToDelete) {
        setActiveDashId(dashboards.find(d => d.id !== dashToDelete)?.id || null);
      }
      showToast('Dashboard eliminata', 'success');
    }
    setDashToDelete(null);
  };

  const handleExportPDF = async () => {
    if (!canvasRef.current || !currentDash) return;
    showToast('Generazione PDF in corso...', 'info');
    
    try {
      const html2canvas = (await import('html2canvas')).default;
      const canvas = await html2canvas(canvasRef.current, { 
        scale: 2, 
        backgroundColor: '#f8fafc',
        logging: false 
      });
      
      const link = document.createElement('a');
      link.download = `${currentDash.name.replace(/\s+/g, '_')}_dashboard.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      
      showToast('Dashboard esportata!', 'success');
    } catch (error) {
      showToast('Errore durante export', 'error');
    }
  };

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      setSelectedChartIndex(null);
    }
  };

  const handleUpdateChartConfig = (chartId: string, newPlotlyConfig: any) => {
    const chart = savedCharts.find(c => c.id === chartId);
    if (chart && updateChart) {
      updateChart(chartId, { plotlyConfig: newPlotlyConfig });
      setHasUnsavedChanges(true);
      setPreviewConfig(prev => {
        const newPreview = { ...prev };
        delete newPreview[chartId];
        return newPreview;
      });
      showToast('Modifiche salvate!', 'success');
    }
  };

  const handlePreviewChartConfig = (chartId: string, previewPlotlyConfig: any) => {
    setPreviewConfig(prev => ({ ...prev, [chartId]: previewPlotlyConfig }));
  };

  const handleCloseConfigPanel = () => {
    if (configuringChartId) {
      setPreviewConfig(prev => {
        const newPreview = { ...prev };
        delete newPreview[configuringChartId];
        return newPreview;
      });
    }
    setConfiguringChartId(null);
  };

  const getChartConfig = (chartId: string) => {
    if (previewConfig[chartId]) {
      return previewConfig[chartId];
    }
    const chart = savedCharts.find(c => c.id === chartId);
    return chart?.plotlyConfig;
  };

  const configuringChart = configuringChartId ? savedCharts.find(c => c.id === configuringChartId) : null;

  return (
    <div className="flex h-full bg-slate-100 overflow-hidden relative">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />
      
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={confirmDeleteDashboard}
        title="Elimina Dashboard"
        message="Sei sicuro di voler eliminare questa dashboard? L'azione non può essere annullata."
        confirmText="Elimina"
        variant="danger"
      />

      <Modal isOpen={chartSelectorOpen} onClose={() => setChartSelectorOpen(false)} title="Seleziona Grafico" size="lg">
        <div className="grid grid-cols-2 gap-4 max-h-[500px] overflow-y-auto p-1">
          {savedCharts.length === 0 ? (
            <div className="col-span-2 text-center py-8 text-slate-400">
              <p className="text-sm">Nessun grafico salvato</p>
              <p className="text-xs mt-1">Salva grafici dalla Chat per aggiungerli qui</p>
            </div>
          ) : (
            savedCharts.map(c => (
              <button
                key={c.id}
                onClick={() => handleAddChartToDash(c.id)}
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

      {/* Sidebar */}
      <div className={`border-r border-slate-200 flex flex-col bg-white transition-all duration-300 ${isSidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="p-4 border-b border-slate-100 shrink-0">
          <button 
            onClick={handleCreateDashboard}
            className="w-full py-3 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:from-orange-600 hover:to-amber-600 transition-all shadow-lg shadow-orange-100 flex items-center justify-center gap-2"
          >
            <Icons.Plus /> Crea Dashboard
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4 px-2">Mie Dashboard</h4>
          {dashboards.length === 0 ? (
            <p className="text-xs text-slate-400 px-2">Nessuna dashboard creata</p>
          ) : (
            dashboards.map(d => (
              <div 
                key={d.id}
                className={`group w-full flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${
                  d.id === activeDashId ? 'bg-orange-50 border border-orange-200 shadow-sm' : 'hover:bg-slate-50 border border-transparent'
                }`}
                onClick={() => editingSidebarDashId !== d.id && setActiveDashId(d.id)}
              >
                <div className="flex-1 min-w-0">
                  {editingSidebarDashId === d.id ? (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        ref={sidebarInputRef}
                        type="text"
                        value={editingSidebarName}
                        onChange={(e) => setEditingSidebarName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveRenameSidebar();
                          if (e.key === 'Escape') handleCancelRenameSidebar();
                        }}
                        onBlur={handleSaveRenameSidebar}
                        className="text-[11px] font-bold text-slate-700 bg-white border border-orange-300 rounded px-2 py-1 w-full focus:outline-none focus:ring-1 focus:ring-orange-500"
                      />
                    </div>
                  ) : (
                    <>
                      <span className={`text-[11px] font-bold truncate block ${d.id === activeDashId ? 'text-orange-700' : 'text-slate-600'}`}>
                        {d.name}
                      </span>
                      <span className="text-[9px] text-slate-400">{d.layouts.length} grafici</span>
                    </>
                  )}
                </div>
                {editingSidebarDashId !== d.id && (
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                    <button 
                      onClick={(e) => handleStartRenameSidebar(d, e)} 
                      className="p-1 hover:text-orange-600 hover:bg-orange-50 rounded transition-all text-slate-400"
                      title="Rinomina"
                    >
                      <Icons.Edit />
                    </button>
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleDeleteDashboard(d.id); }} 
                      className="p-1 hover:text-red-500 hover:bg-red-50 rounded transition-all text-slate-400"
                      title="Elimina"
                    >
                      <Icons.Trash />
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Toggle Sidebar */}
      <button 
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`absolute bottom-4 z-20 w-8 h-8 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-md hover:bg-slate-50 transition-all ${isSidebarOpen ? 'left-[268px]' : 'left-4'}`}
      >
        <div className={`transition-transform duration-300 ${isSidebarOpen ? '' : 'rotate-180'}`}>
          <Icons.ChevronLeft />
        </div>
      </button>

      {/* Main Canvas Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!currentDash ? (
          <div className="flex-1 flex flex-col items-center justify-center opacity-40">
            <div className="w-20 h-20 bg-white rounded-3xl flex items-center justify-center mb-6 shadow-sm">
              <Icons.Layout />
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Seleziona o crea una dashboard</p>
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="bg-white border-b border-slate-200 px-6 py-4 flex justify-between items-center shrink-0">
              <div className="flex items-center gap-4">
                {isEditingName ? (
                  <div className="flex items-center gap-2">
                    <input 
                      className="text-xl font-black text-slate-900 bg-slate-50 border-2 border-orange-500 rounded-lg px-3 py-1 focus:outline-none"
                      value={currentDash.name}
                      onChange={(e) => {
                        saveDashboard({ ...currentDash, name: e.target.value });
                        setHasUnsavedChanges(true);
                      }}
                      onBlur={() => setIsEditingName(false)}
                      onKeyDown={(e) => e.key === 'Enter' && setIsEditingName(false)}
                      autoFocus
                    />
                    <button
                      onClick={() => setIsEditingName(false)}
                      className="p-1.5 bg-orange-100 text-orange-600 rounded-lg hover:bg-orange-200"
                    >
                      <Icons.Check />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 group">
                    <h2 className="text-xl font-black text-slate-900">
                      {currentDash.name}
                    </h2>
                    <button 
                      onClick={() => setIsEditingName(true)} 
                      className="p-1.5 text-slate-400 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                      title="Rinomina dashboard"
                    >
                      <Icons.Edit />
                    </button>
                  </div>
                )}
                <span className="text-[10px] text-slate-400 bg-slate-100 px-3 py-1 rounded-full font-bold">
                  {currentDash.layouts.length} grafici
                </span>
                {hasUnsavedChanges && (
                  <span className="text-[10px] text-orange-600 bg-orange-50 px-3 py-1 rounded-full font-bold animate-pulse">
                    Modifiche non salvate
                  </span>
                )}
                {isPreviewMode && (
                  <span className="text-[10px] text-green-600 bg-green-50 px-3 py-1 rounded-full font-bold">
                    Modalita Anteprima
                  </span>
                )}
              </div>
              <div className="flex gap-3">
                {isPreviewMode ? (
                  <button 
                    onClick={handleExitPreview}
                    className="px-5 py-2.5 bg-slate-600 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-700 transition-all flex items-center gap-2"
                  >
                    <Icons.Edit /> Modifica
                  </button>
                ) : (
                  <>
                    <button 
                      onClick={() => setChartSelectorOpen(true)}
                      className="px-5 py-2.5 bg-orange-600 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-orange-700 transition-all shadow-lg shadow-orange-100 flex items-center gap-2"
                    >
                      <Icons.Plus /> Aggiungi Grafico
                    </button>
                    <button 
                      onClick={handleSaveDashboard}
                      className={`px-5 py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all flex items-center gap-2 ${
                        hasUnsavedChanges 
                          ? 'bg-green-600 text-white hover:bg-green-700 shadow-lg shadow-green-100' 
                          : 'bg-green-100 text-green-700 hover:bg-green-200'
                      }`}
                    >
                      <Icons.Save /> Salva
                    </button>
                  </>
                )}
                <button 
                  onClick={handleExportPDF}
                  className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-900 transition-all flex items-center gap-2"
                >
                  <Icons.Download /> Esporta
                </button>
              </div>
            </div>

            {/* Canvas */}
            <div 
              ref={canvasRef}
              className="flex-1 relative overflow-auto bg-[#f1f5f9]"
              style={{ 
                backgroundImage: 'radial-gradient(circle, #cbd5e1 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
              onClick={handleCanvasClick}
            >
              <div className="min-w-[1200px] min-h-[800px] relative">
                {currentDash.layouts.length === 0 ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <div className="bg-white rounded-2xl p-8 shadow-sm border-2 border-dashed border-slate-300 text-center">
                      <Icons.Layout />
                      <p className="text-sm font-bold text-slate-500 mt-4">Dashboard vuota</p>
                      <p className="text-xs text-slate-400 mt-1">Clicca "Aggiungi Grafico" per iniziare</p>
                    </div>
                  </div>
                ) : isPreviewMode ? (
                  currentDash.layouts.map((layout, idx) => {
                    const chart = savedCharts.find(c => c.id === layout.chartId);
                    return (
                      <div
                        key={`${layout.chartId}-${idx}`}
                        className="absolute bg-white rounded-2xl border-2 border-slate-200 shadow-lg overflow-hidden flex flex-col"
                        style={{ left: layout.x, top: layout.y, width: layout.width, height: layout.height }}
                      >
                        <div className="flex-1 p-3 flex items-center justify-center overflow-hidden">
                          {chart ? (
                            <ChartViewer config={chart.plotlyConfig} height={layout.height - 24} />
                          ) : (
                            <span className="text-slate-400 text-xs">Grafico non disponibile</span>
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  currentDash.layouts.map((layout, idx) => {
                    const chart = savedCharts.find(c => c.id === layout.chartId);
                    return (
                      <DraggableChart
                        key={`${layout.chartId}-${idx}`}
                        layout={layout}
                        chart={chart}
                        chartConfig={getChartConfig(layout.chartId)}
                        onUpdate={(updates) => handleUpdateLayout(idx, updates)}
                        onRemove={() => handleRemoveFromDash(idx)}
                        isSelected={selectedChartIndex === idx}
                        onSelect={() => setSelectedChartIndex(idx)}
                        onConfigure={() => setConfiguringChartId(layout.chartId)}
                        onDoubleClick={() => setConfiguringChartId(layout.chartId)}
                      />
                    );
                  })
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Pannello Configurazione Grafico */}
      {configuringChart && (
        <ChartConfigPanel
          chart={{ ...configuringChart, plotlyConfig: getChartConfig(configuringChart.id) }}
          onUpdate={(newConfig) => handleUpdateChartConfig(configuringChart.id, newConfig)}
          onClose={handleCloseConfigPanel}
          onPreview={(previewCfg) => handlePreviewChartConfig(configuringChart.id, previewCfg)}
        />
      )}
    </div>
  );
};

export default DashboardManager;