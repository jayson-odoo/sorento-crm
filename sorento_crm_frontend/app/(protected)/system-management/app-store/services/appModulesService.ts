import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  modulePurgeTables as discoveredPurgeTables,
  modulesWithDataPurge as discoveredModulesWithPurge,
} from '@/modules/registry';

export interface TenantModuleState {
  module_key: string;
  display_name: string;
  description: string;
  dependencies: string[];
  /** Tenant has a tenant_modules row (omit on older API — treated as true). */
  installed?: boolean;
  enabled: boolean;
}

export interface ModuleBundleInfo {
  bundle_key: string;
  display_name: string;
  module_keys: string[];
}

export interface MyModulesPayload {
  tenant_id: string;
  modules: TenantModuleState[];
  bundles: ModuleBundleInfo[];
  module_guard_strict: boolean;
}

export interface ModuleInstallEvent {
  id: string;
  tenant_id: string;
  module_key: string;
  action: string;
  actor_user_id?: string | null;
  detail?: Record<string, unknown> | null;
  created_at?: string | null;
}

export async function fetchMyModules(): Promise<MyModulesPayload> {
  const res = await apiFetch('/api/v1/system/modules/me');
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Failed to load modules (${res.status})`));
  }
  return res.json();
}

export async function installModulesOrBundle(body: {
  module_keys?: string[];
  bundle_key?: string;
}): Promise<{ installed: string[]; plan: string[]; bundle?: string }> {
  const res = await apiFetch('/api/v1/system/modules/install', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ||
        (typeof err === 'object' && err !== null && 'message' in err
          ? String((err as { message?: string }).message)
          : `Install failed (${res.status})`),
    );
  }
  return res.json();
}

export async function enableModule(moduleKey: string): Promise<void> {
  const res = await apiFetch(`/api/v1/system/modules/${encodeURIComponent(moduleKey)}/enable`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Enable failed (${res.status})`);
  }
}

export async function disableModule(moduleKey: string): Promise<void> {
  const res = await apiFetch(`/api/v1/system/modules/${encodeURIComponent(moduleKey)}/disable`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: unknown }).detail;
    const message =
      typeof detail === 'object' && detail !== null && 'message' in detail
        ? String((detail as { message?: string }).message)
        : typeof detail === 'string'
          ? detail
          : `Disable failed (${res.status})`;
    throw new Error(message);
  }
}

/** Modules with automated DB purge on uninstall (others: uninstall removes tenant binding only). */
const LEGACY_MODULES_WITH_DATA_PURGE: string[] = [
  'notifications',
  'audit',
  'sla',
  'forms',
  'workflow_forms',
  'marketing',
  'complaints',
  'public_view_links',
];

export const MODULES_WITH_DATA_PURGE: string[] = Array.from(
  new Set([...discoveredModulesWithPurge(), ...LEGACY_MODULES_WITH_DATA_PURGE]),
);

/**
 * Physical DB tables cleared when purge runs, in deletion order (FK-safe).
 * Keep in sync with `sorento_crm_backend/app/services/module_purge_service.py`.
 *
 * Legacy hardcoded entries below; migrated modules ship purge_tables.json under
 * `modules/<key>/` and merge in via `discoveredPurgeTables()`. Discovered entries win.
 */
const LEGACY_MODULE_PURGE_TABLES: Record<
  string,
  { tables: string[]; description?: string }
