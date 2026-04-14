import React, { useState, useEffect, useRef, useCallback } from 'react';
import { databaseApi, SchemaResponse, TablePreviewResponse, ConnectionStatus, Relationship, TableInfo } from '../../api/databaseApi';
import { Icons } from '../Layout/Icons';
import DataQualityAudit from './DataQualityAudit';

interface TablePosition {
  x: number;
  y: number;
}

interface AnalysisReport {
  success: boolean;
  generated_at?: string;
  schema?: string;
  summary?: string;
  domain?: string;
  tables_count?: number;
  tables_analysis?: any[];
  data_insights?: any;
  report_markdown?: string;
  error?: string;
  message?: string;
}

const DatabaseSchema: React.FC = () => {
  const [activeView, setActiveView] = useState<'relational' | 'tables' | 'analysis' | 'audit'>('relational');
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [tablePreview, setTablePreview] = useState<TablePreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [_error, setError] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  
  // Analysis report state
  const [analysisReport, setAnalysisReport] = useState<AnalysisReport | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  // Canvas state for relational schema
  const [tablePositions, setTablePositions] = useState<Record<string, TablePosition>>({});
  const [draggingTable, setDraggingTable] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [hoveredRelation, setHoveredRelation] = useState<number | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSchema();
  }, []);

  useEffect(() => {
    if (selectedTable && activeView === 'tables') {
      loadTablePreview(selectedTable);
    }
  }, [selectedTable, activeView]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const loadSchema = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const status = await databaseApi.getStatus();
      setConnectionStatus(status);
      
      if (status.connected && status.active_database) {
        const [schemaData, relData] = await Promise.all([
          databaseApi.getSchema(),
          databaseApi.getRelationships()
        ]);
        setSchema(schemaData);
        setRelationships(relData.relationships || []);
        if (schemaData.tables.length > 0) {
          setSelectedTable(schemaData.tables[0].name);
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Errore nel caricamento dello schema');
    } finally {
      setIsLoading(false);
    }
  };

  // Load analysis report
  const loadAnalysisReport = async () => {
    try {
      const baseUrl = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');
      const response = await fetch(`${baseUrl}/api/database/analysis-report`);
      const data = await response.json();
      if (data.success !== false) {
        setAnalysisReport(data);
      }
    } catch (err) {
      console.log('No cached analysis report');
    }
  };

  // Generate new analysis
  const generateAnalysis = async () => {
    setIsAnalyzing(true);
    try {
      const baseUrl = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');
      const response = await fetch(`${baseUrl}/api/database/analyze`, { method: 'POST' });
      const data = await response.json();
      setAnalysisReport(data);
    } catch (err: any) {
      setAnalysisReport({ success: false, error: err.message });
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Load analysis when switching to analysis tab
  useEffect(() => {
    if (activeView === 'analysis' && !analysisReport) {
      loadAnalysisReport();
    }
  }, [activeView]);

  const getTableType = (tableName: string, tableInfo?: TableInfo): 'fact' | 'dimension' | 'view' | 'other' => {
    // Check if it's a view based on API type field
    if (tableInfo?.type === 'view') return 'view';
    const match = schema?.tables.find(t => t.name === tableName);
    if (match?.type === 'view') return 'view';
    if (tableName.startsWith('fact_')) return 'fact';
    if (tableName.startsWith('dim_')) return 'dimension';
    return 'other';
  };

  // Initialize table positions - grid layout to avoid overlaps
  const initializePositions = useCallback((tables: TableInfo[]) => {
    const positions: Record<string, TablePosition> = {};
    const tableWidth = 220;
    const tableHeight = 240;
    const gapX = 60;
    const gapY = 40;
    const startX = 40;
    const startY = 40;
    
    const factTables = tables.filter(t => getTableType(t.name, t) === 'fact');
    const dimTables = tables.filter(t => getTableType(t.name, t) === 'dimension');
    const viewTables = tables.filter(t => getTableType(t.name, t) === 'view');
    const otherTables = tables.filter(t => getTableType(t.name, t) === 'other');
    
    // Calculate columns based on available width
    const cols = 4;
    let currentRow = 0;
    
    // Place fact tables first (top row, centered)
    const factStartCol = Math.floor((cols - factTables.length) / 2);
    factTables.forEach((table, i) => {
      positions[table.name] = {
        x: startX + (factStartCol + i) * (tableWidth + gapX),
        y: startY
      };
    });
    currentRow = factTables.length > 0 ? 1 : 0;
    
    // Place dimension tables in rows below
    dimTables.forEach((table, i) => {
      positions[table.name] = {
        x: startX + (i % cols) * (tableWidth + gapX),
        y: startY + currentRow * (tableHeight + gapY) + (Math.floor(i / cols) * (tableHeight + gapY))
      };
    });
    const dimRows = Math.ceil(dimTables.length / cols);
    currentRow += dimRows;
    
    // Place other tables
    otherTables.forEach((table, i) => {
      positions[table.name] = {
        x: startX + (i % cols) * (tableWidth + gapX),
        y: startY + currentRow * (tableHeight + gapY) + (Math.floor(i / cols) * (tableHeight + gapY))
      };
    });
    const otherRows = Math.ceil(otherTables.length / cols);
    currentRow += otherRows;
    
    // Place views at the bottom
    viewTables.forEach((table, i) => {
      positions[table.name] = {
        x: startX + (i % cols) * (tableWidth + gapX),
        y: startY + currentRow * (tableHeight + gapY) + (Math.floor(i / cols) * (tableHeight + gapY))
      };
    });
    
    setTablePositions(positions);
  }, []);

  // Initialize positions when schema loads
  useEffect(() => {
    if (schema?.tables && Object.keys(tablePositions).length === 0) {
      initializePositions(schema.tables);
    }
  }, [schema, tablePositions, initializePositions]);

  // Drag handlers - optimized for smooth movement
  const handleMouseDown = (tableName: string, e: React.MouseEvent) => {
    e.preventDefault();
    const pos = tablePositions[tableName];
    if (pos && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      setDraggingTable(tableName);
      setDragOffset({
        x: e.clientX - rect.left - pos.x,
        y: e.clientY - rect.top - pos.y
      });
    }
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!draggingTable || !canvasRef.current) return;
    
    const rect = canvasRef.current.getBoundingClientRect();
    const newX = Math.max(0, e.clientX - rect.left - dragOffset.x);
    const newY = Math.max(0, e.clientY - rect.top - dragOffset.y);
    
    // Use requestAnimationFrame for smooth updates
    requestAnimationFrame(() => {
      setTablePositions(prev => ({
        ...prev,
        [draggingTable]: { x: newX, y: newY }
      }));
    });
  }, [draggingTable, dragOffset]);

  const handleMouseUp = useCallback(() => {
    setDraggingTable(null);
  }, []);

  useEffect(() => {
    if (draggingTable) {
      document.body.style.cursor = 'grabbing';
      document.body.style.userSelect = 'none';
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [draggingTable, handleMouseMove, handleMouseUp]);

  // Calculate connection points for relationship lines
  const getConnectionPoints = (fromTable: string, toTable: string) => {
    const fromPos = tablePositions[fromTable];
    const toPos = tablePositions[toTable];
    if (!fromPos || !toPos) return null;
    
    const tableWidth = 220;
    const tableHeight = 220;
    
    const fromCenterX = fromPos.x + tableWidth / 2;
    const fromCenterY = fromPos.y + tableHeight / 2;
    const toCenterX = toPos.x + tableWidth / 2;
    const toCenterY = toPos.y + tableHeight / 2;
    
    // Determine which side to connect from/to
    const dx = toCenterX - fromCenterX;
    const dy = toCenterY - fromCenterY;
    
    let fromX, fromY, toX, toY;
    
    if (Math.abs(dx) > Math.abs(dy)) {
      // Connect horizontally
      if (dx > 0) {
        fromX = fromPos.x + tableWidth;
        toX = toPos.x;
      } else {
        fromX = fromPos.x;
        toX = toPos.x + tableWidth;
      }
      fromY = fromCenterY;
      toY = toCenterY;
    } else {
      // Connect vertically
      fromX = fromCenterX;
      toX = toCenterX;
      if (dy > 0) {
        fromY = fromPos.y + tableHeight;
        toY = toPos.y;
      } else {
        fromY = fromPos.y;
        toY = toPos.y + tableHeight;
      }
    }
    
    return { fromX, fromY, toX, toY };
  };

  const loadTablePreview = async (tableName: string) => {
    setIsLoadingPreview(true);
    try {
      const preview = await databaseApi.getTablePreview(tableName, 50);
      setTablePreview(preview);
    } catch (err) {
      console.error('Error loading preview:', err);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const tableData = schema?.tables.find(t => t.name === selectedTable);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-sm font-bold text-slate-500">Caricamento schema...</p>
        </div>
      </div>
    );
  }

  if (!connectionStatus?.connected) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Icons.Database />
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Database non connesso</h3>
          <p className="text-sm text-slate-500 mb-4">Vai nelle Impostazioni per configurare la connessione al database.</p>
          <button 
            onClick={loadSchema}
            className="px-6 py-2 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700"
          >
            Riprova
          </button>
        </div>
      </div>
    );
  }

  if (!connectionStatus?.active_database) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 bg-amber-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Icons.Database />
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Nessun database selezionato</h3>
          <p className="text-sm text-slate-500 mb-4">Vai nelle Impostazioni e seleziona un database da utilizzare.</p>
          <button 
            onClick={loadSchema}
            className="px-6 py-2 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700"
          >
            Riprova
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col bg-white overflow-hidden">
      <div className="flex items-center justify-between pb-4 shrink-0">
        <div>
          <h2 className="text-xl font-black text-slate-900 tracking-tight">Struttura Database</h2>
          <p className="text-slate-500 text-sm mt-1">
            Database: <span className="font-bold text-orange-600">{connectionStatus?.active_database || schema?.database}</span> • {schema?.tables.filter(t => t.type !== 'view').length || 0} tabelle
            {(schema?.tables.filter(t => t.type === 'view').length || 0) > 0 && <span className="ml-1">• {schema?.tables.filter(t => t.type === 'view').length} viste</span>}
            {relationships.length > 0 && <span className="ml-2">• {relationships.length} relazioni</span>}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={loadSchema}
            className="p-2 text-slate-400 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all"
            title="Aggiorna schema"
          >
            <Icons.Refresh />
          </button>
          <div className="flex bg-slate-100 p-1 rounded-xl">
             <button 
               onClick={() => setActiveView('relational')}
               className={`px-6 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all ${activeView === 'relational' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
             >
               Schema Relazionale
             </button>
             <button 
               onClick={() => setActiveView('tables')}
               className={`px-6 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all ${activeView === 'tables' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
             >
               Esplora Tabelle
             </button>
             <button
               onClick={() => setActiveView('analysis')}
               className={`px-6 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all ${activeView === 'analysis' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
             >
               Analisi Database
             </button>
             <button
               onClick={() => setActiveView('audit')}
               className={`px-6 py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all ${activeView === 'audit' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
             >
               Data Quality
             </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {activeView === 'relational' ? (
          <section className="h-full">
            {/* Interactive Canvas - Same style as Dashboard */}
            <div 
              ref={canvasRef}
              className="bg-slate-50 rounded-3xl border border-slate-200 relative overflow-auto"
              style={{ minHeight: 'calc(100vh - 200px)', minWidth: '100%' }}
            >
              {/* Grid Background - Same as Dashboard */}
              <div 
                className="absolute inset-0 opacity-[0.4]" 
                style={{ 
                  backgroundImage: 'radial-gradient(#cbd5e1 1px, transparent 1px)',
                  backgroundSize: '20px 20px'
                }}
              ></div>

              {/* SVG Layer for Relationship Lines */}
              <svg className="absolute inset-0 w-full h-full" style={{ zIndex: 5, pointerEvents: 'none' }}>
                <defs>
                  <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                    <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
                  </marker>
                  <marker id="arrowhead-hover" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                    <polygon points="0 0, 8 3, 0 6" fill="#f97316" />
                  </marker>
                </defs>
                {relationships.map((rel, idx) => {
                  const points = getConnectionPoints(rel.from_table, rel.to_table);
                  if (!points) return null;
                  
                  const { fromX, fromY, toX, toY } = points;
                  const midX = (fromX + toX) / 2;
                  const midY = (fromY + toY) / 2;
                  const isHovered = hoveredRelation === idx;
                  
                  return (
                    <g key={idx}>
                      {/* Invisible thick path for easier hover detection */}
                      <path
                        d={`M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`}
                        stroke="transparent"
                        strokeWidth="20"
                        fill="none"
                        style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                        onMouseEnter={() => setHoveredRelation(idx)}
                        onMouseLeave={() => setHoveredRelation(null)}
                      />
                      {/* Visible connection line */}
                      <path
                        d={`M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`}
                        stroke={isHovered ? '#f97316' : '#cbd5e1'}
                        strokeWidth={isHovered ? 2.5 : 1.5}
                        fill="none"
                        markerEnd={isHovered ? 'url(#arrowhead-hover)' : 'url(#arrowhead)'}
                        style={{ transition: 'stroke 0.15s, stroke-width 0.15s' }}
                      />
                      {/* Tooltip on hover */}
                      {isHovered && (
                        <g>
                          <rect 
                            x={midX - 80} 
                            y={midY - 28} 
                            width="160" 
                            height="36" 
                            rx="8" 
                            fill="white" 
                            stroke="#e2e8f0"
                            strokeWidth="1"
                            filter="drop-shadow(0 4px 6px rgba(0,0,0,0.1))"
                          />
                          <text x={midX} y={midY - 10} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="500">
                            {rel.from_table}.{rel.from_column}
                          </text>
                          <text x={midX} y={midY + 4} textAnchor="middle" fill="#f97316" fontSize="10" fontWeight="700">
                            → {rel.relationship_type} →
                          </text>
                          <text x={midX} y={midY + 18} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="500">
                            {rel.to_table}.{rel.to_column}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Table Nodes */}
              {schema?.tables.map((table) => {
                const pos = tablePositions[table.name];
                if (!pos) return null;
                const type = getTableType(table.name, table);
                
                return (
                  <DraggableTableNode
                    key={table.name}
                    table={table}
                    type={type}
                    position={pos}
                    isDragging={draggingTable === table.name}
                    onMouseDown={(e) => handleMouseDown(table.name, e)}
                  />
                );
              })}
            </div>
          </section>
        ) : activeView === 'tables' ? (
          <section className="space-y-8">
            {/* Custom Dropdown */}
            <div className="flex items-center gap-6 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex-1" ref={dropdownRef}>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Seleziona Tabella</p>
                <div className="relative">
                  <button
                    onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                    className="w-full lg:w-96 flex items-center justify-between bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 text-left hover:border-orange-300 focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-2.5 h-2.5 rounded-full ${
                        getTableType(selectedTable) === 'fact' ? 'bg-orange-500' :
                        getTableType(selectedTable) === 'dimension' ? 'bg-blue-500' :
                        getTableType(selectedTable) === 'view' ? 'bg-purple-500' : 'bg-slate-400'
                      }`}></div>
                      <span className="text-sm font-bold text-slate-900">{selectedTable.toUpperCase()}</span>
                      <span className="text-[10px] text-slate-400 font-medium">
                        {getTableType(selectedTable) === 'fact' ? 'Fact' :
                         getTableType(selectedTable) === 'dimension' ? 'Dim' :
                         getTableType(selectedTable) === 'view' ? 'View' : ''}
                      </span>
                    </div>
                    <svg className={`w-5 h-5 text-slate-400 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {isDropdownOpen && (
                    <div className="absolute z-50 mt-2 w-full lg:w-96 bg-white border-2 border-slate-200 rounded-xl shadow-xl overflow-hidden">
                      <div className="max-h-72 overflow-y-auto">
                        {(schema?.tables.filter(t => getTableType(t.name, t) === 'fact').length ?? 0) > 0 && (
                          <div>
                            <div className="px-4 py-2 bg-orange-50 border-b border-orange-100 sticky top-0">
                              <span className="text-[10px] font-bold text-orange-600 uppercase tracking-widest">Fact Tables</span>
                            </div>
                            {schema?.tables.filter(t => getTableType(t.name, t) === 'fact')?.map(t => (
                              <button key={t.name} onClick={() => { setSelectedTable(t.name); setIsDropdownOpen(false); }}
                                className={`w-full flex items-center justify-between px-4 py-3 hover:bg-orange-50 transition-colors ${selectedTable === t.name ? 'bg-orange-50' : ''}`}>
                                <div className="flex items-center gap-3">
                                  <div className="w-2 h-2 rounded-full bg-orange-500"></div>
                                  <span className="text-sm font-bold text-slate-700">{t.name.toUpperCase()}</span>
                                </div>
                                <span className="text-[10px] text-slate-400">{t.row_count?.toLocaleString()}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {(schema?.tables.filter(t => getTableType(t.name, t) === 'dimension').length ?? 0) > 0 && (
                          <div>
                            <div className="px-4 py-2 bg-blue-50 border-b border-blue-100 sticky top-0">
                              <span className="text-[10px] font-bold text-blue-600 uppercase tracking-widest">Dimensions</span>
                            </div>
                            {schema?.tables.filter(t => getTableType(t.name, t) === 'dimension')?.map(t => (
                              <button key={t.name} onClick={() => { setSelectedTable(t.name); setIsDropdownOpen(false); }}
                                className={`w-full flex items-center justify-between px-4 py-3 hover:bg-blue-50 transition-colors ${selectedTable === t.name ? 'bg-blue-50' : ''}`}>
                                <div className="flex items-center gap-3">
                                  <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                                  <span className="text-sm font-bold text-slate-700">{t.name.toUpperCase()}</span>
                                </div>
                                <span className="text-[10px] text-slate-400">{t.row_count?.toLocaleString()}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {(schema?.tables.filter(t => getTableType(t.name, t) === 'other').length ?? 0) > 0 && (
                          <div>
                            <div className="px-4 py-2 bg-slate-100 border-b border-slate-200 sticky top-0">
                              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Other Tables</span>
                            </div>
                            {schema?.tables.filter(t => getTableType(t.name, t) === 'other')?.map(t => (
                              <button key={t.name} onClick={() => { setSelectedTable(t.name); setIsDropdownOpen(false); }}
                                className={`w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors ${selectedTable === t.name ? 'bg-slate-100' : ''}`}>
                                <div className="flex items-center gap-3">
                                  <div className="w-2 h-2 rounded-full bg-slate-400"></div>
                                  <span className="text-sm font-bold text-slate-700">{t.name.toUpperCase()}</span>
                                </div>
                                <span className="text-[10px] text-slate-400">{t.row_count?.toLocaleString()}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {(schema?.tables.filter(t => getTableType(t.name, t) === 'view').length ?? 0) > 0 && (
                          <div>
                            <div className="px-4 py-2 bg-purple-50 border-b border-purple-100 sticky top-0">
                              <span className="text-[10px] font-bold text-purple-600 uppercase tracking-widest">Views</span>
                            </div>
                            {schema?.tables.filter(t => getTableType(t.name, t) === 'view')?.map(t => (
                              <button key={t.name} onClick={() => { setSelectedTable(t.name); setIsDropdownOpen(false); }}
                                className={`w-full flex items-center justify-between px-4 py-3 hover:bg-purple-50 transition-colors ${selectedTable === t.name ? 'bg-purple-50' : ''}`}>
                                <div className="flex items-center gap-3">
                                  <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                                  <span className="text-sm font-bold text-slate-700">{t.name.toUpperCase()}</span>
                                  <span className="text-[9px] px-1.5 py-0.5 bg-purple-100 text-purple-600 rounded font-bold">VIEW</span>
                                </div>
                                <span className="text-[10px] text-slate-400">{t.row_count?.toLocaleString() ?? '—'}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <div className="hidden lg:flex gap-8">
                 <div className="text-center px-6 border-l border-slate-200">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Colonne</p>
                    <p className="text-2xl font-black text-slate-900">{tableData?.columns.length || 0}</p>
                 </div>
                 <div className="text-center px-6 border-l border-slate-200">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Totale Record</p>
                    <p className="text-2xl font-black text-slate-900">{tableData?.row_count?.toLocaleString() || 0}</p>
                 </div>
              </div>
            </div>

            {isLoadingPreview ? (
              <div className="bg-white border border-slate-200 rounded-3xl p-12 flex items-center justify-center">
                <div className="text-center">
                  <div className="w-8 h-8 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin mx-auto mb-3"></div>
                  <p className="text-sm text-slate-500">Caricamento dati...</p>
                </div>
              </div>
            ) : tablePreview && tablePreview.rows.length > 0 ? (
              <div className="bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-50 border-b border-slate-100">
                      <tr>
                        {tablePreview.columns.map(col => (
                          <th key={col} className="px-6 py-5 font-black text-slate-900 uppercase tracking-tight whitespace-nowrap">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {tablePreview.rows.map((row, i) => (
                        <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                          {tablePreview.columns.map((col) => (
                            <td key={col} className="px-6 py-4 text-slate-600 font-medium whitespace-nowrap max-w-[200px] truncate">
                              {row[col] !== null && row[col] !== undefined ? String(row[col]) : '-'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="p-6 bg-slate-50 border-t border-slate-100 flex justify-between items-center">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                    Mostrando {tablePreview.rows.length} di {tablePreview.total_rows.toLocaleString()} righe
                  </p>
                  <p className="text-[10px] font-bold text-orange-600 uppercase tracking-widest">
                    Preview limitata a {tablePreview.preview_limit} record
                  </p>
                </div>
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center">
                <p className="text-sm text-slate-500">Nessun dato disponibile per questa tabella</p>
              </div>
            )}
          </section>
        ) : activeView === 'analysis' ? (
          <section className="space-y-6">
            {/* Analysis Header */}
            <div className="flex items-center justify-between bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Analisi Automatica del Database</h3>
                <p className="text-sm text-slate-500 mt-1">
                  {analysisReport?.generated_at 
                    ? `Ultimo aggiornamento: ${new Date(analysisReport.generated_at).toLocaleString('it-IT')}`
                    : 'Genera un report dettagliato della struttura e dei contenuti del database'}
                </p>
              </div>
              <button
                onClick={generateAnalysis}
                disabled={isAnalyzing}
                className="px-6 py-3 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
              >
                {isAnalyzing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    Analisi in corso...
                  </>
                ) : (
                  <>
                    <Icons.BarChart />
                    {analysisReport ? 'Rigenera Analisi' : 'Genera Analisi'}
                  </>
                )}
              </button>
            </div>

            {/* Analysis Content */}
            {isAnalyzing ? (
              <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center">
                <div className="w-12 h-12 border-4 border-orange-200 border-t-orange-600 rounded-full animate-spin mx-auto mb-4"></div>
                <h4 className="text-lg font-bold text-slate-900 mb-2">Analisi del Database in Corso</h4>
                <p className="text-sm text-slate-500">Stiamo analizzando la struttura, i dati e generando insight...</p>
                <p className="text-xs text-slate-400 mt-2">Questa operazione potrebbe richiedere 30-60 secondi</p>
              </div>
            ) : analysisReport?.success ? (
              /* Report Style - Documento continuo tipo PDF/Word */
              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm">
                <div className="max-w-4xl mx-auto px-12 py-10">
                  {/* Document Header */}
                  <div className="border-b-2 border-slate-200 pb-6 mb-8">
                    <h1 className="text-3xl font-bold text-slate-900 mb-2">Report di Analisi del Database</h1>
                    <p className="text-sm text-slate-500">
                      Generato il {analysisReport.generated_at ? new Date(analysisReport.generated_at).toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                    </p>
                  </div>

                  {/* 1. Executive Summary */}
                  <section className="mb-10">
                    <h2 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-100">1. Sintesi Esecutiva</h2>
                    <p className="text-slate-700 leading-relaxed mb-4">
                      Il database analizzato appartiene al dominio <strong className="text-orange-600">{analysisReport.domain}</strong>. 
                      {analysisReport.summary}
                    </p>
                    {analysisReport.data_insights?.time_range && (
                      <p className="text-slate-700 leading-relaxed">
                        <strong>Periodo di copertura dei dati:</strong> I dati presenti nel database coprono il periodo dal <strong>{analysisReport.data_insights.time_range}</strong>, 
                        permettendo analisi storiche e di trend su questo orizzonte temporale.
                      </p>
                    )}
                  </section>

                  {/* 2. Struttura del Database */}
                  <section className="mb-10">
                    <h2 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-100">2. Struttura del Database</h2>
                    <p className="text-slate-700 leading-relaxed mb-4">
                      Il database è composto da <strong>{analysisReport.tables_count} tabelle</strong> organizzate secondo un modello dimensionale 
                      che distingue tra tabelle dei fatti (fact tables) contenenti le metriche transazionali, e tabelle dimensionali (dimension tables) 
                      che forniscono il contesto descrittivo per l'analisi.
                    </p>
                    
                    {analysisReport.tables_analysis && analysisReport.tables_analysis.length > 0 && (
                      <div className="space-y-6 mt-6">
                        {analysisReport.tables_analysis.map((table: any, i: number) => (
                          <div key={i} className="pl-4 border-l-4 border-slate-200">
                            <h3 className="text-lg font-semibold text-slate-900 mb-2">
                              {table.table_name}
                              <span className={`ml-3 text-xs font-medium px-2 py-1 rounded ${
                                table.table_type === 'fact' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'
                              }`}>
                                {table.table_type === 'fact' ? 'Tabella dei Fatti' : 'Tabella Dimensionale'}
                              </span>
                            </h3>
                            <p className="text-slate-700 leading-relaxed mb-3">{table.business_description}</p>
                            {table.suggested_analyses?.length > 0 && (
                              <div className="text-slate-600 text-sm">
                                <strong>Analisi possibili:</strong>
                                <ul className="list-disc list-inside mt-1 space-y-1">
                                  {table.suggested_analyses.map((a: string, j: number) => (
                                    <li key={j}>{a}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* 3. Metriche e Dimensioni */}
                  <section className="mb-10">
                    <h2 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-100">3. Metriche e Dimensioni di Analisi</h2>
                    
                    {analysisReport.data_insights?.key_metrics?.length > 0 && (
                      <div className="mb-6">
                        <h3 className="text-lg font-semibold text-slate-900 mb-3">3.1 Metriche Principali</h3>
                        <p className="text-slate-700 leading-relaxed mb-3">
                          Le seguenti metriche quantitative sono disponibili per l'analisi e rappresentano i principali indicatori di performance (KPI) del business:
                        </p>
                        <ul className="list-disc list-inside text-slate-700 space-y-1 pl-4">
                          {analysisReport.data_insights.key_metrics.map((m: string, i: number) => (
                            <li key={i}><strong>{m}</strong></li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {analysisReport.data_insights?.key_dimensions?.length > 0 && (
                      <div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-3">3.2 Dimensioni di Analisi</h3>
                        <p className="text-slate-700 leading-relaxed mb-3">
                          I dati possono essere analizzati e segmentati secondo le seguenti dimensioni, che permettono di effettuare drill-down, 
                          confronti e aggregazioni a diversi livelli di dettaglio:
                        </p>
                        <ul className="list-disc list-inside text-slate-700 space-y-1 pl-4">
                          {analysisReport.data_insights.key_dimensions.map((d: string, i: number) => (
                            <li key={i}><strong>{d}</strong></li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>

                  {/* 4. Domande di Esempio */}
                  {analysisReport.data_insights?.suggested_questions?.length > 0 && (
                    <section className="mb-10">
                      <h2 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-100">4. Esempi di Domande per l'Analisi</h2>
                      <p className="text-slate-700 leading-relaxed mb-4">
                        Per iniziare ad esplorare i dati, ecco alcuni esempi di domande che è possibile porre al sistema. 
                        Queste domande sono state formulate sulla base della struttura del database e delle metriche disponibili:
                      </p>
                      <ol className="list-decimal list-inside text-slate-700 space-y-2 pl-4">
                        {analysisReport.data_insights.suggested_questions.map((q: string, i: number) => (
                          <li key={i} className="leading-relaxed">{q}</li>
                        ))}
                      </ol>
                    </section>
                  )}

                  {/* 5. Note Conclusive */}
                  <section className="mb-6">
                    <h2 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-100">5. Note Conclusive</h2>
                    <p className="text-slate-700 leading-relaxed">
                      Questo report fornisce una panoramica completa della struttura del database e delle possibilità di analisi. 
                      Per ottenere risultati ottimali durante l'interrogazione dei dati, si consiglia di formulare domande specifiche 
                      utilizzando le metriche e le dimensioni sopra descritte. Il sistema è in grado di generare automaticamente 
                      query SQL, visualizzazioni grafiche e insight basati sulle domande poste in linguaggio naturale.
                    </p>
                  </section>

                  {/* Document Footer */}
                  <div className="border-t-2 border-slate-200 pt-6 mt-8 text-center text-sm text-slate-400">
                    <p>Report generato automaticamente da DataChat BI Platform</p>
                  </div>
                </div>
              </div>
            ) : analysisReport?.error ? (
              <div className="bg-red-50 border border-red-200 rounded-3xl p-8 text-center">
                <p className="text-red-600 font-medium">{analysisReport.error}</p>
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center">
                <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Icons.Database />
                </div>
                <h4 className="text-lg font-bold text-slate-900 mb-2">Nessuna Analisi Disponibile</h4>
                <p className="text-sm text-slate-500 mb-6">
                  Clicca su "Genera Analisi" per creare un report dettagliato del database.<br/>
                  L'analisi includerà la struttura delle tabelle, le caratteristiche dei dati e domande di esempio.
                </p>
              </div>
            )}
          </section>
        ) : activeView === 'audit' ? (
          <DataQualityAudit />
        ) : null}
      </div>
    </div>
  );
};

// Draggable Table Node for Canvas
interface DraggableTableNodeProps {
  table: TableInfo;
  type: 'fact' | 'dimension' | 'view' | 'other';
  position: TablePosition;
  isDragging: boolean;
  onMouseDown: (e: React.MouseEvent) => void;
}

const DraggableTableNode: React.FC<DraggableTableNodeProps> = ({ table, type, position, isDragging, onMouseDown }) => {
  const headerColor = type === 'fact' ? 'bg-orange-600' : type === 'dimension' ? 'bg-slate-700' : type === 'view' ? 'bg-purple-600' : 'bg-slate-500';

  return (
    <div
      className={`absolute bg-white rounded-xl w-[220px] overflow-hidden border select-none ${isDragging ? 'shadow-2xl border-orange-400 z-50' : 'shadow-lg border-slate-200 hover:shadow-xl hover:border-slate-300'}`}
      style={{
        transform: `translate(${position.x}px, ${position.y}px)`,
        cursor: isDragging ? 'grabbing' : 'grab',
        zIndex: isDragging ? 100 : 10,
        willChange: isDragging ? 'transform' : 'auto'
      }}
      onMouseDown={onMouseDown}
    >
      {/* Header */}
      <div className={`${headerColor} px-4 py-2.5 flex items-center justify-between`}>
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {type === 'view' && <span className="text-[8px] bg-white/20 text-white px-1.5 py-0.5 rounded font-bold shrink-0">VIEW</span>}
          <span className="text-[10px] font-black text-white uppercase tracking-widest truncate">{table.name}</span>
        </div>
        <span className="text-[9px] text-white/70 font-bold shrink-0 ml-1">{table.row_count?.toLocaleString() ?? '—'}</span>
      </div>
      
      {/* Columns */}
      <div className="p-3 space-y-1 max-h-[180px] overflow-y-auto bg-white">
        {table.columns.slice(0, 8).map((col) => (
          <div key={col.name} className="flex items-center justify-between text-[10px] py-1 px-2 rounded-lg hover:bg-slate-50">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {col.isPK && (
                <span className="text-[8px] text-orange-600 font-bold bg-orange-50 px-1.5 py-0.5 rounded">PK</span>
              )}
              {col.isFK && (
                <span className="text-[8px] text-blue-600 font-bold bg-blue-50 px-1.5 py-0.5 rounded">FK</span>
              )}
              <span className={`font-semibold truncate ${col.isPK ? 'text-slate-900' : 'text-slate-600'}`}>
                {col.name}
              </span>
            </div>
            <span className="text-[8px] font-mono text-slate-400 uppercase ml-2 shrink-0">
              {col.type.split(' ')[0].substring(0, 8)}
            </span>
          </div>
        ))}
        {table.columns.length > 8 && (
          <div className="text-[9px] text-slate-400 text-center py-1 font-medium">
            +{table.columns.length - 8} colonne
          </div>
        )}
      </div>
    </div>
  );
};

export default DatabaseSchema;