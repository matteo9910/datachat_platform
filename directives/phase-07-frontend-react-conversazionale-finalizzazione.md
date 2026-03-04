# Fase 07: Frontend React Conversazionale e Finalizzazione

## Panoramica
- **Obiettivo**: Sviluppare SPA React completa con UI conversazionale, rendering chart Plotly, gestione chart salvati, integrazione Power BI
- **Dipendenza**: Fasi 01-06 (Backend completo funzionante)
- **Complessità stimata**: Alta
- **Componenti coinvolti**: Frontend

## Contesto
Le Fasi 01-06 hanno completato l'intero backend del sistema DataChat BI Platform:
- Text-to-SQL con Vanna + RAG
- Multi-provider LLM (Claude/Azure)
- Chart generation Plotly parametrici
- Persistenza e modifica chart
- Automazione Power BI text-to-DAX

Ora costruiamo il **frontend React 18 + TypeScript** che unifica tutte queste funzionalità in un'interfaccia conversazionale user-friendly.

Design principles:
- **Conversational-first**: Chat interface centrale (ispirata ChatGPT)
- **Minimale e clean**: shadcn/ui components, Tailwind utility-first
- **Interattiva**: Chart Plotly.js con hover/zoom/pan, parametri modificabili real-time
- **Responsive**: Desktop-first (1920x1080, 1366x768), tablet usabile, mobile acceptable degradation
- **Type-safe**: TypeScript strict mode, Pydantic-like validation client

Stack:
- **React 18.3** + **TypeScript 5.x**
- **Vite 5.x** (build tool, HMR)
- **shadcn/ui** (Radix UI primitives + Tailwind)
- **Tailwind CSS 3.x** (styling)
- **Plotly.js 2.x** (chart rendering)
- **Zustand 4.x** (state management)
- **Axios 1.x** (API client)

## Obiettivi Specifici
1. Setup progetto React + Vite + TypeScript + Tailwind + shadcn/ui
2. Creare API client Axios con base URL configurabile
3. Implementare Zustand stores (chat, charts, config)
4. Creare componenti UI core (ChatInterface, ChatMessage, ChatInput)
5. Creare componente ChartViewer (render Plotly.js)
6. Creare componente SavedChartsList (galleria chart salvati)
7. Creare componente ParameterControls (UI modifica parametri)
8. Creare componente PowerBIChat (integrazione Power BI)
9. Implementare routing SPA (React Router: /, /saved-charts, /powerbi)
10. Integrare backend API (chat/query, charts/*, powerbi/*)
11. Testare workflow completo end-to-end
12. Deploy localhost:3000 (Vite dev server)

## Specifiche Tecniche Dettagliate

### Area 1: Setup Progetto React

**Inizializzazione Vite + React + TypeScript:**

```bash
# Dalla root del progetto
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator

# Creare progetto Vite
npm create vite@latest frontend -- --template react-ts

# Navigare in frontend
cd frontend

# Installare dipendenze
npm install

# Installare dipendenze aggiuntive
npm install axios zustand plotly.js-dist-min react-plotly.js
npm install react-router-dom
npm install clsx tailwind-merge class-variance-authority
npm install lucide-react  # Icons

# Installare Tailwind CSS
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Dev dependencies
npm install -D @types/plotly.js @types/react-plotly.js
```

**File da creare/modificare:**

**`frontend/tailwind.config.js`:**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
```

**`frontend/src/styles/globals.css`:**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 221.2 83.2% 53.3%;
    --radius: 0.5rem;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
}
```

**`frontend/.env`:**

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_NAME=DataChat BI Platform
```

---

### Area 2: API Client e Types

**File da creare:** `frontend/src/api/client.ts`

```typescript
/**
 * Axios API client configurato
 */

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30s
});

