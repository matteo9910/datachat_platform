import React, { useState } from 'react';
import { databaseApi, TableInfo } from '../api/databaseApi';
import { useAppStore } from '../store/appStore';
import { LLMProvider } from '../types';

interface SetupWizardProps {
  onComplete: () => void;
}

type DataSourceType = 'postgresql' | 'supabase' | 'mysql' | 'bigquery';

const DATA_SOURCES = [
  { type: 'postgresql' as DataSourceType, name: 'PostgreSQL', description: 'Database relazionale open source', icon: '/logos/postgresql.png', available: true },
  { type: 'supabase' as DataSourceType, name: 'Supabase', description: 'PostgreSQL cloud con API', icon: '/logos/supabase.png', available: true },
  { type: 'mysql' as DataSourceType, name: 'MySQL', description: 'Database relazionale', icon: '/logos/mysql.png', available: false },
  { type: 'bigquery' as DataSourceType, name: 'BigQuery', description: 'Data warehouse Google Cloud', icon: '/logos/bigquery.png', available: false },
];

const LLM_PROVIDERS = [
  { id: LLMProvider.CLAUDE, name: 'Claude Sonnet 4.6', description: 'Ottimo per ragionamento complesso', color: 'orange' },
  { id: LLMProvider.AZURE, name: 'GPT-4.1', description: 'Bilanciato per analisi dati', color: 'blue' },
  { id: LLMProvider.GPT52, name: 'GPT-5.2', description: 'Modello avanzato per analisi complesse', color: 'purple' },
];

