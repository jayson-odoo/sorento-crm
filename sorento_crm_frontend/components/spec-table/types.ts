/**
 * The shapes the editable spec table is handed, and the shapes it hands back.
 *
 * Deliberately free of every backend type in `productSpec.types.ts`. This folder is
 * imported by the product page today and by the supplier portal in milestone 2, and the
 * portal sits in the `(auth)` route group with a different service layer and a different
 * principal. A component that knew `ProductSpecDetail` would drag that whole module in.
 */

/** Everything a spec value is allowed to be, matching the stored JSON. */
export type SpecScalar = string | number | boolean;

/** One key as the registry defines it, with its vocabulary already merged. */
export interface SpecKeyDefinition {
  spec_key: string;
  label: string;
  /** text | numeric | boolean - anything else falls through to a typed input. */
  data_type: string;
  unit: string | null;
  /** Seed values plus staff-added ones, minus suppressed. Empty means free text. */
  allowed_values: string[];
  /**
   * Merged customer phrasings per value. Read only to answer "is this word already
   * here under another name" before offering to add it - `matte black` ships as a word
   * for `black`, so adding it as a value of its own would create one nothing can match.
   */
  synonyms?: Record<string, string[]>;
}

/**
 * One row of the table: a key this product carries, or one it was told it does not.
 *
 * Built by `buildSpecTableRows` rather than by the caller, because the union of
 * `values` and the tombstones hiding in `provenance` is the part everybody gets wrong.
 */
export interface SpecTableRow {
  specKey: string;
  label: string;
  /** Null when the row is a tombstone: there is no value, and that is the point. */
  value: SpecScalar | null;
  unit: string | null;
  dataType: string;
  /** Merged vocabulary. Empty means this key takes free text. */
  options: string[];
  /** derived | flyer | code | category | human | supplier, or null when unstamped. */
  source: string | null;
  /** The exact words the value was read from, or the audit stamp for an authored one. */
  evidence: string | null;
  /** The person said this product does not have this spec. Survives re-derivation. */
  tombstoned: boolean;
  /** Stored on the row but no longer in the registry: shown, never edited. */
  unknownKey: boolean;
  /**
   * An open `human_override_conflict`: the rules now read something else and the
   * authored value is holding. Setting the right value is what answers it - there is
   * no separate resolve action.
   */
  conflict: { proposed: SpecScalar | null; proposedUnit: string | null } | null;
}

/** What the table can be asked to do. Every one of them is the caller's to perform. */
export interface SpecTableCallbacks {
  /** Save a value as authored. Rejecting the promise leaves the row in edit. */
  onSetValue: (specKey: string, value: SpecScalar) => Promise<void>;
  /** "This product does not have this spec" - a tombstone that survives re-derivation. */
  onTombstone: (specKey: string) => Promise<void>;
  /** "Use what the rules read" - hand the key back to derivation. */
  onRevert: (specKey: string) => Promise<void>;
  /**
   * The typed word is not in the key's vocabulary. Adding it is a registry edit, so it
   * is the caller's call whether the user may make one - omit to hide the offer.
   */
  onAddValueToKey?: (specKey: string, value: string) => Promise<void>;
  /** Open the add-a-specification picker. Omit to hide the CTA entirely. */
  onAddSpecification?: () => void;
}
