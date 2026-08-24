/**
 * Types for the integration management screen (AC-AC-08).
 *
 * Note what is absent: there is no field here for a key or a credential. The
 * backend never sends either. `hasCredentials` reports that a credential is
 * set; the plaintext of a key exists client-side only in the one-time response
 * to issuing or rotating it, modelled by `IssuedKey`.
 */

export type IntegrationStatus = 'ACTIVE' | 'UNVERIFIED' | 'ERROR';

export interface IntegrationApiKey {
  id: string;
  key_prefix: string;
  expires_at: string | null;
  revoked_at: string | null;
  rotated_from_id: string | null;
  last_used_at: string | null;
  created_at: string;
  /** Server-computed. Do not re-derive from the dates - the auth path owns this rule. */
  is_active: boolean;
}

export interface Integration {
  id: string;
  name: string;
  type: string;
  status: IntegrationStatus;
  act_as_user_id: string | null;
  act_as_user_name: string | null;
  config_json: Record<string, unknown> | null;
  /** Whether a credential is stored - never what it is. */
  has_credentials: boolean;
  is_active: boolean;
  last_used_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  keys: IntegrationApiKey[];
}

/**
 * The only shape carrying a plaintext key. Returned once, never retrievable.
 * Must not be persisted to storage or written to logs.
 */
export interface IssuedKey {
  key: string;
  key_prefix: string;
  integration_id: string;
  warning: string;
}

export interface IntegrationCreatePayload {
  name: string;
  type: string;
  act_as_user_id?: string | null;
  config_json?: Record<string, unknown> | null;
  credentials_json?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface IntegrationUpdatePayload {
  name?: string;
  type?: string;
  act_as_user_id?: string | null;
  config_json?: Record<string, unknown> | null;
  /** Omit to keep the existing credential. Never send an empty object to "clear". */
  credentials_json?: Record<string, unknown> | null;
  is_active?: boolean;
}