> = {
  notifications: {
    tables: ['notification_deliveries', 'notifications', 'push_subscriptions'],
    description: 'In-app notifications, delivery rows, and web push subscriptions.',
  },
  audit: {
    tables: ['audit_logs'],
    description: 'Audit log entries.',
  },
  sla: {
    tables: [
      'conversation_sla_event_log',
      'conversation_sla_tracking',
      'sla_policy_tiers',
      'sla_policies',
    ],
    description: 'SLA policies, tiers, conversation tracking, and SLA event history.',
  },
  forms: {
    tables: [
      'form_submissions',
      'form_versions',
      'form_fields',
      'form_sections',
      'forms',
    ],
    description: 'Form definitions, versions, fields, and submissions. Uploaded files in storage are not deleted.',
  },
  marketing: {
    tables: [
      'marketing_campaigns',
      'promotion_attachments',
      'promotion_products',
      'promotions',
      'campaign_types',
    ],
    description: 'Campaigns, promotions, and promotion link rows.',
  },
  complaints: {
    tables: [
      'complaint_manual_attachments',
      'complaint_attachments',
      'complaints',
    ],
    description: 'Complaint records and attachment link rows (not binary files in storage).',
  },
  public_view_links: {
    tables: ['view_tokens'],
    description:
      'Shareable public-view tokens only. Related records (stock inquiries, purchase requests, complaints, etc.) are not deleted.',
  },
  workflow_forms: {
    tables: [
      'workflow_submission_transition_logs',
      'workflow_submission_lines',
      'workflow_submissions',
      'workflow_form_versions',
      'workflow_form_definitions',
    ],
    description: 'Workflow form definitions, published versions, submissions, and history.',
  },
};

export const MODULE_PURGE_TABLES: Record<
  string,
  { tables: string[]; description?: string }
> = { ...LEGACY_MODULE_PURGE_TABLES, ...discoveredPurgeTables() };

export async function uninstallModule(
  moduleKey: string,
  confirmation: string,
  purgeData: boolean,
): Promise<{
  module_key: string;
  installed: boolean;
  enabled: boolean;
  purge_data: boolean;
  rows_deleted?: Record<string, number> | null;
  message?: string | null;
}> {
  const res = await apiFetch(`/api/v1/system/modules/${encodeURIComponent(moduleKey)}/uninstall`, {
    method: 'POST',
    body: JSON.stringify({ confirmation, purge_data: purgeData }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: unknown }).detail;
    const message =
      typeof detail === 'object' && detail !== null && 'message' in detail
        ? String((detail as { message?: string }).message)
        : typeof detail === 'string'
          ? detail
          : `Uninstall failed (${res.status})`;
    throw new Error(message);
  }
  return res.json();
}

export interface UploadModuleResult {
  module_key: string;
  version: string;
  status: string;
  needs_frontend_rebuild: boolean;
  restart_required: boolean;
  extracted_backend_files: string[];
  extracted_frontend_files: string[];
}

export async function uploadModule(file: File): Promise<UploadModuleResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch('/api/v1/system/modules/upload', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Upload failed (${res.status})`));
  }
  return res.json();
}

export async function activateUploadedModule(
  moduleKey: string,
): Promise<{ installed: string[]; plan: string[] }> {
  const res = await apiFetch(
    `/api/v1/system/modules/${encodeURIComponent(moduleKey)}/activate`,
    { method: 'POST' },
  );
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Activate failed (${res.status})`));
  }
  return res.json();
}

export interface AvailableModule {
  module_key: string;
  display_name: string;
  description: string;
  dependencies: string[];
}

export async function fetchAvailableModules(): Promise<AvailableModule[]> {
  const res = await apiFetch('/api/v1/system/modules/available');
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Failed to load available (${res.status})`));
  }
  return res.json();
}

export async function removeUploadedModule(moduleKey: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/system/modules/${encodeURIComponent(moduleKey)}/remove`,
    { method: 'DELETE' },
  );
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Remove failed (${res.status})`));
  }
}

export async function downloadModuleZip(moduleKey: string): Promise<{ blob: Blob; filename: string }> {
  const res = await apiFetch(`/api/v1/system/modules/${encodeURIComponent(moduleKey)}/export`);
  if (!res.ok) {
    throw new Error(await extractApiError(res, `Export failed (${res.status})`));
  }
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? `${moduleKey}.zip`;
  const blob = await res.blob();
  return { blob, filename };
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function fetchModuleInstallEvents(params?: {
  limit?: number;
  offset?: number;
}): Promise<{
  items: ModuleInstallEvent[];
  total: number;
  limit: number;
  offset: number;
}> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.offset != null) sp.set('offset', String(params.offset));
  const q = sp.toString();
  const res = await apiFetch(`/api/v1/system/modules/events${q ? `?${q}` : ''}`);
  if (!res.ok) {
    throw new Error(`Failed to load install events (${res.status})`);
  }
  return res.json();
}
