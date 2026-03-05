import { apiClient } from './client';

export type DataSourceType = 'postgres' | 'supabase';

export interface ConnectionStatus {
  connected: boolean;
  source_type?: DataSourceType;
  active_database?: string;
  host?: string;
  port?: number;
  username?: string;
  project_ref?: string;
  message: string;
  using_mcp: boolean;
  enabled_databases: string[];
}

export interface ConnectionParams {
  host: string;
  port: number;
  username: string;
  password: string;
}

export interface SupabaseConnectionParams {
  project_ref: string;
  service_role_key?: string;  // Per connessione REST API
  personal_access_token?: string;  // Per connessione MCP nativa
}

export interface DataSourceInfo {
  type: DataSourceType;
  name: string;
  description: string;
  icon: string;
  configured: boolean;
  connected: boolean;
}

export interface DatabaseInfo {
  name: string;
  size?: string;
  tables_count: number;
}

export interface TableColumn {
  name: string;
  type: string;
  nullable: boolean;
  isPK: boolean;
  isFK: boolean;
  fkReferences?: string;
}

export interface TableInfo {
  name: string;
  schema_name: string;
  row_count?: number;
  columns: TableColumn[];
  type?: 'table' | 'view';
}

export interface SchemaResponse {
  database: string;
  tables: TableInfo[];
}

export interface TablePreviewResponse {
  table_name: string;
  columns: string[];
  rows: Record<string, any>[];
  total_rows: number;
  preview_limit: number;
}

export interface Relationship {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  constraint_name: string;
  relationship_type: '1:1' | '1:N' | 'N:M';
}

export interface RelationshipsResponse {
  database: string;
  relationships: Relationship[];
  count: number;
}

export interface OAuthInitResponse {
  auth_url: string;
  state: string;
}

export interface SupabaseProject {
  id: string;
  name: string;
  ref: string;
  region: string;
  organization_id: string;
}

export const databaseApi = {
  async getSources(): Promise<DataSourceInfo[]> {
    const response = await apiClient.get('/api/database/sources');
    return response.data;
  },

  async getStatus(): Promise<ConnectionStatus> {
    const response = await apiClient.get('/api/database/status');
    return response.data;
  },

  async connect(params: ConnectionParams): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/connect', params);
    return response.data;
  },

  async connectSupabase(params: SupabaseConnectionParams): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/connect/supabase', params);
    return response.data;
  },

  async oauthInit(): Promise<OAuthInitResponse> {
    const response = await apiClient.get('/api/database/oauth/init');
    return response.data;
  },

  async oauthCallback(code: string, state: string): Promise<{ status: string; message: string }> {
    const response = await apiClient.post('/api/database/oauth/callback', { code, state });
    return response.data;
  },

  async oauthListProjects(): Promise<{ projects: SupabaseProject[] }> {
    const response = await apiClient.get('/api/database/oauth/projects');
    return response.data;
  },

  async oauthSelectProject(projectRef: string): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/oauth/select-project', { project_ref: projectRef });
    return response.data;
  },

  async connectSupabaseWithPassword(projectRef: string, dbPassword: string, region?: string): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/connect/supabase-password', { 
      project_ref: projectRef, 
      db_password: dbPassword,
      region: region
    });
    return response.data;
  },

  async connectWithConnectionString(connectionString: string, projectRef?: string): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/connect/connection-string', { 
      connection_string: connectionString,
      project_ref: projectRef
    });
    return response.data;
  },

  async switchSource(sourceType: DataSourceType): Promise<ConnectionStatus> {
    const response = await apiClient.post(`/api/database/switch/${sourceType}`);
    return response.data;
  },

  async disconnect(): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post('/api/database/disconnect');
    return response.data;
  },

  async enableDatabases(databases: string[]): Promise<{ success: boolean; enabled_databases: string[]; message: string }> {
    const response = await apiClient.post('/api/database/enable-databases', databases);
    return response.data;
  },

  async selectDatabase(database: string): Promise<ConnectionStatus> {
    const response = await apiClient.post('/api/database/select-database', { database });
    return response.data;
  },

  async listDatabases(): Promise<DatabaseInfo[]> {
    const response = await apiClient.get('/api/database/databases');
    return response.data;
  },

  async getSchema(): Promise<SchemaResponse> {
    const response = await apiClient.get('/api/database/schema');
    return response.data;
  },

  async listTables(): Promise<{ tables: { name: string; row_count: number }[] }> {
    const response = await apiClient.get('/api/database/tables');
    return response.data;
  },

  async getTablePreview(tableName: string, limit: number = 50): Promise<TablePreviewResponse> {
    const response = await apiClient.get(`/api/database/tables/${tableName}/preview`, {
      params: { limit }
    });
    return response.data;
  },

  async getRelationships(): Promise<RelationshipsResponse> {
    const response = await apiClient.get('/api/database/relationships');
    return response.data;
  }
};
