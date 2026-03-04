import React, { useState, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import { LLMProvider } from '../../types';
import { databaseApi, ConnectionStatus, SchemaResponse } from '../../api/databaseApi';
import { Icons } from '../Layout/Icons';
import { Toast, useToast } from '../ui/toast';

const Settings: React.FC = () => {
  const { llmProvider, setLLMProvider, language, setLanguage } = useAppStore();
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const { toast, showToast, hideToast } = useToast();

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    setIsLoading(true);
    try {
      const status = await databaseApi.getStatus();
      setConnectionStatus(status);
      if (status.connected && status.active_database) {
        const schemaData = await databaseApi.getSchema();
        setSchema(schemaData);
      }
    } catch (error) {
      console.error('Error loading status:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await databaseApi.disconnect();
      localStorage.removeItem('datachat-setup-complete');
      localStorage.removeItem('datachat-connection-credentials');
      showToast('Disconnesso. Ricarica la pagina per riconfigurare.', 'success');
      setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
      showToast('Errore nella disconnessione', 'error');
    }
  };

  const handleReconnect = async () => {
    setIsReconnecting(true);
    try {
      const savedCreds = localStorage.getItem('datachat-connection-credentials');
      if (savedCreds) {
        const creds = JSON.parse(savedCreds);
        const status = await databaseApi.connectWithConnectionString(creds.connectionString, creds.displayName);
        if (status.connected) {
          showToast('Riconnesso con successo!', 'success');
          await loadStatus();
        }
      }
    } catch (error) {
      showToast('Errore nella riconnessione', 'error');
    } finally {
      setIsReconnecting(false);
    }
  };

  const handleLLMChange = (provider: LLMProvider) => {
    setLLMProvider(provider);
    localStorage.setItem('datachat-llm-provider', provider);
    showToast(`Provider AI cambiato: ${provider}`, 'success');
  };

  const savedConfig = localStorage.getItem('datachat-connection-config');
  const config = savedConfig ? JSON.parse(savedConfig) : null;

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-8 h-full overflow-y-auto">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />
      
      <h2 className="text-2xl font-black text-slate-900 tracking-tight mb-8">Impostazioni</h2>
      
      <div className="space-y-6">
        {/* Stato Connessione Database */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
                <Icons.Database />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Connessione Database</h3>
                <p className="text-xs text-slate-500">Stato della connessione attuale</p>
              </div>
            </div>
            {connectionStatus?.connected ? (
              <div className="flex items-center gap-2 px-4 py-2 bg-green-100 rounded-xl">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
                <span className="text-xs font-bold text-green-700">Connesso</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-4 py-2 bg-red-100 rounded-xl">
                <div className="w-3 h-3 bg-red-500 rounded-full" />
                <span className="text-xs font-bold text-red-700">Non connesso</span>
              </div>
            )}
          </div>

          {connectionStatus?.connected ? (
            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <span className="block text-[10px] font-bold text-green-600 uppercase">Sorgente</span>
                    <span className="font-bold text-green-900">{config?.source === 'supabase' ? 'Supabase' : 'PostgreSQL'}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-bold text-green-600 uppercase">Host</span>
                    <span className="font-bold text-green-900 text-sm truncate block">{connectionStatus.host}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-bold text-green-600 uppercase">Database</span>
                    <span className="font-bold text-green-900">{connectionStatus.active_database}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-bold text-green-600 uppercase">Username</span>
                    <span className="font-bold text-green-900 text-sm truncate block">{connectionStatus.username}</span>
                  </div>
                </div>
              </div>

              {/* Tabelle connesse */}
              {schema && schema.tables.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wide mb-3">Tabelle disponibili ({schema.tables.length})</h4>
                  <div className="grid grid-cols-3 gap-2">
                    {schema.tables.map(table => (
                      <div key={table.name} className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                        <p className="font-semibold text-slate-900 text-sm">{table.name}</p>
                        <p className="text-xs text-slate-500">{table.columns?.length || 0} colonne - {table.row_count?.toLocaleString() || 0} righe</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button onClick={handleDisconnect} className="w-full py-3 bg-red-600 text-white rounded-xl text-sm font-bold hover:bg-red-700 transition-all">
                Disconnetti e Riconfigura
              </button>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-slate-500 mb-4">La connessione al database non e attiva.</p>
              <button onClick={handleReconnect} disabled={isReconnecting} className="px-6 py-3 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all">
                {isReconnecting ? 'Riconnessione...' : 'Riconnetti'}
              </button>
            </div>
          )}
        </div>

        {/* Provider LLM */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Provider AI</h3>
              <p className="text-xs text-slate-500">Modello di intelligenza artificiale per le analisi</p>
            </div>
          </div>
          
          <div className="grid grid-cols-3 gap-3">
            <button onClick={() => handleLLMChange(LLMProvider.CLAUDE)}
              className={`px-4 py-3 rounded-xl text-sm font-bold transition-all ${llmProvider === LLMProvider.CLAUDE ? 'bg-orange-600 text-white shadow-lg' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              Claude Sonnet 4.6
            </button>
            <button onClick={() => handleLLMChange(LLMProvider.AZURE)}
              className={`px-4 py-3 rounded-xl text-sm font-bold transition-all ${llmProvider === LLMProvider.AZURE ? 'bg-blue-600 text-white shadow-lg' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              GPT-4.1
            </button>
            <button onClick={() => handleLLMChange(LLMProvider.GPT52)}
              className={`px-4 py-3 rounded-xl text-sm font-bold transition-all ${llmProvider === LLMProvider.GPT52 ? 'bg-purple-600 text-white shadow-lg' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              GPT-5.2
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-3">
            {llmProvider === LLMProvider.CLAUDE && 'Claude Sonnet 4.6 via OpenRouter - Ottimo per ragionamento complesso'}
            {llmProvider === LLMProvider.AZURE && 'Azure OpenAI GPT-4.1 - Bilanciato per analisi dati'}
            {llmProvider === LLMProvider.GPT52 && 'Azure OpenAI GPT-5.2 - Modello piu avanzato per analisi complesse'}
          </p>

          {/* Lingua - Styled Buttons */}
          <div className="mt-6 pt-6 border-t border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-slate-900">Lingua</h4>
                <p className="text-xs text-slate-500">Lingua per interrogare i dati</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => { setLanguage('it'); showToast('Lingua: Italiano', 'success'); }}
                  className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                    language === 'it' ? 'bg-orange-600 text-white shadow-lg' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Italiano
                </button>
                <button
                  onClick={() => { setLanguage('en'); showToast('Language: English', 'success'); }}
                  className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                    language === 'en' ? 'bg-orange-600 text-white shadow-lg' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  English
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Info Sistema */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="text-sm font-bold text-slate-900 mb-4 uppercase tracking-wide">Info Sistema</h3>
          <div className="space-y-2 text-sm text-slate-600">
            <p><span className="font-bold">Backend:</span> http://localhost:8000</p>
            <p><span className="font-bold">Versione:</span> 0.5.0</p>
            <p><span className="font-bold">Architettura:</span> Vanna RAG + Direct PostgreSQL + Multi-Provider LLM</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
