'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';

/**
 * Shared inline column mapper (PLAN-import-column-mapper-24sep.md F1, R4): sample data |
 * header text | field select, over a header PROBE the caller already fetched. One
 * component so "Plan a container" and "Upload supplier documents" - and any later
 * supplier-file upload - map a header the same way, in the same place the file is dropped,
 * rather than a separate admin page (the whole point of this lane, see the plan's "What
 * the owner asked").
 *
 * Reserved field `IGNORE_FIELD` = "a column the operator has looked at and decided means
 * nothing" (grill G2, AC-M7). It is a SAVED choice like any other pick, so `序号` / `图片`
 * do not put the mapper back in front of the operator on every later upload of the same
 * layout (ruling R3, AC-M11).
 *
 * Stateful on purpose: the mapper owns "what has the operator picked so far" between the
 * probe landing and Test being pressed, and decides its own collapsed/expanded state
 * (R3/AC-M11/AC-M12). A new `probe` (a new file, or the header-row stepper moving) reseeds
 * both from scratch - a pick made against the PREVIOUS file's columns must never survive
 * onto this one.
 */

export const IGNORE_FIELD = 'ignore';

/** One column of the probed table, as the mapping endpoint (B4) states it. */
export interface ImportMappingColumn {
  position: number;
  /** The full header text, line breaks and all - never re-typed, never truncated. */
  header: string;
  /** Up to two sample values, first non-blank cells below the header (R5). */
  samples: string[];
  /** The resolver's current answer for this header, or null when nothing on file resolves
   *  it yet. `IGNORE_FIELD` counts as a known answer (AC-M7), never as unresolved. */
  field: string | null;
  source: 'supplier' | 'shared' | 'none';
  /** True when `field` is one of the doc type's required fields (B4's own wire shape) -
   *  not read by this component, which derives its own live "still needed" line from
   *  CURRENT picks (`unresolvedRequiredFields`) rather than this static, probe-time flag;
   *  carried on the type so a caller inspecting the raw probe sees it too. Optional so a
   *  hand-built probe (a spec, `buildMockProbe`) need not state it. */
  required?: boolean;
}

/** One pickable field the doc type's reader asks for, plus its screen label. */
export interface ImportMappingField {
  field: string;
  label: string;
}

/** What `POST .../import-mapping/probe` (B4) answers for one file. `header_row` is null
 *  when no row satisfied the heuristic (AC-M16) - the stepper still has to start
 *  somewhere, and row 1 is that starting point, not a guess dressed up as one. */
export interface ImportMappingProbe {
  header_row: number | null;
  columns: ImportMappingColumn[];
  /** Canonical field names the doc type cannot be read without - drives the "required"
   *  badge and the caller's own Test-disabled reason (AC-M9), never a per-column flag: a
   *  required field can be satisfied by ANY column, not a fixed one. */
  required_fields: string[];
  /** `required_fields` not yet resolved BY ANY COLUMN, as the probe found them - B4's own
   *  wire shape. Optional (a hand-built probe need not state it): this component always
   *  recomputes its live "still needed" line from current picks instead
   *  (`unresolvedRequiredFields`), since a probe-time snapshot goes stale the moment the
   *  operator picks a field. */
  missing_required?: string[];
  /** The sheet's own last row number (review round 1, item 12) - the stepper's ceiling.
   *  Optional (a hand-built probe need not state it): absent, the stepper has no ceiling,
   *  same as before this field existed. */
  row_count?: number;
}

/** One header's pick, in the shape `onChange` reports it and `save` (B5) takes it -
 *  `field` is `IGNORE_FIELD` for an ignored column, never omitted: Ignore is a saved
 *  choice, not an absence (G2). */
export interface ImportMappingSelection {
  header: string;
  field: string;
}

/** Required fields with no current pick, by field name - what a caller (the upload
 *  dialogs) names in a disabled Test button's `title` (AC-M9). Exported so neither dialog
 *  re-derives this from `selections` its own way. */
export function unresolvedRequiredFields(
  probe: ImportMappingProbe,
  selections: ImportMappingSelection[],
): string[] {
  const picked = new Set(selections.map((s) => s.field));
  return probe.required_fields.filter((f) => !picked.has(f));
}

