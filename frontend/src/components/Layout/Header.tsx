import React from 'react';
import { useAppStore } from '../../store/appStore';

const Header: React.FC = () => {
  const { activeTab, llmProvider } = useAppStore();

  const tabLabels: Record<string, string> = {
    chat: 'Chat',
    charts: 'Charts',
    dashboard: 'Dashboard',
    database: 'Database',
    settings: 'Settings'
  };

  return (
    <header className="h-16 bg-white border-b border-slate-100 px-8 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-4">
        <h2 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
          DataChat BI Platform / {tabLabels[activeTab] || activeTab}
        </h2>
      </div>
      
      <div className="flex items-center gap-6">
         <div className="flex items-center gap-2 px-3 py-1 bg-green-50 rounded-full border border-green-100">
            <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-[9px] font-black text-green-700 uppercase tracking-widest">DB LIVE: superstore_v2</span>
         </div>
         <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 rounded-full border border-slate-200">
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">LLM: {llmProvider}</span>
         </div>
         <div className="flex items-center gap-2 group cursor-pointer">
           <div className="text-right">
              <p className="text-[10px] font-black text-slate-900 uppercase">AI Engineer</p>
              <p className="text-[9px] text-slate-400 font-bold uppercase tracking-widest">Session ID: POC-{Math.floor(Math.random() * 999)}</p>
           </div>
           <div className="w-8 h-8 rounded-full bg-orange-600 flex items-center justify-center text-white font-black text-xs shadow-lg group-hover:scale-110 transition-transform">
             AI
           </div>
         </div>
      </div>
    </header>
  );
};

export default Header;