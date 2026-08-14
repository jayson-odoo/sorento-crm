import { readable } from '@/lib/spec-readable';
import type { SpecKeyDefinition, SpecScalar, SpecTableRow } from './types';

/**
 * Turn one product's stored specs into the rows a person reads.
 *
 * The load-bearing part is that the row set is the **union** of two things, not one:
 * the keys in `values`, and the keys whose only trace is a provenance entry carrying
 * `absent: true`. A tombstone - "this product does not have this spec" - lives in
 * `provenance` alone, by design, so a table built from `values` renders nothing at all
 * where a person made a deliberate statement of fact. It reads as the setting having
 * been lost.
 */

/** The stored shape of one value. `unit` is the registry's, copied at write time. */
export interface StoredSpecValue {
  value: SpecScalar;
  unit?: string;
}

/** The stored shape of one provenance entry. */
export interface StoredSpecProvenance {
  source?: string;
  confidence?: number;
  evidence?: string;
  /** The tombstone flag. Present and true means the value was removed on purpose. */
  absent?: boolean;
}

/** An open exception, narrowed to the two fields a row cares about. */
export interface SpecConflict {
  spec_key: string;
  reason: string;
  proposed: { value?: SpecScalar; unit?: string } | null;
}

export const CONFLICT_REASON = 'human_override_conflict';

export function buildSpecTableRows(input: {
  values: Record<string, StoredSpecValue>;
  provenance: Record<string, StoredSpecProvenance>;
  /** The registry as it stands now. A stored key missing from here renders read-only. */
  registry: SpecKeyDefinition[];
  /** Every open exception for the code. Only the conflicts are read. */
  exceptions?: SpecConflict[];
}): SpecTableRow[] {
  const { values, provenance, registry, exceptions = [] } = input;

  const byKey = new Map(registry.map((key) => [key.spec_key, key]));
  const conflicts = new Map(
    exceptions
      .filter((row) => row.reason === CONFLICT_REASON)
      .map((row) => [row.spec_key, row]),
  );

  const keys = new Set<string>(Object.keys(values ?? {}));
  for (const [key, entry] of Object.entries(provenance ?? {})) {
    if (entry?.absent) keys.add(key);
  }

  const rows: SpecTableRow[] = [];
  for (const specKey of keys) {
    const definition = byKey.get(specKey);
    const stored = values?.[specKey];
    const stamp = provenance?.[specKey];
    const conflict = conflicts.get(specKey);

    rows.push({
      specKey,
      label: definition?.label || readable(specKey),
      value: stored ? stored.value : null,
      // The registry's unit wins over the stored copy: a unit the registry has since
      // changed is a re-verification problem, not a reason to render the old suffix.
      unit: definition?.unit ?? stored?.unit ?? null,
      dataType: definition?.data_type ?? 'text',
      options: definition?.allowed_values ?? [],
      source: stamp?.source ?? null,
      evidence: stamp?.evidence ?? null,
      tombstoned: Boolean(stamp?.absent),
      unknownKey: !definition,
      conflict: conflict
        ? {
            proposed: conflict.proposed?.value ?? null,
            proposedUnit: conflict.proposed?.unit ?? null,
          }
        : null,
    });
  }

  // By label, not by key: the reader is scanning "Finish", "Height", "Width", and
  // sorting on `dim_height` puts Height between Finish and Length for no visible reason.
  return rows.sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Keys this product may carry and does not already hold, ready for the picker.
 *
 * A tombstoned key counts as held: it is on the table with a revert action, and
 * offering it again in "add a specification" would give the same key two places to be.
 */
export function keysNotYetOnProduct(
  registry: SpecKeyDefinition[],
  rows: SpecTableRow[],
): SpecKeyDefinition[] {
  const held = new Set(rows.map((row) => row.specKey));
  return registry.filter((key) => !held.has(key.spec_key));
}