// Request interceptor (logging, auth future)
apiClient.interceptors.request.use(
  (config) => {
    console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor (error handling)
apiClient.interceptors.response.use(
  (response) => {
    console.log(`[API Response] ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('[API Error]', error.response?.data || error.message);
    return Promise.reject(error);
  }
);
```

**File da creare:** `frontend/src/types/chat.ts`

```typescript
/**
 * TypeScript types per Chat API
 */

export interface ChatQueryRequest {
  query: string;
  session_id?: string;
  llm_provider: 'claude' | 'azure';
  include_chart?: boolean;
}

export interface PlotlyConfig {
  data: any[];
  layout: Record<string, any>;
}

export interface Parameter {
  name: string;
  type: 'enum' | 'number' | 'date' | 'text';
  current_value: any;
  options?: any[];
  min_value?: any;
  max_value?: any;
  label: string;
}

export interface ChartData {
  chart_type: string;
  plotly_config: PlotlyConfig;
  parameters: Record<string, Parameter>;
  sql_template: string;
}

export interface ChatQueryResponse {
  success: boolean;
  session_id: string;
  nl_response: string;
  sql: string;
  results: Record<string, any>[];
  chart?: ChartData | null;
  execution_time_ms: number;
  error?: string | null;
}

export interface ChatMessage {
  id: string;
  query: string;
  response: ChatQueryResponse;
  timestamp: Date;
}
```

**File da creare:** `frontend/src/types/charts.ts`

```typescript
/**
 * TypeScript types per Charts API
 */

import { PlotlyConfig, Parameter } from './chat';

export interface SaveChartRequest {
  title: string;
  description?: string;
  sql_template: string;
  parameters: Record<string, Parameter>;
  plotly_config: PlotlyConfig;
}

export interface SavedChart {
  chart_id: string;
  title: string;
  description?: string;
  sql_template: string;
  parameters: Record<string, Parameter>;
  plotly_config: PlotlyConfig;
  created_at: string;
  updated_at?: string;
}

export interface UpdateParametersRequest {
  parameters: Record<string, any>;
  llm_provider?: 'claude' | 'azure';
}
```

**File da creare:** `frontend/src/api/chatApi.ts`

```typescript
/**
 * Chat API calls
 */

import { apiClient } from './client';
import { ChatQueryRequest, ChatQueryResponse } from '../types/chat';

export const chatApi = {
  async query(request: ChatQueryRequest): Promise<ChatQueryResponse> {
    const response = await apiClient.post<ChatQueryResponse>('/api/chat/query', request);
    return response.data;
  },

  async getHistory(sessionId: string): Promise<any> {
    const response = await apiClient.get(`/api/chat/history`, {
      params: { session_id: sessionId },
    });
    return response.data;
  },
};
```

**File da creare:** `frontend/src/api/chartsApi.ts`

```typescript
/**
 * Charts API calls
 */

import { apiClient } from './client';
import { SaveChartRequest, SavedChart, UpdateParametersRequest } from '../types/charts';

export const chartsApi = {
  async save(request: SaveChartRequest): Promise<{ chart_id: string; created_at: string }> {
    const response = await apiClient.post('/api/charts/save', request);
    return response.data;
  },

  async list(): Promise<SavedChart[]> {
    const response = await apiClient.get('/api/charts');
    return response.data.charts;
  },

  async get(chartId: string): Promise<SavedChart> {
    const response = await apiClient.get(`/api/charts/${chartId}`);
    return response.data;
  },

  async updateParameters(
    chartId: string,
    request: UpdateParametersRequest
  ): Promise<{ plotly_config: any; results: any[] }> {
    const response = await apiClient.put(`/api/charts/${chartId}/parameters`, request);
    return response.data;
  },

  async delete(chartId: string): Promise<void> {
    await apiClient.delete(`/api/charts/${chartId}`);
  },
};
```

---

### Area 3: Zustand State Management

**File da creare:** `frontend/src/store/chatStore.ts`

```typescript
/**
 * Zustand store - Chat state
 */

import { create } from 'zustand';
import { ChatMessage } from '../types/chat';

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  currentProvider: 'claude' | 'azure';

  addMessage: (message: ChatMessage) => void;
  setSessionId: (sessionId: string) => void;
  setLoading: (loading: boolean) => void;
  setProvider: (provider: 'claude' | 'azure') => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: null,
  isLoading: false,
  currentProvider: 'claude',

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  setSessionId: (sessionId) => set({ sessionId }),

  setLoading: (loading) => set({ isLoading: loading }),

  setProvider: (provider) => set({ currentProvider: provider }),

  clearMessages: () => set({ messages: [], sessionId: null }),
}));
```

**File da creare:** `frontend/src/store/chartsStore.ts`

```typescript
/**
 * Zustand store - Saved charts state
 */

import { create } from 'zustand';
import { SavedChart } from '../types/charts';

interface ChartsStore {
  savedCharts: SavedChart[];
  selectedChart: SavedChart | null;
  isLoading: boolean;

  setSavedCharts: (charts: SavedChart[]) => void;
  setSelectedChart: (chart: SavedChart | null) => void;
  addSavedChart: (chart: SavedChart) => void;
  removeSavedChart: (chartId: string) => void;
  setLoading: (loading: boolean) => void;
}

export const useChartsStore = create<ChartsStore>((set) => ({
  savedCharts: [],
  selectedChart: null,
  isLoading: false,

  setSavedCharts: (charts) => set({ savedCharts: charts }),

  setSelectedChart: (chart) => set({ selectedChart: chart }),

  addSavedChart: (chart) =>
    set((state) => ({
      savedCharts: [chart, ...state.savedCharts],
    })),

  removeSavedChart: (chartId) =>
    set((state) => ({
      savedCharts: state.savedCharts.filter((c) => c.chart_id !== chartId),
    })),

  setLoading: (loading) => set({ isLoading: loading }),
}));
```

---

### Area 4: Componenti UI Core

**Installare shadcn/ui components:**

```bash
# Dalla directory frontend/
npx shadcn-ui@latest init

# Quando richiesto:
# - TypeScript: Yes
# - Style: Default
# - Base color: Slate
# - CSS variables: Yes

# Installare componenti necessari
npx shadcn-ui@latest add button
npx shadcn-ui@latest add card
npx shadcn-ui@latest add input
npx shadcn-ui@latest add select
npx shadcn-ui@latest add dropdown-menu
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add alert
npx shadcn-ui@latest add badge
npx shadcn-ui@latest add separator
npx shadcn-ui@latest add skeleton
```

**File da creare:** `frontend/src/components/Chat/ChatInterface.tsx`

```typescript
/**
 * Main chat interface component
 */

import React, { useState } from 'react';
import { useChatStore } from '../../store/chatStore';
import { chatApi } from '../../api/chatApi';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { Card } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Loader2 } from 'lucide-react';

export const ChatInterface: React.FC = () => {
  const { messages, sessionId, isLoading, currentProvider, addMessage, setSessionId, setLoading } =
    useChatStore();

  const [error, setError] = useState<string | null>(null);

  const handleSendMessage = async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await chatApi.query({
        query,
        session_id: sessionId || undefined,
        llm_provider: currentProvider,
        include_chart: true,
      });

      // Update session ID
      if (response.session_id && !sessionId) {
        setSessionId(response.session_id);
      }

      // Add message to store
      const newMessage: import('../../types/chat').ChatMessage = {
        id: crypto.randomUUID(),
        query,
        response,
        timestamp: new Date(),
      };

      addMessage(newMessage);
    } catch (err: any) {
      console.error('Chat query error:', err);
      setError(err.response?.data?.detail || err.message || 'Errore durante la query');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-6xl mx-auto p-4">
      <h1 className="text-3xl font-bold mb-4">DataChat BI Platform</h1>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <Card className="p-8 text-center text-muted-foreground">
            <p className="text-lg mb-2">👋 Benvenuto in DataChat BI Platform</p>
            <p>Fai una domanda sui tuoi dati in linguaggio naturale</p>
          </Card>
        )}

        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {isLoading && (
          <div className="flex items-center justify-center p-4">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            <span>Elaborazione in corso...</span>
          </div>
        )}

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>

      {/* Input */}
      <ChatInput onSend={handleSendMessage} disabled={isLoading} />
    </div>
  );
};
```

**File da creare:** `frontend/src/components/Chat/ChatInput.tsx`

```typescript
/**
 * Chat input component
 */

import React, { useState } from 'react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Send } from 'lucide-react';

interface ChatInputProps {
  onSend: (query: string) => void;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (query.trim() && !disabled) {
      onSend(query.trim());
      setQuery('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <Input
        type="text"
        placeholder="Fai una domanda... (es: Vendite totali per regione)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={disabled}
        className="flex-1"
      />
      <Button type="submit" disabled={disabled || !query.trim()}>
        <Send className="h-4 w-4" />
      </Button>
    </form>
  );
};
```

**File da creare:** `frontend/src/components/Chat/ChatMessage.tsx`

```typescript
/**
 * Single chat message component
 */

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { ChatMessage as ChatMessageType } from '../../types/chat';
import { ChartViewer } from '../Charts/ChartViewer';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';

interface ChatMessageProps {
  message: ChatMessageType;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const { query, response } = message;

  return (
    <div className="space-y-2">
      {/* User query */}
      <div className="flex justify-end">
        <Card className="max-w-[80%] bg-primary text-primary-foreground">
          <CardContent className="p-3">
            <p>{query}</p>
          </CardContent>
        </Card>
      </div>

      {/* AI response */}
      <div className="flex justify-start">
        <Card className="max-w-[90%]">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              🤖 DataChat AI
              <Badge variant="outline">{response.execution_time_ms.toFixed(0)}ms</Badge>
            </CardTitle>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* NL response */}
            <p className="text-sm">{response.nl_response}</p>

            <Separator />

            {/* SQL query (collapsible) */}
            <details>
              <summary className="cursor-pointer text-sm font-medium">SQL Query</summary>
              <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-x-auto">
                {response.sql}
              </pre>
            </details>

            {/* Chart */}
            {response.chart && (
              <>
                <Separator />
                <ChartViewer
                  chartData={response.chart}
                  results={response.results}
                  query={query}
                />
              </>
            )}

            {/* Results table (collapsible, limit 10 rows) */}
            {response.results.length > 0 && (
              <>
                <Separator />
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    Risultati ({response.results.length} righe)
                  </summary>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-xs border">
                      <thead className="bg-muted">
                        <tr>
                          {Object.keys(response.results[0]).map((key) => (
                            <th key={key} className="p-2 text-left border">
                              {key}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {response.results.slice(0, 10).map((row, idx) => (
                          <tr key={idx} className="border">
                            {Object.values(row).map((val, i) => (
                              <td key={i} className="p-2 border">
                                {String(val)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {response.results.length > 10 && (
                      <p className="text-xs text-muted-foreground mt-2">
                        ...e altre {response.results.length - 10} righe
                      </p>
                    )}
                  </div>
                </details>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
```

**File da creare:** `frontend/src/components/Charts/ChartViewer.tsx`

```typescript
/**
 * Plotly.js chart viewer component
 */

import React from 'react';
import Plot from 'react-plotly.js';
import { ChartData } from '../../types/chat';
import { Button } from '../ui/button';
import { Save } from 'lucide-react';
import { chartsApi } from '../../api/chartsApi';
import { useChartsStore } from '../../store/chartsStore';

interface ChartViewerProps {
  chartData: ChartData;
  results: Record<string, any>[];
  query: string;
}

export const ChartViewer: React.FC<ChartViewerProps> = ({ chartData, results, query }) => {
  const { addSavedChart } = useChartsStore();

  const handleSaveChart = async () => {
    try {
      const title = query.slice(0, 100); // Usa query come titolo default

      const savedChart = await chartsApi.save({
        title,
        description: `Generated on ${new Date().toLocaleString()}`,
        sql_template: chartData.sql_template,
        parameters: chartData.parameters,
        plotly_config: chartData.plotly_config,
      });

      alert(`Chart salvato con successo! ID: ${savedChart.chart_id}`);

      // Add to store (opzionale, per aggiornare lista saved charts)
      // addSavedChart(...);
    } catch (error) {
      console.error('Save chart error:', error);
      alert('Errore durante il salvataggio del chart');
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-medium">Chart: {chartData.chart_type}</h3>
        <Button size="sm" variant="outline" onClick={handleSaveChart}>
          <Save className="h-4 w-4 mr-2" />
          Salva Chart
        </Button>
      </div>

      <div className="border rounded p-2">
        <Plot
          data={chartData.plotly_config.data}
          layout={{
            ...chartData.plotly_config.layout,
            autosize: true,
            margin: { l: 40, r: 40, t: 40, b: 40 },
          }}
          config={{
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
          }}
          style={{ width: '100%', height: '400px' }}
        />
      </div>

      {/* Parameters (se presenti) */}
      {Object.keys(chartData.parameters).length > 0 && (
        <div className="text-xs text-muted-foreground">
          <p>Parametri modificabili: {Object.keys(chartData.parameters).join(', ')}</p>
        </div>
      )}
    </div>
  );
};
```

---

### Area 5: App Root e Routing

**File da creare:** `frontend/src/App.tsx`

```typescript
/**
 * App root component
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { ChatInterface } from './components/Chat/ChatInterface';
import { Button } from './components/ui/button';
import './styles/globals.css';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        {/* Simple nav */}
        <nav className="border-b p-4">
          <div className="max-w-6xl mx-auto flex gap-4">
            <Link to="/">
              <Button variant="ghost">Chat</Button>
            </Link>
            <Link to="/saved-charts">
              <Button variant="ghost">Chart Salvati</Button>
            </Link>
            <Link to="/powerbi">
              <Button variant="ghost">Power BI</Button>
            </Link>
          </div>
        </nav>

        {/* Routes */}
        <Routes>
          <Route path="/" element={<ChatInterface />} />
          <Route
            path="/saved-charts"
            element={
              <div className="p-4">
                <h1 className="text-2xl font-bold">Chart Salvati</h1>
                <p className="text-muted-foreground">TODO: Implementare lista chart salvati</p>
              </div>
            }
          />
          <Route
            path="/powerbi"
            element={
              <div className="p-4">
                <h1 className="text-2xl font-bold">Power BI Integration</h1>
                <p className="text-muted-foreground">TODO: Implementare Power BI chat</p>
              </div>
            }
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
```

**File da modificare:** `frontend/src/main.tsx`

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `frontend/package.json` | Creare | Dipendenze npm (generato da Vite) |
| `frontend/tailwind.config.js` | Creare | Configurazione Tailwind CSS |
| `frontend/src/styles/globals.css` | Creare | CSS global (Tailwind imports + variables) |
| `frontend/.env` | Creare | Variabili ambiente frontend (API base URL) |
| `frontend/src/api/client.ts` | Creare | Axios client configurato |
| `frontend/src/api/chatApi.ts` | Creare | Chat API calls |
| `frontend/src/api/chartsApi.ts` | Creare | Charts API calls |
| `frontend/src/types/chat.ts` | Creare | TypeScript types chat |
| `frontend/src/types/charts.ts` | Creare | TypeScript types charts |
| `frontend/src/store/chatStore.ts` | Creare | Zustand store chat |
| `frontend/src/store/chartsStore.ts` | Creare | Zustand store charts |
| `frontend/src/components/Chat/ChatInterface.tsx` | Creare | Main chat component |
| `frontend/src/components/Chat/ChatInput.tsx` | Creare | Chat input box |
| `frontend/src/components/Chat/ChatMessage.tsx` | Creare | Single message component |
| `frontend/src/components/Charts/ChartViewer.tsx` | Creare | Plotly chart renderer |
| `frontend/src/App.tsx` | Creare | App root + routing |
| `frontend/src/main.tsx` | Modificare | React entry point |
| `scripts/start_frontend.sh` | Creare | Script avvio frontend dev server |

## Dipendenze da Installare

### Frontend (Node.js)

Vedi setup progetto Area 1. Principali dipendenze:

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.7",
    "zustand": "^4.5.0",
    "plotly.js-dist-min": "^2.30.0",
    "react-plotly.js": "^2.6.0",
    "lucide-react": "^0.344.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.2.1",
    "class-variance-authority": "^0.7.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@types/plotly.js": "^2.29.0",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.4",
    "tailwindcss": "^3.4.1",
    "postcss": "^8.4.35",
    "autoprefixer": "^10.4.17"
  }
}
```

## Variabili d'Ambiente

**Frontend `.env`:**

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `VITE_API_BASE_URL` | Base URL backend API | `http://localhost:8000` |
| `VITE_APP_NAME` | Nome applicazione | `DataChat BI Platform` |

## Criteri di Completamento

- [ ] Progetto Vite + React + TypeScript inizializzato
- [ ] Tailwind CSS configurato, theme variables definite
- [ ] shadcn/ui components installati (button, card, input, select, etc.)
- [ ] API client Axios configurato con interceptors
- [ ] Zustand stores (chat, charts) funzionanti
- [ ] Componente ChatInterface renderizza messaggi correttamente
- [ ] Componente ChatInput invia query a backend
- [ ] Componente ChartViewer renderizza Plotly charts
- [ ] Routing React Router funziona (/, /saved-charts, /powerbi)
- [ ] Integrazione backend API completa (chat/query testato)
- [ ] Frontend si avvia su localhost:3000 senza errori
- [ ] Responsive design: desktop (1920x1080, 1366x768) funziona
- [ ] Test workflow completo: chat query → visualizza chart → salva chart

## Test di Verifica

### Test 1: Setup e Avvio Frontend

```bash
# Dalla directory frontend/
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\frontend

# Installare dipendenze
npm install

# Avviare dev server
npm run dev

# Output atteso:
# VITE v5.x.x  ready in xxx ms
# ➜  Local:   http://localhost:3000/
# ➜  Network: use --host to expose

# Aprire browser: http://localhost:3000
# UI deve caricare senza errori console
```

### Test 2: Chat Query End-to-End

```
1. Aprire http://localhost:3000
2. Input chat: "Vendite totali per regione"
3. Inviare (pulsante Send o Enter)
4. Verificare:
   - Loading spinner appare
   - Messaggio utente appare (blu, destra)
   - Risposta AI appare (grigio, sinistra) con:
     - Testo NL riassuntivo
     - SQL query (collapsabile)
     - Chart Plotly interattivo (bar chart regioni)
     - Tabella risultati (collapsabile, max 10 righe visibili)
   - Badge execution time ms
5. Hover su chart → tooltip con valori
6. Zoom su chart → funziona
```

### Test 3: Save Chart

```
1. Dopo query con chart (Test 2)
2. Click pulsante "Salva Chart"
3. Verificare alert "Chart salvato con successo! ID: ..."
4. (Opzionale) Navigare a /saved-charts → chart appare in lista
```

### Test 4: Multi-Message Conversation

```
1. Inviare query: "Vendite per categoria"
2. Attendere risposta
3. Inviare follow-up: "Mostralo per sottocategoria"
4. Verificare:
   - Session ID persistito (stesso tra richieste)
   - Entrambi i messaggi visibili nella chat
   - Scroll automatico all'ultimo messaggio
```

### Test 5: LLM Provider Switch

```typescript
// Modificare store chatStore manualmente (o aggiungere UI selector)
import { useChatStore } from './store/chatStore';

// In console browser:
useChatStore.getState().setProvider('azure');

// Inviare query, verificare funziona con Azure OpenAI
// (se configurato in backend .env)
```

### Test 6: Error Handling

```
1. Fermare backend (Ctrl+C su uvicorn)
2. Frontend: inviare query
3. Verificare:
   - Loading spinner scompare
   - Alert rosso con messaggio errore appare
   - Chat input rimane abilitato (retry possibile)
4. Riavviare backend
5. Retry query → funziona
```

### Test 7: Responsive Design

```
1. Aprire DevTools (F12)
2. Toggle device toolbar (Ctrl+Shift+M)
3. Testare risoluzioni:
   - 1920x1080 (desktop full HD) → tutto visibile, layout ottimale
   - 1366x768 (laptop standard) → layout funzionale, scroll verticale
   - 768x1024 (tablet iPad) → layout usabile, nav collapsata opzionale
4. Verificare chart Plotly responsive (width 100%)
```

### Test 8: TypeScript Type Safety

```bash
# Verificare no errori TypeScript
npm run tsc -- --noEmit

# Output atteso: "Found 0 errors"

# Se errori type, fixare prima di procedere
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **Functional components:** Sempre `React.FC<Props>` con TypeScript
2. **Hooks:** Zustand `useChatStore()`, React `useState`, `useEffect`
3. **Event handlers:** Naming convention `handleXxx` (es. `handleSendMessage`)
4. **Async/await:** Tutte le API calls con try/catch
5. **Conditional rendering:** `{condition && <Component />}` o ternary

### Convenzioni Naming

- **Components:** PascalCase `ChatInterface.tsx`
- **Hooks/stores:** camelCase `useChatStore.ts`
- **Types:** PascalCase `ChatMessage`, `SavedChart`
- **CSS classes:** Tailwind utility classes (no custom CSS se possibile)

### Errori Comuni da Evitare

1. **CORS errors:** Verificare backend CORS_ORIGINS include `http://localhost:3000`
2. **Plotly import:** Usare `plotly.js-dist-min` (bundle minimizzato, più veloce)
3. **State mutations:** Zustand immutabile, usare spread operator `[...state.messages, newMsg]`
4. **Missing keys:** Sempre `key={uniqueId}` in `.map()`
5. **Chart re-renders:** Plotly può essere lento, evitare re-render inutili (React.memo se necessario)

### Troubleshooting

**Errore: "Module not found: plotly.js"**
```bash
npm install plotly.js-dist-min react-plotly.js
npm install -D @types/plotly.js @types/react-plotly.js
```

**Errore: "Tailwind classes not working"**
```bash
# Verificare tailwind.config.js content paths
# Riavviare dev server (Ctrl+C, npm run dev)
```

**Chart Plotly non renderizza**
- Verificare `plotly_config.data` non vuoto
- Controllare console browser per errori Plotly
- Test config Plotly manualmente in codepen.io

**API calls CORS blocked**
```python
# Backend main.py, verificare:
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Riavviare backend
```

**Zustand state non aggiorna UI**
- Verificare subscription corretta: `const { messages } = useChatStore();`
- Controllare store mutations sono immutabili
- DevTools: React Developer Tools extension

## Riferimenti

- **BRIEFING.md**: Sezione "Stack Tecnologico" (React 18, TypeScript, Tailwind, Plotly.js, Zustand)
- **PRD.md**: Sezione 7 "Struttura del Progetto" (frontend architecture), Sezione "UI/UX Requirements"
- **Fase precedente**: `phase-06-automazione-power-bi-mcp-modeling.md` (backend completo)
- **React 18 Docs**: https://react.dev/
- **Vite Docs**: https://vitejs.dev/
- **shadcn/ui**: https://ui.shadcn.com/
- **Tailwind CSS**: https://tailwindcss.com/
- **Plotly.js React**: https://plotly.com/javascript/react/
- **Zustand**: https://github.com/pmndrs/zustand
