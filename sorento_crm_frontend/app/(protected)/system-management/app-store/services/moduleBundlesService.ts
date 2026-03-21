import { apiFetch } from '@/lib/api';

export interface ModuleBundleDTO {
  bundle_key: string;
  display_name: string;
  module_keys: string[];
  sort_order?: string | null;
}

function errorMessage(res: Response, fallback: string): Promise<string> {
  return res
    .json()
    .then((body: { detail?: unknown }) => {
      const d = body?.detail;
      if (typeof d === 'string') return d;
      if (d && typeof d === 'object' && 'message' in d) {
        return String((d as { message?: string }).message) || fallback;
      }
      return fallback;
    })
    .catch(() => fallback);
}

export async function fetchModuleBundles(): Promise<ModuleBundleDTO[]> {
  const res = await apiFetch('/api/v1/system/modules/bundles');
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Failed to load bundles (${res.status})`));
  }
  return res.json();
}

export async function createModuleBundle(body: {
  bundle_key: string;
  display_name: string;
  module_keys: string[];
  sort_order?: string | null;
}): Promise<ModuleBundleDTO> {
  const res = await apiFetch('/api/v1/system/modules/bundles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...body,
      sort_order: body.sort_order?.trim() || undefined,
    }),
  });
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Create failed (${res.status})`));
  }
  return res.json();
}

export async function updateModuleBundle(
  bundleKey: string,
  body: {
    display_name?: string;
    module_keys?: string[];
    sort_order?: string | null;
  },
): Promise<ModuleBundleDTO> {
  const res = await apiFetch(
    `/api/v1/system/modules/bundles/${encodeURIComponent(bundleKey)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...body,
        sort_order:
          body.sort_order === undefined
            ? undefined
            : body.sort_order === null || body.sort_order === ''
              ? ''
              : body.sort_order.trim(),
      }),
    },
  );
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Update failed (${res.status})`));
  }
  return res.json();
}

export async function deleteModuleBundle(bundleKey: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/system/modules/bundles/${encodeURIComponent(bundleKey)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) {
    throw new Error(await errorMessage(res, `Delete failed (${res.status})`));
  }
}
