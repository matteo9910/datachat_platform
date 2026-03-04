import { apiClient } from './client';

export interface SaveChartRequest {
  title: string;
  description?: string;
  sql_template: string;
  parameters: Record<string, any>;
  plotly_config: any;
}

export interface ChartListItem {
  chart_id: string;
  title: string;
  description?: string;
  sql_template: string;
  parameters: Record<string, any>;
  plotly_config: any;
  created_at: string;
  updated_at?: string;
}

export interface SavedChartResponse {
  chart_id: string;
  title: string;
  description?: string;
  sql_template: string;
  parameters: Record<string, any>;
  plotly_config: any;
  created_at: string;
  updated_at?: string;
}

export const chartsApi = {
  async save(request: SaveChartRequest): Promise<{ chart_id: string; created_at: string }> {
    const response = await apiClient.post('/api/charts/save', request);
    return response.data;
  },

  async list(): Promise<ChartListItem[]> {
    const response = await apiClient.get('/api/charts');
    return response.data.charts || [];
  },

  async get(chartId: string): Promise<SavedChartResponse> {
    const response = await apiClient.get(`/api/charts/${chartId}`);
    return response.data;
  },

  async updateParameters(
    chartId: string,
    params: Record<string, any>,
    llmProvider: string = 'claude'
  ): Promise<{ plotly_config: any; results: any[] }> {
    const response = await apiClient.put(`/api/charts/${chartId}/parameters`, {
      parameters: params,
      llm_provider: llmProvider
    });
    return response.data;
  },

  async delete(chartId: string): Promise<void> {
    await apiClient.delete(`/api/charts/${chartId}`);
  },

  async modifyWithNL(
    chartId: string,
    modificationRequest: string,
    llmProvider: string = 'claude'
  ): Promise<{
    success: boolean;
    chart_id: string;
    sql: string;
    results: any[];
    plotly_config: any;
    chart_title?: string;
    execution_time_ms: number;
  }> {
    const response = await apiClient.post(`/api/charts/${chartId}/modify`, {
      modification_request: modificationRequest,
      llm_provider: llmProvider
    });
    return response.data;
  },

  async modifyVisualization(request: {
    current_plotly_config: any;
    modification_request: string;
    sql_query: string;
    original_results: any[];
    llm_provider: string;
  }): Promise<{
    success: boolean;
    plotly_config: any;
    execution_time_ms: number;
  }> {
    const response = await apiClient.post('/api/charts/modify-visualization', request);
    return response.data;
  },
};