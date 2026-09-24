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
  /** One sample value, the first non-blank cell below the header (owner override, 24 Sep
   *  evening - was up to two, R5). List shape kept (length <= 1). */
  samples: string[];
  /** The resolver's current answer for this header, or null when nothing on file resolves
   *  it yet. `IGNORE_FIELD` counts as a known answer (AC-M7), never as unresolved. */
  field: string | null;
  source: 'supplier' | 'shared' | 'none';
  /** True when `field` is one of the doc type's required fields (B4's own wire shape) -
   *  not read by this component, which derives its own live "still needed" line from
   *  CURRENT picks (`unresolvedRequiredFields`) rather than this static, probe-time flag;
   *  carried on the type so a caller inspecting the raw probe sees it too. Optional so a
   *  hand-built probe (a spec fixture, e.g. this file's own tests) need not state it. */
  required?: boolean;
}

/** One pickable field the doc type's reader asks for, plus its screen label. */
export interface ImportMappingField {
  field: string;
  label: string;
}

/** One `label：value` pair found ABOVE the table's header row (or in its footer rows) -
 *  PLAN-pi-header-fields-convert-fixes-24sep.md F1/F2, R-D: the PI's own BL/container/seal
 *  block, often three pairs in one cell (DAFUYUAN), rather than a table column. `field` is
 *  the resolver's current answer, block fields only (`pi_number`, `invoice_date`, `bl_no`,
 *  `container_no`, `seal_no`, `currency`) - `consignee` is never offered (R-B: always the
 *  PI's own company, never read off the sheet). */
export interface ImportMappingHeaderField {
  row: number;
  /** The label exactly as the sheet states it (AC-F1) - never re-typed, colon included or
   *  not, whichever the sheet itself carries ("提单号" vs "Date:"). */
  label: string;
  sample: string;
  field: string | null;
  source: 'supplier' | 'shared' | 'none';
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
  /** F1/R-D: every header-block `label：value` pair this file carries, for a doc type that
   *  has such a block (proforma_invoice / packing_list). Absent for a doc type with none
   *  (`supplier_inventory`), and absent on a hand-built probe from before this field
   *  existed - the "Header fields" section below renders nothing either way. */
  header_fields?: ImportMappingHeaderField[];
  /** V2 (fix round 1, review): the "Header fields" section's OWN field choices, driven by
   *  the doc type(s) this probe was run for - the block fields (`_BLOCK_FIELDS`) that
   *  doc type's reader actually resolves, minus `consignee` (R-B: always the PI's own
   *  company, never read off the sheet) - never a hard-coded superset that offers
   *  Currency on a packing-list-only upload, which has no such field at all. A combined
   *  file's probe unions both doc types' choices. Absent on a hand-built probe from
   *  before this field existed, or a doc type with no header block at all
   *  (`supplier_inventory`) - the section then offers nothing to pick, same as before. */
  header_field_choices?: ImportMappingField[];
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
  // F2/R-D: the "Header fields" section's own picks, keyed by `${row}::${label}` (a probe
  // can carry the same label twice on different rows) - and its own fold state, independent
  // of the columns section above (F2: "same folded/open rule", not the SAME fold).
  const [headerSelections, setHeaderSelections] = useState<Record<string, string | null>>({});
  const [headerExpanded, setHeaderExpanded] = useState(true);

  const headerFields = probe.header_fields ?? [];
  const headerFieldKey = (hf: ImportMappingHeaderField) => `${hf.row}::${hf.label}`;

  /** Both sections' current picks, combined into the ONE selections array `onChange`
   *  reports (F3: "writes label -> field rows exactly like column rows, same table"). */
  const emitChange = (
    columnPicks: Record<string, string | null>,
    headerPicks: Record<string, string | null>,
  ) => {
    const columnSelections: ImportMappingSelection[] = probe.columns
      .filter((c) => columnPicks[c.header])
      .map((c) => ({ header: c.header, field: columnPicks[c.header] as string }));
    const headerFieldSelections: ImportMappingSelection[] = headerFields
      .filter((hf) => headerPicks[headerFieldKey(hf)])
      .map((hf) => ({ header: hf.label, field: headerPicks[headerFieldKey(hf)] as string }));
    onChange([...columnSelections, ...headerFieldSelections]);
  };