const SetupWizard: React.FC<SetupWizardProps> = ({ onComplete }) => {
  const { setLLMProvider } = useAppStore();
  const [step, setStep] = useState(1);
  const [selectedSource, setSelectedSource] = useState<DataSourceType | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState('5432');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [database, setDatabase] = useState('postgres');
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [isLoadingTables, setIsLoadingTables] = useState(false);
  const [selectedLLM, setSelectedLLM] = useState<LLMProvider>(LLMProvider.GPT52);

  const handleSourceSelect = (source: DataSourceType) => {
    setSelectedSource(source);
    if (source === 'supabase') { 
      setPort('6543'); 
      setDatabase('postgres'); 
    } else { 
      setPort('5432'); 
    }
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    setConnectionError('');
    try {
      const encodedUser = encodeURIComponent(username);
      const encodedPass = encodeURIComponent(password);
      const connectionString = `postgresql://${encodedUser}:${encodedPass}@${host}:${port}/${database}`;
      
      const status = await databaseApi.connectWithConnectionString(connectionString, displayName);
      
      if (status.connected) {
        // Save credentials immediately after successful connection
        localStorage.setItem('datachat-connection-credentials', JSON.stringify({
          connectionString,
          displayName: displayName || 'Database'
        }));
        localStorage.setItem('datachat-connection-config', JSON.stringify({
          source: selectedSource,
          displayName,
          host,
          port,
          username,
          database
        }));
        
        setIsLoadingTables(true);
        const schema = await databaseApi.getSchema();
        setTables(schema.tables);
        setSelectedTables(schema.tables.map(t => t.name));
        setIsLoadingTables(false);
        setStep(3);
      }
    } catch (error: any) {
      setConnectionError(error.response?.data?.detail || 'Connessione fallita. Verifica le credenziali.');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleTableToggle = (tableName: string) => {
    setSelectedTables(prev => 
      prev.includes(tableName) 
        ? prev.filter(t => t !== tableName) 
        : [...prev, tableName]
    );
  };

  const handleFinish = () => {
    localStorage.setItem('datachat-setup-complete', 'true');
    localStorage.setItem('datachat-selected-tables', JSON.stringify(selectedTables));
    localStorage.setItem('datachat-llm-provider', selectedLLM);
    setLLMProvider(selectedLLM);
    onComplete();
  };

  const canProceedStep2 = host && username && password && database;

  const getProviderStyle = (color: string, isSelected: boolean) => {
    if (!isSelected) return {};
    const colors: Record<string, { border: string; bg: string }> = {
      orange: { border: '#f97316', bg: '#fff7ed' },
      blue: { border: '#3b82f6', bg: '#eff6ff' },
      purple: { border: '#9333ea', bg: '#faf5ff' }
    };
    return { borderColor: colors[color]?.border, backgroundColor: colors[color]?.bg };
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-8 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-orange-600 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-black text-slate-900 tracking-tight">DataChat BI</h1>
              <p className="text-xs text-slate-500">Setup Wizard</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4].map((s) => (
              <div key={s} className="flex items-center">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${step === s ? 'bg-orange-600 text-white' : step > s ? 'bg-green-500 text-white' : 'bg-slate-200 text-slate-500'}`}>
                  {step > s ? '✓' : s}
                </div>
                {s < 4 && <div className={`w-8 h-1 mx-1 rounded ${step > s ? 'bg-green-500' : 'bg-slate-200'}`} />}
              </div>
            ))}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-3xl">
          
          {/* Step 1: Select Data Source */}
          {step === 1 && (
            <div className="text-center">
              <h2 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Configura il tuo progetto</h2>
              <p className="text-slate-500 mb-8">Seleziona la sorgente dati da collegare</p>
              <div className="grid grid-cols-2 gap-4 mb-8">
                {DATA_SOURCES.map((source) => (
                  <button 
                    key={source.type} 
                    onClick={() => source.available && handleSourceSelect(source.type)} 
                    disabled={!source.available}
                    className={`relative p-6 rounded-2xl border-2 text-left transition-all ${
                      selectedSource === source.type 
                        ? 'border-orange-500 bg-orange-50 shadow-lg' 
                        : source.available 
                          ? 'border-slate-200 bg-white hover:border-slate-300' 
                          : 'border-slate-100 bg-slate-50 opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <img src={source.icon} alt={source.name} className="w-12 h-12 object-contain" />
                      <div>
                        <p className="font-bold text-slate-900">{source.name}</p>
                        <p className="text-xs text-slate-500">{source.description}</p>
                      </div>
                    </div>
                    {!source.available && (
                      <span className="absolute top-3 right-3 text-[9px] font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-full">
                        COMING SOON
                      </span>
                    )}
                    {selectedSource === source.type && (
                      <div className="absolute top-3 right-3 w-6 h-6 bg-orange-600 rounded-full flex items-center justify-center text-white text-sm">
                        ✓
                      </div>
                    )}
                  </button>
                ))}
              </div>
              <button 
                onClick={() => setStep(2)} 
                disabled={!selectedSource} 
                className="px-8 py-3 bg-orange-600 text-white rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Continua
              </button>
            </div>
          )}

          {/* Step 2: Connection Configuration */}
          {step === 2 && (
            <div>
              <button onClick={() => setStep(1)} className="flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-6 text-sm">
                ← Indietro
              </button>
              <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center gap-4 mb-6">
                  <img src={DATA_SOURCES.find(s => s.type === selectedSource)?.icon} alt="" className="w-10 h-10 object-contain" />
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">Connetti a {DATA_SOURCES.find(s => s.type === selectedSource)?.name}</h3>
                    <p className="text-xs text-slate-500">Inserisci i dettagli della connessione</p>
                  </div>
                </div>
                
                {selectedSource === 'supabase' && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 text-sm text-amber-800">
                    <p className="font-semibold mb-1">Dove trovo queste informazioni?</p>
                    <p>Supabase Dashboard → Connect → Connection parameters</p>
                  </div>
                )}
                
                <div className="space-y-4">
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Display Name</label>
                    <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="es. Production Database" className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="col-span-2">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Host *</label>
                      <input type="text" value={host} onChange={(e) => setHost(e.target.value)} placeholder={selectedSource === 'supabase' ? 'aws-0-xx-xxxx.pooler.supabase.com' : 'localhost'} className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Port *</label>
                      <input type="text" value={port} onChange={(e) => setPort(e.target.value)} className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Username *</label>
                    <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder={selectedSource === 'supabase' ? 'postgres.xxxxx' : 'postgres'} className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Password *</label>
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Database Name *</label>
                    <input type="text" value={database} onChange={(e) => setDatabase(e.target.value)} placeholder="postgres" className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
                  </div>
                </div>
                
                {connectionError && (
                  <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
                    {connectionError}
                  </div>
                )}
                
                <button 
                  onClick={handleConnect} 
                  disabled={!canProceedStep2 || isConnecting} 
                  className="mt-6 w-full py-3 bg-orange-600 text-white rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-orange-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                >
                  {isConnecting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Connessione...
                    </>
                  ) : (
                    'Connetti'
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Select Tables */}
          {step === 3 && (
            <div>
              <button onClick={() => setStep(2)} className="flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-6 text-sm">
                ← Indietro
              </button>
              <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">Seleziona le tabelle</h3>
                    <p className="text-xs text-slate-500">Scegli quali tabelle vuoi utilizzare</p>
                  </div>
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 rounded-lg">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                    <span className="text-xs font-bold text-green-700">Connesso</span>
                  </div>
                </div>
                
                {isLoadingTables ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-8 h-8 border-3 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-sm text-slate-600">{selectedTables.length} di {tables.length} tabelle</span>
                      <div className="flex gap-2">
                        <button onClick={() => setSelectedTables(tables.map(t => t.name))} className="text-xs text-orange-600 hover:underline">Tutte</button>
                        <span className="text-slate-300">|</span>
                        <button onClick={() => setSelectedTables([])} className="text-xs text-slate-500 hover:underline">Nessuna</button>
                      </div>
                    </div>
                    <div className="border border-slate-200 rounded-xl overflow-hidden max-h-64 overflow-y-auto">
                      {tables.map((table, index) => (
                        <div 
                          key={table.name} 
                          onClick={() => handleTableToggle(table.name)} 
                          className={`flex items-center gap-4 p-4 cursor-pointer transition-all ${
                            index !== tables.length - 1 ? 'border-b border-slate-100' : ''
                          } ${selectedTables.includes(table.name) ? 'bg-orange-50' : 'hover:bg-slate-50'}`}
                        >
                          <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                            selectedTables.includes(table.name) ? 'bg-orange-600 border-orange-600 text-white' : 'border-slate-300'
                          }`}>
                            {selectedTables.includes(table.name) && '✓'}
                          </div>
                          <div className="flex-1">
                            <p className="font-semibold text-slate-900">{table.name}</p>
                            <p className="text-xs text-slate-500">{table.columns?.length || 0} colonne - {table.row_count?.toLocaleString() || 0} righe</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
                
                <button 
                  onClick={() => setStep(4)} 
                  disabled={selectedTables.length === 0} 
                  className="mt-6 w-full py-3 bg-orange-600 text-white rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-orange-700 disabled:opacity-50 transition-all"
                >
                  Continua
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Select LLM Provider */}
          {step === 4 && (
            <div>
              <button onClick={() => setStep(3)} className="flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-6 text-sm">
                ← Indietro
              </button>
              <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
                    <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">Seleziona Provider AI</h3>
                    <p className="text-xs text-slate-500">Scegli il modello per le analisi dati</p>
                  </div>
                </div>
                
                <div className="space-y-3 mb-6">
                  {LLM_PROVIDERS.map((provider) => (
                    <button 
                      key={provider.id} 
                      onClick={() => setSelectedLLM(provider.id)}
                      className={`w-full p-4 rounded-xl border-2 text-left transition-all ${
                        selectedLLM !== provider.id ? 'border-slate-200 bg-white hover:border-slate-300' : ''
                      }`}
                      style={getProviderStyle(provider.color, selectedLLM === provider.id)}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-bold text-slate-900">{provider.name}</p>
                          <p className="text-xs text-slate-500">{provider.description}</p>
                        </div>
                        {selectedLLM === provider.id && (
                          <div 
                            className="w-6 h-6 rounded-full flex items-center justify-center text-white text-sm"
                            style={{backgroundColor: provider.color === 'orange' ? '#f97316' : provider.color === 'blue' ? '#3b82f6' : '#9333ea'}}
                          >
                            ✓
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
                
                <button 
                  onClick={handleFinish} 
                  className="w-full py-3 bg-green-600 text-white rounded-xl text-sm font-bold uppercase tracking-widest hover:bg-green-700 transition-all flex items-center justify-center gap-2"
                >
                  ✓ Completa Setup
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
      
      <footer className="py-4 text-center text-xs text-slate-400">
        DataChat BI Platform v0.5.0
      </footer>
    </div>
  );
};

export default SetupWizard;
