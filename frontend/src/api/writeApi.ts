import { apiClient } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GenerateWriteRequest {
  nl_text: string;
  llm_provider?: string;
}

export interface GenerateWriteResponse {
  sql: string;
  estimated_rows: number | null;
  target_tables: string[];
  target_columns: string[];
  is_bulk: boolean;
}

export interface ExecuteWriteRequest {
  sql: string;
  extra_confirmation?: boolean;
}

export interface ExecuteWriteResponse {
  success: boolean;
  rows_affected: number;
  message: string;
}

export interface WhitelistEntry {
  id: string | null;
  table_name: string;
  column_name: string;
  created_at: string | null;
}

export interface WhitelistSaveRequest {
  entries: { table_name: string; column_name: string }[];
}

export interface TableColumn {
  column_name: string;
  data_type: string;
}

export interface AvailableTable {
  table_name: string;
  columns: TableColumn[];
}

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  action: string;
  resource: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string | null;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const writeApi = {
  // Write generation & execution
  async generateSQL(body: GenerateWriteRequest): Promise<GenerateWriteResponse> {
    const response = await apiClient.post<GenerateWriteResponse>('/api/write/generate', body);
    return response.data;
  },

  async executeSQL(body: ExecuteWriteRequest): Promise<ExecuteWriteResponse> {
    const response = await apiClient.post<ExecuteWriteResponse>('/api/write/execute', body);
    return response.data;
  },

  // Whitelist CRUD
  async getWhitelist(): Promise<WhitelistEntry[]> {
    const response = await apiClient.get<WhitelistEntry[]>('/api/write/whitelist');
    return response.data;
  },

  async saveWhitelist(body: WhitelistSaveRequest): Promise<WhitelistEntry[]> {
    const response = await apiClient.post<WhitelistEntry[]>('/api/write/whitelist', body);
    return response.data;
  },

  async deleteWhitelistEntry(entryId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/write/whitelist/${entryId}`);
    return response.data;
  },

  async getAvailableTables(): Promise<AvailableTable[]> {
    const response = await apiClient.get<{ tables: AvailableTable[] }>('/api/write/whitelist/available-tables');
    return response.data.tables;
  },

  // Audit logs
  async getAuditLogs(page = 1, pageSize = 20): Promise<AuditLogListResponse> {
    const response = await apiClient.get<AuditLogListResponse>(
      `/api/audit/logs?page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },
};
