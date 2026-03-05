import { apiClient } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChartSpec {
  title: string;
  sql: string;
  chart_type: string;
  plotly_config?: any;
  data?: any[];
}

export interface DashboardGenerateResponse {
  charts: ChartSpec[];
  layout: { columns: number; positions: any[]; total_width: number; total_height: number };
  suggested_name: string;
}

export interface DashboardSaveRequest {
  name: string;
  layout?: any;
  charts?: any[];
  filters?: any;
}

export interface DashboardResponse {
  id: string;
  name: string;
  layout?: any;
  charts?: any[];
  filters?: any;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface DashboardListItem {
  id: string;
  name: string;
  charts_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface FilterOption {
  column: string;
  filter_type: 'date' | 'categorical' | 'numeric';
  values?: any[];
  min_val?: any;
  max_val?: any;
  label: string;
}

export interface ApplyFiltersResponse {
  charts: any[];
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const dashboardApi = {
  /** NL description -> dashboard config with charts */
  async generate(description: string, llmProvider: string = 'azure'): Promise<DashboardGenerateResponse> {
    const resp = await apiClient.post('/api/dashboard/generate', {
      description,
      llm_provider: llmProvider,
    });
    return resp.data;
  },

  /** Save a new dashboard */
  async save(request: DashboardSaveRequest): Promise<DashboardResponse> {
    const resp = await apiClient.post('/api/dashboards', request);
    return resp.data;
  },

  /** List saved dashboards */
  async list(): Promise<DashboardListItem[]> {
    const resp = await apiClient.get('/api/dashboards');
    return resp.data;
  },

  /** Get dashboard detail */
  async get(id: string): Promise<DashboardResponse> {
    const resp = await apiClient.get(`/api/dashboards/${id}`);
    return resp.data;
  },

  /** Update dashboard */
  async update(id: string, request: DashboardSaveRequest): Promise<DashboardResponse> {
    const resp = await apiClient.put(`/api/dashboards/${id}`, request);
    return resp.data;
  },

  /** Delete dashboard */
  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/dashboards/${id}`);
  },

  /** Apply global filters to all charts */
  async applyFilters(dashboardId: string, filterValues: Record<string, any>): Promise<ApplyFiltersResponse> {
    const resp = await apiClient.post('/api/dashboard/apply-filters', {
      dashboard_id: dashboardId,
      filter_values: filterValues,
    });
    return resp.data;
  },

  /** Get available filters for a dashboard */
  async getAvailableFilters(dashboardId: string): Promise<FilterOption[]> {
    const resp = await apiClient.get(`/api/dashboard/${dashboardId}/available-filters`);
    return resp.data.filters;
  },
};