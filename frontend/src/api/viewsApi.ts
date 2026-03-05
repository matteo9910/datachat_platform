import { apiClient } from './client';

export interface SqlView {
  id: string;
  view_name: string;
  sql_query: string;
  created_by: string | null;
  client_db_id: string | null;
  created_at: string | null;
}

export interface CreateViewRequest {
  view_name: string;
  sql_query: string;
}

export const viewsApi = {
  async getViews(): Promise<SqlView[]> {
    const response = await apiClient.get<SqlView[]>('/api/views');
    return response.data;
  },

  async createView(body: CreateViewRequest): Promise<SqlView> {
    const response = await apiClient.post<SqlView>('/api/views', body);
    return response.data;
  },

  async deleteView(viewId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/views/${viewId}`);
    return response.data;
  },
};