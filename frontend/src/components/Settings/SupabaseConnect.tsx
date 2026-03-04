import React, { useState, useEffect } from "react";
import { databaseApi, ConnectionStatus, SupabaseProject } from "../../api/databaseApi";

interface Props {
  onConnected: (status: ConnectionStatus) => void;
  showToast: (message: string, type: "success" | "error" | "info") => void;
}

const SupabaseConnect: React.FC<Props> = ({ onConnected, showToast }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [projects, setProjects] = useState<SupabaseProject[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedProjectName, setSelectedProjectName] = useState("");
  const [connectionString, setConnectionString] = useState("");
  const [showConnectionStep, setShowConnectionStep] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      if (event.data?.type === "oauth_success") {
        setIsLoading(false);
        setIsAuthenticated(true);
        showToast("Autenticazione completata!", "success");
        try {
          const { projects } = await databaseApi.oauthListProjects();
          setProjects(projects);
        } catch (err) {
          showToast("Errore nel caricamento progetti", "error");
        }
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [showToast]);

  const handleOAuthConnect = async () => {
    setIsLoading(true);
    try {
      const { auth_url } = await databaseApi.oauthInit();
      const width = 600, height = 700;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;
      const popup = window.open(auth_url, "Supabase OAuth", `width=${width},height=${height},left=${left},top=${top},popup=yes`);
      if (!popup) {
        showToast("Popup bloccato. Abilita i popup.", "error");
        setIsLoading(false);
        return;
      }
      const checkPopup = setInterval(() => {
        if (popup.closed) { clearInterval(checkPopup); setIsLoading(false); }
      }, 500);
    } catch (error: any) {
      showToast(error.response?.data?.detail || "Errore OAuth", "error");
      setIsLoading(false);
    }
  };

  const handleProjectSelect = () => {
    if (!selectedProject) { showToast("Seleziona un progetto", "error"); return; }
    const project = projects.find(p => p.ref === selectedProject);
    setSelectedProjectName(project?.name || selectedProject);
    setShowConnectionStep(true);
  };

  const handleConnect = async () => {
    if (!connectionString) {
      showToast("Inserisci la connection string", "error");
      return;
    }
    if (!connectionString.startsWith("postgresql://")) {
      showToast("La connection string deve iniziare con postgresql://", "error");
      return;
    }
    setIsConnecting(true);
    try {
      const status = await databaseApi.connectWithConnectionString(connectionString, selectedProject);
      onConnected(status);
      showToast(`Connesso a ${selectedProjectName}!`, "success");
    } catch (error: any) {
      showToast(error.response?.data?.detail || "Errore connessione", "error");
    } finally {
      setIsConnecting(false);
    }
  };

  const handleBack = () => {
    setShowConnectionStep(false);
    setConnectionString("");
  };

  return (
    <div className="space-y-4 p-4 bg-emerald-50 rounded-xl border border-emerald-100">
      <div className="flex items-center gap-3 mb-4">
        <img src="/logos/supabase.png" alt="Supabase" className="w-8 h-8" />
        <div>
          <p className="text-sm font-bold text-emerald-800">Connetti a Supabase</p>
          <p className="text-xs text-emerald-600">Database PostgreSQL cloud</p>
        </div>
      </div>

      {!isAuthenticated && (
        <div className="text-center py-4">
          <p className="text-sm text-slate-600 mb-4">Clicca per accedere al tuo account Supabase e autorizzare l'accesso.</p>
          <button onClick={handleOAuthConnect} disabled={isLoading} className="px-6 py-3 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 transition-all disabled:opacity-50 flex items-center gap-2 mx-auto">
            {isLoading ? (<><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>Autenticazione...</>) : (<><svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M21.805 10.023h-9.18v3.954h5.246c-.477 2.527-2.682 3.954-5.246 3.954a5.93 5.93 0 01-5.932-5.931 5.93 5.93 0 015.932-5.932c1.477 0 2.818.545 3.863 1.432l2.954-2.954A9.848 9.848 0 0012.625 2C6.885 2 2.25 6.635 2.25 12.375S6.885 22.75 12.625 22.75c5.738 0 9.568-4.023 9.568-9.682 0-.682-.068-1.364-.205-2.045h-.183z"/></svg>Accedi con Supabase</>)}
          </button>
        </div>
      )}

      {isAuthenticated && projects.length > 0 && !showConnectionStep && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-emerald-600 text-sm mb-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            <span className="font-semibold">Autenticato! Seleziona un progetto:</span>
          </div>
          <select value={selectedProject} onChange={(e) => setSelectedProject(e.target.value)} className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500">
            <option value="">-- Seleziona progetto --</option>
            {projects.map((p) => (<option key={p.id} value={p.ref}>{p.name} ({p.region})</option>))}
          </select>
          <button onClick={handleProjectSelect} disabled={!selectedProject} className="w-full py-3 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>Continua
          </button>
        </div>
      )}

      {isAuthenticated && showConnectionStep && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-emerald-600 text-sm mb-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
            <span className="font-semibold">Connetti a: {selectedProjectName}</span>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
            <p className="font-semibold mb-1">Dove trovo la Connection String?</p>
            <p className="mb-2">Supabase Dashboard ? Project Settings ? Database ? Connection string</p>
            <p>Seleziona <strong>"URI"</strong> e copia la stringa completa (Session pooler consigliato)</p>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 block">Connection String *</label>
            <textarea 
              value={connectionString} 
              onChange={(e) => setConnectionString(e.target.value)} 
              placeholder="postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx.pooler.supabase.com:6543/postgres"
              className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono text-xs h-20 resize-none"
            />
            <p className="text-[10px] text-slate-400 mt-1">Sostituisci [YOUR-PASSWORD] con la tua password database</p>
          </div>
          <div className="flex gap-2">
            <button onClick={handleBack} className="px-4 py-3 bg-slate-100 text-slate-600 rounded-xl font-semibold hover:bg-slate-200 transition-all">Indietro</button>
            <button onClick={handleConnect} disabled={!connectionString || isConnecting} className="flex-1 py-3 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2">
              {isConnecting ? (<><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>Connessione...</>) : (<><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>Connetti</>)}
            </button>
          </div>
        </div>
      )}

      {isAuthenticated && projects.length === 0 && (
        <div className="text-center py-4 text-slate-500"><p>Nessun progetto trovato nel tuo account Supabase.</p></div>
      )}
    </div>
  );
};

export default SupabaseConnect;
