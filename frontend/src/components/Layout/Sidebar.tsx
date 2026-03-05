import React from 'react';
import { Icons, AppIcon } from './Icons';
import { useAppStore } from '../../store/appStore';
import { useAuth } from '../../contexts/AuthContext';
import type { UserRole } from '../../types/auth';

interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  roles?: UserRole[];  // if undefined, visible to all authenticated users
}

const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab, isSidebarCollapsed, setSidebarCollapsed } = useAppStore();
  const { user, logout } = useAuth();

  const allMenuItems: MenuItem[] = [
    { id: 'chat', label: 'Chat con i Dati', icon: <Icons.MessageSquare /> },
    { id: 'charts', label: 'Charts Gallery', icon: <Icons.BarChart /> },
    { id: 'dashboard', label: 'Dashboard', icon: <Icons.Layout /> },
    { id: 'database', label: 'Schema DB', icon: <Icons.Database /> },
    { id: 'settings', label: 'Impostazioni', icon: <Icons.Settings /> },
    { id: 'knowledge-base', label: 'Knowledge Base', icon: <Icons.BookOpen />, roles: ['admin', 'analyst'] },
    { id: 'instructions', label: 'Instructions', icon: <Icons.FileText />, roles: ['admin', 'analyst'] },
    { id: 'write-ops', label: 'Write Operations', icon: <Icons.PenTool />, roles: ['admin', 'analyst'] },
    { id: 'admin', label: 'Admin Panel', icon: <Icons.Shield />, roles: ['admin'] },
  ];

  const userRole = user?.role;
  const menuItems = allMenuItems.filter(item => {
    if (!item.roles) return true;
    if (!userRole) return false;
    return item.roles.includes(userRole);
  });

  const handleLogout = async () => {
    await logout();
  };

  return (
    <aside className={`bg-white border-r border-slate-200 h-screen flex flex-col shrink-0 transition-all duration-300 ease-in-out ${isSidebarCollapsed ? 'w-20' : 'w-64'}`}>
      <div className={`p-6 border-b border-slate-200 flex items-center ${isSidebarCollapsed ? 'justify-center' : 'gap-4'}`}>
        <AppIcon />
        {!isSidebarCollapsed && (
          <div>
            <h1 className="text-lg font-bold text-slate-900 tracking-tight leading-none">
              DataChat
            </h1>
            <p className="text-[10px] text-orange-600 mt-1 uppercase tracking-widest font-bold">
              AI Analytics
            </p>
          </div>
        )}
      </div>
      
      <nav className="flex-1 p-3 space-y-1.5 overflow-y-auto mt-4">
        {menuItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl transition-all ${activeTab === item.id ? 'bg-orange-600 text-white shadow-lg shadow-orange-100' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'} ${isSidebarCollapsed ? 'justify-center' : ''}`}
            title={isSidebarCollapsed ? item.label : undefined}
          >
            <span className="shrink-0">{item.icon}</span>
            {!isSidebarCollapsed && <span className="font-bold text-xs whitespace-nowrap uppercase tracking-wide">{item.label}</span>}
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-slate-50 space-y-2">
        {!isSidebarCollapsed && user && (
          <div className="px-3 py-2 mb-1">
            <p className="text-[10px] font-bold text-slate-900 uppercase truncate">{user.full_name}</p>
            <p className={`text-[9px] font-bold uppercase tracking-widest ${user.role === 'admin' ? 'text-orange-600' : user.role === 'analyst' ? 'text-blue-600' : 'text-slate-400'}`}>{user.role}</p>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={`w-full flex items-center gap-3 px-3 py-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition-all ${isSidebarCollapsed ? 'justify-center' : ''}`}
          title="Logout"
        >
          <Icons.LogOut />
          {!isSidebarCollapsed && <span className="text-[10px] font-bold uppercase tracking-widest">Logout</span>}
        </button>
        <button 
          onClick={() => setSidebarCollapsed(!isSidebarCollapsed)}
          className="w-full flex items-center gap-3 px-3 py-2 text-slate-400 hover:text-slate-900 transition-all"
        >
          <div className={`transition-transform duration-300 ${isSidebarCollapsed ? 'rotate-180' : ''}`}>
             <Icons.ChevronLeft />
          </div>
          {!isSidebarCollapsed && <span className="text-[10px] font-bold uppercase tracking-widest">Contrai</span>}
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;