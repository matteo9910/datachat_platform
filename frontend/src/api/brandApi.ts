import { apiClient } from './client';

export interface BrandConfig {
  id: string | null;
  primary_color: string;
  secondary_color: string;
  accent_colors: string[];
  font_family: string;
  logo_url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SaveBrandConfigRequest {
  primary_color: string;
  secondary_color: string;
  accent_colors?: string[];
  font_family?: string;
  logo_url?: string;
}

export const brandApi = {
  async getConfig(): Promise<BrandConfig> {
    const response = await apiClient.get<BrandConfig>('/api/brand/config');
    return response.data;
  },

  async saveConfig(body: SaveBrandConfigRequest): Promise<BrandConfig> {
    const response = await apiClient.post<BrandConfig>('/api/brand/config', body);
    return response.data;
  },
};