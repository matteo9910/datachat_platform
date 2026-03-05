import { apiClient } from './client';

export interface KBPair {
  id: string;
  question: string;
  sql_query: string;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateKBPairRequest {
  question: string;
  sql_query: string;
}

export interface UpdateKBPairRequest {
  question?: string;
  sql_query?: string;
}

export const knowledgeApi = {
  async getPairs(): Promise<KBPair[]> {
    const response = await apiClient.get<KBPair[]>('/api/knowledge/pairs');
    return response.data;
  },

  async createPair(body: CreateKBPairRequest): Promise<KBPair> {
    const response = await apiClient.post<KBPair>('/api/knowledge/pairs', body);
    return response.data;
  },

  async updatePair(pairId: string, body: UpdateKBPairRequest): Promise<KBPair> {
    const response = await apiClient.put<KBPair>(`/api/knowledge/pairs/${pairId}`, body);
    return response.data;
  },

  async deletePair(pairId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/knowledge/pairs/${pairId}`);
    return response.data;
  },
};
