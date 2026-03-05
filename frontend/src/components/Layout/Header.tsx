import React from 'react';
import { useAppStore } from '../../store/appStore';
import { useAuth } from '../../contexts/AuthContext';

const Header: React.FC = () => {
  const { activeTab, llmProvider } = useAppStore();
  const { user, logout } = useAuth();

  const tabLabels: Record<string, string> = {
    chat: 'Chat',
    charts: 'Charts',
    dashboard: 'Dashboard',
    database: 'Database',
    settings: 'Settings',
    'knowledge-base': 'Knowledge Base',
    instructions: 'Instructions',
    'write-ops': 'Write Operations',
    admin: 'Admin Panel',
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
            <span className="text-[9px] font-black text-green-700 uppercase tracking-widest">DB LIVE</span>
         </div>
         <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 rounded-full border border-slate-200">
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">LLM: {llmProvider}</span>
         </div>
         {user && (
           <div className="flex items-center gap-2 group">
             <div className="text-right">
                <p className="text-[10px] font-black text-slate-900 uppercase">{user.full_name}</p>
                <p className={`text-[9px] font-bold uppercase tracking-widest ${user.role === 'admin' ? 'text-orange-600' : user.role === 'analyst' ? 'text-blue-600' : 'text-slate-400'}`}>{user.role}</p>
             </div>
             <div className="w-8 h-8 rounded-full bg-orange-600 flex items-center justify-center text-white font-black text-xs shadow-lg">
               {user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
             </div>
             <button onClick={logout} className="ml-2 text-slate-400 hover:text-red-500 transition-colors" title="Logout">
               <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
             </button>
           </div>
         )}
      </div>
    </header>
  );
};

export default Header;