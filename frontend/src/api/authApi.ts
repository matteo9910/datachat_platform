import { apiClient } from './client';
import type {
  LoginRequest,
  LoginResponse,
  AdminUser,
  CreateUserRequest,
  UpdateUserRequest,
} from '../types/auth';

export const authApi = {
  async login(body: LoginRequest): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>('/api/auth/login', body);
    return response.data;
  },

  async logout(): Promise<{ message: string }> {
    const response = await apiClient.post<{ message: string }>('/api/auth/logout');
    return response.data;
  },

  // Admin user management
  async listUsers(): Promise<AdminUser[]> {
    const response = await apiClient.get<AdminUser[]>('/api/admin/users');
    return response.data;
  },

  async createUser(body: CreateUserRequest): Promise<AdminUser> {
    const response = await apiClient.post<AdminUser>('/api/admin/users', body);
    return response.data;
  },

  async updateUser(userId: string, body: UpdateUserRequest): Promise<AdminUser> {
    const response = await apiClient.put<AdminUser>(`/api/admin/users/${userId}`, body);
    return response.data;
  },

  async getUser(userId: string): Promise<AdminUser> {
    const response = await apiClient.get<AdminUser>(`/api/admin/users/${userId}`);
    return response.data;
  },
};
