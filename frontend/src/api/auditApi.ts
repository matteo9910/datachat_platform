import { apiClient } from './client';

export interface AuditDimension {
  score: number;
  weight: number;
  issues_count: number;
  issues: AuditIssue[];
}

export interface AuditIssue {
  severity: 'high' | 'medium' | 'low';
  table: string;
  column: string | null;
  message: string;
}

export interface AuditReportResponse {
  id?: string;
  overall_score: number;
  dimensions: Record<string, AuditDimension>;
  recommendations: string[];
  summary: string;
  table_count: number;
  generated_at: string;
}

export interface AuditHistoryItem {
  id: string;
  overall_score: number;
  table_count: number;
  summary: string;
  created_at: string | null;
}

export const auditApi = {
  async runAudit(llmProvider?: string): Promise<AuditReportResponse> {
    const res = await apiClient.post('/api/database/audit/run', {
      llm_provider: llmProvider || undefined,
    }, { timeout: 180000 });
    return res.data;
  },

  async getLatest(): Promise<AuditReportResponse | null> {
    const res = await apiClient.get('/api/database/audit/latest');
    return res.data;
  },

  async getHistory(limit: number = 20): Promise<AuditHistoryItem[]> {
    const res = await apiClient.get('/api/database/audit/history', {
      params: { limit },
    });
    return res.data;
  },
};