  useEffect(() => {
    const seeded: Record<string, string | null> = {};
    probe.columns.forEach((c) => {
      seeded[c.header] = c.field;
    });
    setSelections(seeded);
    // Expanded the moment one column is not yet known (R3); collapsed only when every
    // column already resolved BEFORE the operator touched anything.
    setExpanded(probe.columns.some((c) => c.field == null));

    const nextHeaderFields = probe.header_fields ?? [];
    const seededHeader: Record<string, string | null> = {};
    nextHeaderFields.forEach((hf) => {
      seededHeader[headerFieldKey(hf)] = hf.field;
    });
    setHeaderSelections(seededHeader);
    setHeaderExpanded(nextHeaderFields.some((hf) => hf.field == null));

    emitChange(seeded, seededHeader);
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
  const headerFieldOptions = useMemo(
    () => [{ field: IGNORE_FIELD, label: 'Ignore' }, ...(probe.header_field_choices ?? [])],
    [probe.header_field_choices],
  );
  const headerSelectOptions = useMemo(
    () => headerFieldOptions.map((f) => ({ value: f.field, label: f.label })),
    [headerFieldOptions],
  );

  const pick = (header: string, field: string) => {
    const next = { ...selections, [header]: field || null };
    setSelections(next);
    emitChange(next, headerSelections);
  };

  const pickHeaderField = (key: string, field: string) => {
    const next = { ...headerSelections, [key]: field || null };
    setHeaderSelections(next);
    emitChange(selections, next);
  };

  const total = probe.columns.length;
  const knownCount = probe.columns.filter(
    (c) => selections[c.header] != null,
  ).length;
  const allKnown = total > 0 && knownCount === total;

  const headerTotal = headerFields.length;
  const headerKnownCount = headerFields.filter(
    (hf) => headerSelections[headerFieldKey(hf)] != null,
  ).length;
  const headerAllKnown = headerTotal > 0 && headerKnownCount === headerTotal;

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
      {allKnown && !expanded ? (
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
      ) : (
        <>
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
                    title={c.samples[0] ?? ''}
                  >
                    {c.samples[0] !== undefined ? (
                      c.samples[0]
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
        </>
      )}
      {headerFields.length ? (
        <div className="space-y-2 border-t pt-2">
          <p className="text-2xs font-medium text-muted-foreground">Header fields</p>
          {headerAllKnown && !headerExpanded ? (
            <div className="flex items-center justify-between gap-2 rounded-md border border-dashed p-2 text-xs text-muted-foreground">
              <span>
                {headerTotal} of {headerTotal} header field{headerTotal === 1 ? '' : 's'} mapped
                from saved layout
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setHeaderExpanded(true)}
              >
                Review
              </Button>
            </div>
          ) : (
            <>
              <div
                className="hidden gap-2 px-1.5 text-2xs uppercase tracking-wide text-muted-foreground/70 sm:grid sm:grid-cols-[1fr_1fr_1fr]"
                aria-hidden
              >
                <span>Sample</span>
                <span>Label</span>
                <span>Field</span>
              </div>
              <div className="space-y-1.5">
                {headerFields.map((hf) => {
                  const key = headerFieldKey(hf);
                  const field = headerSelections[key] ?? null;
                  const isNew = hf.source === 'none' && !field;
                  return (
                    <div
                      key={key}
                      className={
                        'grid grid-cols-1 gap-1.5 rounded-md p-1.5 sm:grid-cols-[1fr_1fr_1fr] sm:items-center sm:gap-2' +
                        (isNew ? ' bg-primary/5 ring-1 ring-primary/20' : '')
                      }
                    >
                      <div
                        className="order-1 min-w-0 whitespace-pre-line text-xs sm:order-2"
                        title={hf.label}
                      >
                        {hf.label}
                      </div>
                      <div
                        className="order-2 min-w-0 truncate text-2xs text-muted-foreground sm:order-1"
                        title={hf.sample}
                      >
                        {hf.sample || <span className="italic">no sample</span>}
                      </div>
                      <div className="order-3 sm:order-3">
                        <SearchableSelect
                          size="sm"
                          value={field ?? ''}
                          onChange={(v: string) => pickHeaderField(key, v)}
                          options={headerSelectOptions}
                          selectedOption={
                            field
                              ? headerSelectOptions.find((o) => o.value === field)
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
            </>
          )}
        </div>
      ) : null}
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
