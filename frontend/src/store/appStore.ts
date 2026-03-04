import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { ChatMessage, ChatSession, SavedChart, LLMProvider, DBTable, UserDashboard } from '../types';

export type Language = 'it' | 'en';

interface AppState {
  // Chat
  sessions: ChatSession[];
  currentSessionId: string;
  isLoading: boolean;
  
  // Charts & Dashboards
  savedCharts: SavedChart[];
  dashboards: UserDashboard[];
  
  // Schema
  dbSchema: DBTable[];
  llmProvider: LLMProvider;
  language: Language;

  // UI State
  isSidebarCollapsed: boolean;
  activeTab: string;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateMessage: (messageId: string, updates: ChatMessage) => void;
  newChat: () => void;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;
  saveChart: (chart: SavedChart) => void;
  deleteChart: (id: string) => void;
  setSavedCharts: (charts: SavedChart[]) => void;
  updateChart: (id: string, updates: Partial<SavedChart>) => void;
  saveDashboard: (dashboard: UserDashboard) => void;
  deleteDashboard: (id: string) => void;
  setLLMProvider: (provider: LLMProvider) => void;
  setLanguage: (language: Language) => void;
  setDbSchema: (schema: DBTable[]) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setActiveTab: (tab: string) => void;
  setLoading: (loading: boolean) => void;
}

const INITIAL_SESSION_ID = 'session-1';

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
  sessions: [
    {
      id: INITIAL_SESSION_ID,
      title: 'Nuova Conversazione',
      updatedAt: new Date(),
      messages: []
    }
  ],
  currentSessionId: INITIAL_SESSION_ID,
  isLoading: false,
  savedCharts: [],
  dashboards: [],
  llmProvider: LLMProvider.CLAUDE,
  language: 'it' as Language,
  dbSchema: [
    {
      name: 'orders',
      rowCount: 9994,
      columns: [
        { name: 'order_id', type: 'VARCHAR(50)', nullable: false, isPK: true },
        { name: 'order_date', type: 'DATE', nullable: false },
        { name: 'region', type: 'VARCHAR(50)', nullable: false },
        { name: 'sales', type: 'DECIMAL(10,2)', nullable: false },
        { name: 'customer_id', type: 'VARCHAR(50)', nullable: false, isFK: true }
      ]
    },
    {
      name: 'customers',
      rowCount: 793,
      columns: [
        { name: 'customer_id', type: 'VARCHAR(50)', nullable: false, isPK: true },
        { name: 'customer_name', type: 'VARCHAR(100)', nullable: false },
        { name: 'segment', type: 'VARCHAR(50)', nullable: false }
      ]
    },
    {
      name: 'products',
      rowCount: 1894,
      columns: [
        { name: 'product_id', type: 'VARCHAR(50)', nullable: false, isPK: true },
        { name: 'product_name', type: 'VARCHAR(255)', nullable: false },
        { name: 'category', type: 'VARCHAR(100)', nullable: false }
      ]
    }
  ],
  isSidebarCollapsed: false,
  activeTab: 'chat',

  addMessage: (message) => set((state) => {
    const sessions = state.sessions.map(s => 
      s.id === state.currentSessionId 
        ? { ...s, messages: [...s.messages, message], updatedAt: new Date() }
        : s
    );
    return { sessions };
  }),

  updateMessage: (messageId, updates) => set((state) => {
    const sessions = state.sessions.map(s => 
      s.id === state.currentSessionId 
        ? { 
            ...s, 
            messages: s.messages.map(m => m.id === messageId ? { ...m, ...updates } : m),
            updatedAt: new Date() 
          }
        : s
    );
    return { sessions };
  }),

  newChat: () => set((state) => {
    const newId = `session-${Date.now()}`;
    return {
      sessions: [{ id: newId, title: 'Nuova Conversazione', messages: [], updatedAt: new Date() }, ...state.sessions],
      currentSessionId: newId
    };
  }),

  switchSession: (id) => set({ currentSessionId: id }),

  deleteSession: (id) => set((state) => {
    const filtered = state.sessions.filter(s => s.id !== id);
    // Se eliminiamo la sessione corrente, passa alla prima disponibile o crea nuova
    if (state.currentSessionId === id) {
      if (filtered.length === 0) {
        const newId = `session-${Date.now()}`;
        return {
          sessions: [{ id: newId, title: 'Nuova Conversazione', messages: [], updatedAt: new Date() }],
          currentSessionId: newId
        };
      }
      return { sessions: filtered, currentSessionId: filtered[0].id };
    }
    return { sessions: filtered };
  }),
  
  updateSessionTitle: (id, title) => set((state) => ({
    sessions: state.sessions.map(s => s.id === id ? { ...s, title } : s)
  })),
  
  saveChart: (chart) => set((state) => ({ savedCharts: [chart, ...state.savedCharts] })),
  deleteChart: (id) => set((state) => ({ savedCharts: state.savedCharts.filter(c => c.id !== id) })),
  setSavedCharts: (charts) => set({ savedCharts: charts }),
  updateChart: (id, updates) => set((state) => ({
    savedCharts: state.savedCharts.map(c => c.id === id ? { ...c, ...updates } : c)
  })),
  saveDashboard: (dashboard) => set((state) => {
    const exists = state.dashboards.find(d => d.id === dashboard.id);
    if (exists) {
      return { dashboards: state.dashboards.map(d => d.id === dashboard.id ? dashboard : d) };
    }
    return { dashboards: [dashboard, ...state.dashboards] };
  }),
  deleteDashboard: (id) => set((state) => ({ dashboards: state.dashboards.filter(d => d.id !== id) })),
  setLLMProvider: (provider) => set({ llmProvider: provider }),
  setLanguage: (language) => set({ language }),
  setDbSchema: (schema) => set({ dbSchema: schema }),
  setSidebarCollapsed: (collapsed) => set({ isSidebarCollapsed: collapsed }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setLoading: (loading) => set({ isLoading: loading })
    }),
    {
      name: 'datachat-storage',
      partialize: (state) => ({
        sessions: state.sessions,
        currentSessionId: state.currentSessionId,
        savedCharts: state.savedCharts,
        dashboards: state.dashboards,
        llmProvider: state.llmProvider,
        language: state.language,
      }),
    }
  )
);