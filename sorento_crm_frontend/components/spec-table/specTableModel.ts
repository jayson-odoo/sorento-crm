import { readable } from '@/lib/spec-readable';
import type { SpecKeyDefinition, SpecScalar, SpecTableRow } from './types';

/**
 * Turn one product's stored specs into the rows a person reads.
 *
 * A row is a key with a value, and nothing else. A removed key keeps a tombstone in
 * `provenance` (`absent: true`) so re-derivation will not fill it back in, but that is
 * the server's business: on screen, removed means gone (captain's call). The way back
 * is the add picker, and setting a value there replaces the tombstone wholesale.
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
  /** The tombstone flag. Present and true means the key was removed on purpose. */
  absent?: boolean;
  /**
   * Where an authored value came from before it was authored.
   *
   * `flyer` on the 3,351 (re-measured 2026-08-16) entries the promote migration
   * re-stamped: the flyer stopped being something derivation reads, so its values
   * became authored ones rather than disappearing on the next run (D2). Carried so a
   * person can tell why a value they never typed says "Set by hand" (AC-B.15).
   */
  migrated_from?: string;
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

  const rows: SpecTableRow[] = [];
  for (const [specKey, stored] of Object.entries(values ?? {})) {
    const definition = byKey.get(specKey);
    const stamp = provenance?.[specKey];
    const conflict = conflicts.get(specKey);

    rows.push({
      specKey,
      label: definition?.label || readable(specKey),
      value: stored.value,
      // The registry's unit wins over the stored copy: a unit the registry has since
      // changed is a re-verification problem, not a reason to render the old suffix.
      unit: definition?.unit ?? stored.unit ?? null,
      dataType: definition?.data_type ?? 'text',
      options: definition?.allowed_values ?? [],
      source: stamp?.source ?? null,
      migratedFrom: stamp?.migrated_from ?? null,
      evidence: stamp?.evidence ?? null,
      unknownKey: !definition,
      valueLabels: definition?.value_labels ?? {},
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
