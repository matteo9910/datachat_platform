import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import WriteOperationsPage from '../components/WriteOperations/WriteOperationsPage';
import WhitelistConfig from '../components/WriteOperations/WhitelistConfig';
import AuditLogPage from '../components/WriteOperations/AuditLogPage';

type Tab = 'write' | 'whitelist' | 'audit';

const WriteOperations: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [activeTab, setActiveTab] = useState<Tab>('write');

  const tabs: { id: Tab; label: string; adminOnly: boolean }[] = [
    { id: 'write', label: 'Write Operations', adminOnly: false },
    { id: 'whitelist', label: 'Whitelist Config', adminOnly: true },
    { id: 'audit', label: 'Audit Log', adminOnly: true },
  ];

  const visibleTabs = tabs.filter(t => !t.adminOnly || isAdmin);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="border-b border-slate-200 bg-white px-8 pt-4">
        <div className="flex gap-1">
          {visibleTabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wide rounded-t-xl transition-all ${
                activeTab === tab.id
                  ? 'bg-orange-600 text-white'
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'write' && <WriteOperationsPage />}
        {activeTab === 'whitelist' && isAdmin && <WhitelistConfig />}
        {activeTab === 'audit' && isAdmin && <AuditLogPage />}
      </div>
    </div>
  );
};

export default WriteOperations;
