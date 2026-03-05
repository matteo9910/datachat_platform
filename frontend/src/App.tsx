import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import ChatInterface from './components/Chat/ChatInterface';
import ChartsGallery from './components/Charts/ChartsGallery';
import DashboardManager from './components/Dashboard/DashboardManager';
import DatabaseSchema from './components/Database/DatabaseSchema';
import Settings from './components/Settings/Settings';
import OAuthCallback from './pages/OAuthCallback';
import SetupWizard from './pages/SetupWizard';
import KnowledgeBase from './pages/KnowledgeBase';
import Instructions from './pages/Instructions';
import WriteOperations from './pages/WriteOperations';
import AdminPanel from './pages/AdminPanel';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/Auth/ProtectedRoute';
import { useAppStore } from './store/appStore';
import { databaseApi } from './api/databaseApi';
import { LLMProvider } from './types';
import './styles/globals.css';

const MainApp: React.FC = () => {
  const { activeTab, setLLMProvider } = useAppStore();
  const { isAuthenticated } = useAuth();
  const [showSetup, setShowSetup] = useState<boolean | null>(null);
  const [isCheckingConnection, setIsCheckingConnection] = useState(true);

  useEffect(() => {
    if (isAuthenticated) {
      checkSetupStatus();
    }
  }, [isAuthenticated]);

  const checkSetupStatus = async () => {
    setIsCheckingConnection(true);
    
    // Load LLM provider from localStorage
    const savedLLM = localStorage.getItem('datachat-llm-provider');
    if (savedLLM) {
      setLLMProvider(savedLLM as LLMProvider);
    }
    
    try {
      const status = await databaseApi.getStatus();
      if (status.connected) {
        setShowSetup(false);
      } else {
        localStorage.removeItem('datachat-setup-complete');
        localStorage.removeItem('datachat-connection-credentials');
        localStorage.removeItem('datachat-connection-config');
        localStorage.removeItem('datachat-selected-tables');
        setShowSetup(true);
      }
    } catch {
      localStorage.removeItem('datachat-setup-complete');
      localStorage.removeItem('datachat-connection-credentials');
      localStorage.removeItem('datachat-connection-config');
      localStorage.removeItem('datachat-selected-tables');
      setShowSetup(true);
    }
    
    setIsCheckingConnection(false);
  };

  const handleSetupComplete = async () => {
    try {
      const status = await databaseApi.getStatus();
      if (!status.connected) {
        const savedCreds = localStorage.getItem('datachat-connection-credentials');
        if (savedCreds) {
          const creds = JSON.parse(savedCreds);
          await databaseApi.connectWithConnectionString(creds.connectionString, creds.displayName);
        }
      }
    } catch (error) {
      console.error('Error verifying connection after setup:', error);
    }
    setShowSetup(false);
  };

  // Show loading while checking connection
  if (isCheckingConnection || showSetup === null) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-500 text-sm">Caricamento...</p>
        </div>
      </div>
    );
  }

  // Show setup wizard if needed (after authentication)
  if (showSetup) {
    return <SetupWizard onComplete={handleSetupComplete} />;
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'chat': return <ChatInterface />;
      case 'charts': return <ChartsGallery />;
      case 'dashboard': return <DashboardManager />;
      case 'database': return <DatabaseSchema />;
      case 'settings': return <Settings />;
      case 'knowledge-base': return <KnowledgeBase />;
      case 'instructions': return <Instructions />;
      case 'write-ops': return <WriteOperations />;
      case 'admin': return <AdminPanel />;
      default: return <ChatInterface />;
    }
  };

  return (
    <div className="flex h-screen bg-white text-slate-900 overflow-hidden font-sans">
      <Sidebar />
      
      <main className="flex-1 relative flex flex-col h-full overflow-hidden">
        <Header />
        
        <div className="flex-1 overflow-hidden">
          {renderContent()}
        </div>
      </main>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;