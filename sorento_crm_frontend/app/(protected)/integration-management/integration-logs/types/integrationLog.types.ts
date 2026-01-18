export interface IntegrationLog {
  id: string;
  integration_channel: string;
  business_table: string;
  business_id: string;
  external_reference?: string | null;
  direction: 'inbound' | 'outbound';
  endpoint: string;
  http_method: string;
  request_headers?: string | null;
  request_payload?: string | null;
  status_code?: number | null;
  status: 'pending' | 'processing' | 'success' | 'failed';
  response_headers?: string | null;
  response_payload?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  correlation_id?: string | null;
  retry_count: number;
  max_retry_allowed: number;
  next_retry_at?: Date | string | null;
  created_at: Date | string;
  created_by?: string | null;
  processed_at?: Date | string | null;
  updated_at: Date | string;
}

export interface IntegrationLogResponse {
  id: string;
  integration_channel: string;
  business_table: string;
  business_id: string;
  external_reference?: string | null;
  direction: 'inbound' | 'outbound';
  endpoint: string;
  http_method: string;
  request_headers?: string | null;
  request_payload?: string | null;
  status_code?: number | null;
  status: 'pending' | 'processing' | 'success' | 'failed';
  response_headers?: string | null;
  response_payload?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  correlation_id?: string | null;
  retry_count: number;
  max_retry_allowed: number;
  next_retry_at?: Date | string | null;
  created_at: Date | string;
  created_by?: string | null;
  processed_at?: Date | string | null;
  updated_at: Date | string;
}
