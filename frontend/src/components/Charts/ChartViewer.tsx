import React from 'react';
import Plot from 'react-plotly.js';

interface ChartViewerProps {
  config: any;
  height?: number;
}

const ChartViewer: React.FC<ChartViewerProps> = ({ config, height = 300 }) => {
  if (!config || !config.data) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-sm">
        Nessun grafico disponibile
      </div>
    );
  }

  const hasDropdownMenu = config.layout?.updatemenus && config.layout.updatemenus.length > 0;
  const effectiveHeight = hasDropdownMenu ? Math.max(height, 460) : height;

  // Per grafici con dropdown, rispetta i margini dal backend (che includono spazio per il filtro)
  const mergedLayout = {
    ...config.layout,
    autosize: true,
    height: effectiveHeight,
    paper_bgcolor: config.layout?.paper_bgcolor || 'transparent',
    plot_bgcolor: config.layout?.plot_bgcolor || 'transparent',
    font: { 
      family: 'Inter, system-ui, sans-serif', 
      size: config.layout?.font?.size || 11,
      color: config.layout?.font?.color || undefined
    },
  };

  // Solo sovrascrivere il margin se NON ci sono dropdown (il backend gestisce i margini per pie_with_filter)
  if (!hasDropdownMenu) {
    mergedLayout.margin = { t: 30, b: 40, l: 50, r: 30 };
  }

  return (
    <Plot
      data={config.data}
      layout={mergedLayout}
      config={{
        responsive: true,
        displayModeBar: false,
        displaylogo: false,
      }}
      style={{ width: '100%', height: '100%' }}
    />
  );
};

export default ChartViewer;