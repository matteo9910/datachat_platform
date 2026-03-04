import { apiClient } from './client';
import { ChatQueryResponse, ThinkingStep } from '../types';

export interface ChatQueryRequest {
  query: string;
  session_id?: string;
  llm_provider: 'claude' | 'azure' | 'gpt52';
  include_chart?: boolean;
}

export interface StreamEvent {
  type: 'thinking_step' | 'result' | 'error';
  step?: ThinkingStep;
  data?: ChatQueryResponse;
  error?: string;
}

export const chatApi = {
  async query(request: ChatQueryRequest): Promise<ChatQueryResponse> {
    const response = await apiClient.post<ChatQueryResponse>('/api/chat/query', request);
    return response.data;
  },

  // Streaming query with real-time thinking steps
  async queryStream(
    request: ChatQueryRequest,
    onThinkingStep: (step: ThinkingStep) => void,
    onResult: (result: ChatQueryResponse) => void,
    onError: (error: string) => void,
    signal?: AbortSignal
  ): Promise<void> {
    const response = await fetch('http://localhost:8000/api/chat/query/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader available');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event: StreamEvent = JSON.parse(line.slice(6));
            
            if (event.type === 'thinking_step' && event.step) {
              onThinkingStep(event.step);
            } else if (event.type === 'result' && event.data) {
              onResult(event.data);
            } else if (event.type === 'error') {
              onError(event.error || 'Unknown error');
            }
          } catch (e) {
            console.error('Error parsing SSE event:', e);
          }
        }
      }
    }
  },

  async getHistory(sessionId: string): Promise<any> {
    const response = await apiClient.get(`/api/chat/history/${sessionId}`);
    return response.data;
  },
};