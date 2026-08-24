/**
 * useFieldLinkageSchema - fetches the per-entity-type field registry the
 * backend exposes at GET /api/v1/master-data/field-linkage-schema.
 *
 * Used by:
 * - the attachment upload modal (Linked Fields multi-select).
 * - the per-row "Manage field links" dialog on the Product Attachments tab
 *    and AttachmentDetailModal Linkages tabs.
 * - the Specifications tooltip when grouping composite fields under a
 *    `group_key` (e.g. dimensions_length / _width / _height share `dimensions`).
 */
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type FieldLinkageEntityType =
  | 'product'
  | 'promotion'
  | 'packing_list'
  | 'form';

export interface FieldLinkageSpec {
  name: string;
  label: string;
  kind: 'text' | 'number' | 'lookup' | 'fk' | 'date';
  unit: string | null;
  group_key: string | null;
  extract_note: string | null;
}

export interface FieldLinkageSchema {
  entity_type: FieldLinkageEntityType;
  fields: FieldLinkageSpec[];
}

export async function getFieldLinkageSchema(
  entityType: FieldLinkageEntityType,
): Promise<FieldLinkageSchema> {
  const response = await apiFetch(
    `/api/v1/master-data/field-linkage-schema?entity_type=${entityType}`,
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load field linkage schema'),
    );
  }
  return response.json();
}

export function useFieldLinkageSchema(
  entityType: FieldLinkageEntityType | null | undefined,
) {
  return useQuery({
    queryKey: ['field-linkage-schema', entityType],
    queryFn: () => getFieldLinkageSchema(entityType as FieldLinkageEntityType),
    enabled: Boolean(entityType),
    staleTime: 5 * 60 * 1000,
  });
}

/** Group field specs by ``group_key``. Specs without a group_key go into the
 *  catch-all ``__solo`` bucket (rendered alongside groups). */
export function groupFieldSpecs(
  specs: FieldLinkageSpec[],
): { groupKey: string; label: string; specs: FieldLinkageSpec[] }[] {
  const buckets = new Map<string, FieldLinkageSpec[]>();
  for (const spec of specs) {
    const key = spec.group_key || `__solo:${spec.name}`;
    const arr = buckets.get(key) ?? [];
    arr.push(spec);
    buckets.set(key, arr);
  }
  return Array.from(buckets.entries()).map(([groupKey, items]) => ({
    groupKey,
    label: groupKey.startsWith('__solo:') ? items[0].label : groupLabel(groupKey),
    specs: items,
  }));
}

function groupLabel(groupKey: string): string {
  if (groupKey === 'dimensions') return 'Dimensions (L × W × H)';
  // Title-case fallback: capitalize first letter of each word.
  return groupKey
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
