export enum LLMProvider {
  CLAUDE = 'claude',
  AZURE = 'azure',
  GPT52 = 'gpt52'
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sql?: string;
  results?: any[];
  chart?: any;
  chartType?: string;  // 'bar', 'line', 'pie', 'table', etc.
  charts?: any[];  // Multi-visualization support
  timestamp: Date;
  executionTimeMs?: number;
  thinkingSteps?: ThinkingStep[];
  thoughtProcess?: string[];  // Bullet point reasoning like Wren AI
  suggestedFollowups?: string[];
  trustScore?: number;
  trustGrade?: 'high' | 'medium' | 'low';
  trustFactors?: Record<string, any>;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: Date;
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

export interface SavedChart {
  id: string;
  title: string;
  description: string;
  sqlTemplate: string;
  parameters: Record<string, Parameter>;
  plotlyConfig: any;
  createdAt: Date;
}

export interface DashboardLayout {
  chartId: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface UserDashboard {
  id: string;
  name: string;
  layouts: DashboardLayout[];
  createdAt: Date;
  updatedAt?: Date;
}

export interface DBTable {
  name: string;
  columns: { name: string; type: string; nullable: boolean; isPK?: boolean; isFK?: boolean }[];
  rowCount?: number;
}

export interface ThinkingStepDetail {
  title: string;
  content: any;
}

export interface ThinkingStep {
  step: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  duration_ms?: number;
  details?: ThinkingStepDetail[];
}

export interface ChatQueryResponse {
  success: boolean;
  session_id: string;
  nl_response: string;
  sql: string;
  results: Record<string, any>[];
  chart?: {
    chart_type: string;
    chart_title?: string;
    plotly_config: any;
    parameters: Record<string, Parameter>;
    sql_template: string;
    charts?: any[];  // Multi-visualization support
  } | null;
  execution_time_ms: number;
  error?: string | null;
  thinking_steps?: ThinkingStep[];
  thought_process?: string[];  // Bullet point reasoning
  suggested_followups?: string[];
  should_show_chart?: boolean;
  trust_score?: number;
  trust_grade?: 'high' | 'medium' | 'low';
  trust_factors?: Record<string, any>;
}