export function ImportColumnMapper({
  probe,
  fields,
  onChange,
  onHeaderRowChange,
  busy = false,
}: {
  probe: ImportMappingProbe;
  /** The field list to offer for this doc type (or the UNION of two, for a combined file,
   *  G4) - Ignore is added by this component, so no caller has to remember it. */
  fields: ImportMappingField[];
  /** Fires on every pick AND once whenever `probe` changes, so a caller reading Test's
   *  eligibility off the latest selection never needs a first interaction to get one. */
  onChange: (mappings: ImportMappingSelection[]) => void;
  onHeaderRowChange: (row: number) => void;
  busy?: boolean;
}) {
  const [selections, setSelections] = useState<Record<string, string | null>>(
    {},
  );
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    const seeded: Record<string, string | null> = {};
    probe.columns.forEach((c) => {
      seeded[c.header] = c.field;
    });
    setSelections(seeded);
    // Expanded the moment one column is not yet known (R3); collapsed only when every
    // column already resolved BEFORE the operator touched anything.
    setExpanded(probe.columns.some((c) => c.field == null));
    onChange(
      probe.columns
        .filter((c) => c.field != null)
        .map((c) => ({ header: c.header, field: c.field as string })),
    );
    // Only the probe identity should reseed - `onChange` is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probe]);

  const fieldOptions = useMemo(
    () => [{ field: IGNORE_FIELD, label: 'Ignore' }, ...fields],
    [fields],
  );
  const selectOptions = useMemo(
    () => fieldOptions.map((f) => ({ value: f.field, label: f.label })),
    [fieldOptions],
  );

  const pick = (header: string, field: string) => {
    const next = { ...selections, [header]: field || null };
    setSelections(next);
    onChange(
      probe.columns
        .filter((c) => next[c.header])
        .map((c) => ({ header: c.header, field: next[c.header] as string })),
    );
  };

  const total = probe.columns.length;
  const knownCount = probe.columns.filter(
    (c) => selections[c.header] != null,
  ).length;
  const allKnown = total > 0 && knownCount === total;

  if (allKnown && !expanded) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border border-dashed p-2 text-xs text-muted-foreground">
        <span>
          {total} of {total} column{total === 1 ? '' : 's'} mapped from saved
          layout
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setExpanded(true)}
        >
          Review
        </Button>
      </div>
    );
  }

  const currentSelections: ImportMappingSelection[] = probe.columns
    .filter((c) => selections[c.header])
    .map((c) => ({ header: c.header, field: selections[c.header] as string }));
  const missingRequired = unresolvedRequiredFields(probe, currentSelections);
  const requiredLabel = (field: string) =>
    fieldOptions.find((f) => f.field === field)?.label ?? field;

  return (
    <div className="space-y-2 rounded-md border p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <HeaderRowStepper
          row={probe.header_row}
          maxRow={probe.row_count}
          onChange={onHeaderRowChange}
          disabled={busy}
        />
        {missingRequired.length ? (
          <p className="flex items-center gap-1.5 text-2xs text-destructive">
            <TriangleAlert className="size-3.5 shrink-0" />
            Still needed: {missingRequired.map(requiredLabel).join(', ')}
          </p>
        ) : null}
      </div>
      {probe.header_row == null ? (
        <p className="flex items-center gap-1.5 text-2xs text-destructive">
          <TriangleAlert className="size-3.5 shrink-0" />
          No header row was found.
        </p>
      ) : null}
      {probe.columns.length ? (
        <div
          className="hidden gap-2 px-1.5 text-2xs uppercase tracking-wide text-muted-foreground/70 sm:grid sm:grid-cols-[1fr_1fr_1fr]"
          aria-hidden
        >
          <span>Sample</span>
          <span>Column</span>
          <span>Field</span>
        </div>
      ) : null}
      <div className="space-y-1.5">
        {probe.columns.map((c) => {
          const field = selections[c.header] ?? null;
          // A column this supplier has never mapped before stands out among otherwise
          // pre-filled columns (AC-M12) - `source: 'none'` is exactly that - UNTIL the
          // operator gives it a pick IN THIS SAME SESSION: the highlight means "you have
          // never decided this one", and it has to stop the moment that stops being true,
          // not stay keyed off the probe's own immutable snapshot (review round 1).
          const isNew = c.source === 'none' && !field;
          return (
            <div
              key={`${c.position}-${c.header}`}
              className={
                'grid grid-cols-1 gap-1.5 rounded-md p-1.5 sm:grid-cols-[1fr_1fr_1fr] sm:items-center sm:gap-2' +
                (isNew ? ' bg-primary/5 ring-1 ring-primary/20' : '')
              }
            >
              {/* Mobile (< 640px, review round 1 item 18): stacked in READING order - the
                  column's own name first, then its sample data, then the pick. Desktop
                  (>= 640px) keeps the Sample | Column | Field order the header row above
                  names, via the `sm:order-*` overrides below. */}
              <div
                className="order-1 min-w-0 whitespace-pre-line text-xs sm:order-2"
                title={c.header}
              >
                {c.header}
              </div>
              <div
                className="order-2 min-w-0 truncate text-2xs text-muted-foreground sm:order-1"
                title={c.samples.join(' · ')}
              >
                {c.samples.length ? (
                  c.samples.join(' · ')
                ) : (
                  <span className="italic">no sample</span>
                )}
              </div>
              <div className="order-3 sm:order-3">
                <SearchableSelect
                  size="sm"
                  value={field ?? ''}
                  onChange={(v: string) => pick(c.header, v)}
                  options={selectOptions}
                  selectedOption={
                    field
                      ? selectOptions.find((o) => o.value === field)
                      : undefined
                  }
                  placeholder="Choose a field"
                  clearable
                  disabled={busy}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** "Header row N" plus a stepper (grill G3: the guess may be wrong, so moving it is a
 *  plain up/down rather than a click-the-row preview). Starts at row 1 when the probe
 *  found none (AC-M16). */
function HeaderRowStepper({
  row,
  maxRow,
  onChange,
  disabled,
}: {
  row: number | null;
  /** The sheet's own last row number (review round 1, item 12) - "move down" has nowhere
   *  useful to go past it. Optional/absent (a caller with no probe yet, or an older probe
   *  shape) leaves the ceiling off, same as before this bound existed. */
  maxRow?: number;
  onChange: (next: number) => void;
  disabled: boolean;
}) {
  const current = row ?? 1;
  const atCeiling = maxRow != null && maxRow > 0 && current >= maxRow;
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="font-medium">Header row {current}</span>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-6"
        disabled={disabled || current <= 1}
        onClick={() => onChange(current - 1)}
        aria-label="Move header row up"
      >
        <ChevronUp className="size-3.5" />
      </Button>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-6"
        disabled={disabled || atCeiling}
        onClick={() => onChange(current + 1)}
        aria-label="Move header row down"
      >
        <ChevronDown className="size-3.5" />
      </Button>
    </div>
  );
}

export default ImportColumnMapper;
