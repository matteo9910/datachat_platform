import { apiClient } from './client';

export interface ColumnSchemaResponse {
  original_name: string;
  suggested_name: string;
  pg_type: string;
  nullable: boolean;
  sample_values: any[];
}

export interface UploadResponse {
  import_id: string;
  filename: string;
  file_type: string;
  total_rows: number;
  columns: ColumnSchemaResponse[];
  preview_rows: Record<string, any>[];
}

export interface ColumnOverride {
  original_name: string;
  suggested_name: string;
  pg_type: string;
  nullable: boolean;
}

export interface ConfirmResponse {
  success: boolean;
  table_name: string;
  rows_imported: number;
  errors: string[];
}

export interface ImportHistoryItem {
  id: string;
  original_filename: string;
  table_name: string;
  row_count: number;
  column_count: number;
  source_type: string;
  created_at: string | null;
}

// ERP Template types
export interface ERPTemplateItem {
  id: string;
  erp_name: string;
  export_type: string;
  description: string;
  instructions: string;
  column_count: number;
}

export interface ERPColumnMatch {
  original_name: string;
  matched_erp_column: string | null;
  suggested_name: string;
  pg_type: string;
  nullable: boolean;
  confidence: number;
}

export interface ERPUploadResponse {
  import_id: string;
  filename: string;
  file_type: string;
  total_rows: number;
  template_id: string;
  erp_name: string;
  columns: ERPColumnMatch[];
  preview_rows: Record<string, any>[];
}

export const importsApi = {
  async upload(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post('/api/imports/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
    return res.data;
  },

  async confirm(
    importId: string,
    tableName: string,
    columns: ColumnOverride[],
  ): Promise<ConfirmResponse> {
    const res = await apiClient.post('/api/imports/confirm', {
      import_id: importId,
      table_name: tableName,
      columns,
    });
    return res.data;
  },

  async getHistory(): Promise<ImportHistoryItem[]> {
    const res = await apiClient.get('/api/imports/history');
    return res.data;
  },

  // ERP Template methods
  async getERPTemplates(): Promise<ERPTemplateItem[]> {
    const res = await apiClient.get('/api/imports/erp/templates');
    return res.data;
  },

  async uploadERP(templateId: string, file: File): Promise<ERPUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post(
      `/api/imports/erp/upload?template_id=${encodeURIComponent(templateId)}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
    );
    return res.data;
  },
};
