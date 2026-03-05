import { apiClient } from './client';

export interface Instruction {
  id: string;
  type: 'global' | 'topic';
  topic: string | null;
  text: string;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateInstructionRequest {
  type: 'global' | 'topic';
  topic?: string;
  text: string;
}

export interface UpdateInstructionRequest {
  type?: 'global' | 'topic';
  topic?: string;
  text?: string;
}

export const instructionsApi = {
  async getInstructions(): Promise<Instruction[]> {
    const response = await apiClient.get<Instruction[]>('/api/knowledge/instructions');
    return response.data;
  },

  async createInstruction(body: CreateInstructionRequest): Promise<Instruction> {
    const response = await apiClient.post<Instruction>('/api/knowledge/instructions', body);
    return response.data;
  },

  async updateInstruction(id: string, body: UpdateInstructionRequest): Promise<Instruction> {
    const response = await apiClient.put<Instruction>(`/api/knowledge/instructions/${id}`, body);
    return response.data;
  },

  async deleteInstruction(id: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/knowledge/instructions/${id}`);
    return response.data;
  },
};