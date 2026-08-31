'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, GripVertical, X } from 'lucide-react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  restrictToParentElement,
  restrictToVerticalAxis,
} from '@dnd-kit/modifiers';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { compileBuilder } from '../lib/ruleSentence';
import type {
  SpecDerivationRule,
  SpecRuleBuilder,
  SpecRuleBuilderKind,
  SpecTryRuleRead,
} from '../types/productSpec.types';

/**
 * How a spec key is read out of a product's text.
 *
 * Every row is a sentence with blanks (AC-C.1): the kind menu picks the sentence, the
 * blanks are filled in, and what gets saved is compiled from them - the same compile
 * Advanced shows under the row. A row with no `builder` is one somebody dropped into
 * Advanced and pressed "Edit pattern" on; it is the only place raw regex shows by
 * default (AC-C.2), and there is no way back to a sentence from there.
 *
 * Order is set by dragging, same as before - it is a priority list, so "stainless
 * steel" has to sit above "steel" or every stainless product reads as plain steel.
 */
const SENTENCE_KIND_OPTIONS: { value: SpecRuleBuilderKind; label: string }[] = [
  { value: 'number_after', label: 'Number after a word' },
  { value: 'number_before', label: 'Number before a word' },
  { value: 'number_between', label: 'Number between two words' },
  { value: 'text_contains', label: 'Text contains...' },
  { value: 'text_ends_with', label: 'Text ends with...' },
  { value: 'word_present', label: 'Word is present' },
  { value: 'code_contains', label: 'Code contains...' },
  { value: 'code_starts_with', label: 'Code starts with...' },
  { value: 'code_ends_with', label: 'Code ends with...' },
  { value: 'from_field', label: "From the product's own field" },
  { value: 'size_triple', label: 'Size from L x W x H' },
  { value: 'name_head', label: 'Product name head' },
];

// The whitelist `from_field_choices()` enforces server-side (B3): `category`,
// `brand`, or a numeric `Product` column. Offered here rather than a free-text box
// for the SAME reason the server refuses anything else - `from_field
// column:currency` used to crash derivation for the whole catalogue, because
// nothing checked the column existed, let alone that it held a number.
const FROM_FIELD_OPTIONS = [
  { value: 'category', label: "the product's category" },
  { value: 'brand', label: "the product's brand field" },
  {
    value: 'column:dimensions_length',
    label: 'the `dimensions_length` column',
  },
  { value: 'column:dimensions_width', label: 'the `dimensions_width` column' },
  {
    value: 'column:dimensions_height',
    label: 'the `dimensions_height` column',
  },
  { value: 'column:weight', label: 'the `weight` column' },
  { value: 'column:list_price', label: 'the `list_price` column' },
  { value: 'column:cost_price', label: 'the `cost_price` column' },
  { value: 'column:invoice_price', label: 'the `invoice_price` column' },
  { value: 'column:warranty_months', label: 'the `warranty_months` column' },
  { value: 'column:reorder_level', label: 'the `reorder_level` column' },
  { value: 'column:reorder_quantity', label: 'the `reorder_quantity` column' },
];

const SIZE_POSITION_OPTIONS = [
  { value: '1', label: '1st (length)' },
  { value: '2', label: '2nd (width)' },
  { value: '3', label: '3rd (height)' },
  { value: '4', label: '4th (thickness)' },
];

const SOURCES = [
  { value: 'any', label: 'Description and flyer' },
  { value: 'description', label: 'Product description only' },
  { value: 'flyer', label: 'Flyer only' },
  // The two texts derivation builds FROM the description, so a shipped row can be
  // scoped to one without it ever meaning "read the flyer" (S6): the shipped
  // `dim_length` lone-size row is `source: "size_text"` and every `class` rule
  // defaults to `class_tail`. Without an option for them the select rendered blank
  // for a row already carrying a valid scope, and picking anything on it silently
  // rewrote that scope out from under the row.
  {
    value: 'size_text',
    label: 'the description, sizes only (trap span ignored)',
  },
  { value: 'class_tail', label: 'the product name tail' },
];

function defaultBuilderFor(kind: SpecRuleBuilderKind): SpecRuleBuilder {
  switch (kind) {
    case 'number_after':
    case 'number_before':
    case 'word_present':
      return { kind, word: '' };
    case 'number_between':
      return { kind, from: '', to: '' };
    case 'text_contains':
    case 'text_ends_with':
    case 'code_contains':
    case 'code_starts_with':
    case 'code_ends_with':
      return { kind, word: '', value: '' };
    case 'from_field':
      return { kind, field: 'category' };
    case 'size_triple':
      return { kind, position: 1 };
    case 'name_head':
      return { kind };
    default:
      return { kind };
  }
}

/** Compile the builder into the row's saved fields, so `match`/`pattern`/`capture`/
 *  `value` are never stale relative to what the sentence says - true whether the row
 *  is about to be saved or tried against a product this instant.
 *
 *  The four engine fields are explicitly cleared FIRST, then overwritten by whatever
 *  this compile actually produced (B2): `update()` merges the patch with `{...r,
 *  ...patch}`, and a patch that simply omitted `value` would leave a PREVIOUS kind's
 *  value sitting on the row - Text contains `PP SEAT` -> Number after a word kept
 *  `value: "PP"` next to a `\bL\s*(\d+...)` pattern that never produces one, and the
 *  server's builder/pattern comparison refused the save as a mismatch. Explicitly
 *  `undefined` here means the spread below actually overwrites the key rather than
 *  skipping it, and `JSON.stringify` drops an `undefined` value on the way out. */
function withCompiled(builder: SpecRuleBuilder): Partial<SpecDerivationRule> {
  return {
    builder,
    // `match`/`pattern` are not pre-cleared: `compileBuilder` always returns both
    // (every branch, including its `default`), so TypeScript rightly flags setting
    // them here as dead - the spread below overwrites them unconditionally either
    // way. `capture`/`value` are NOT always returned (`text_contains` has no
    // `capture`, `number_after` has no `value`), which is the actual bug: clearing
    // them first is what stops a previous kind's leftovers surviving the merge.
    capture: undefined,
    value: undefined,
    ...compileBuilder(builder),
  };
}

/** "300 from `S-TRAP 300MM`" / "nothing". What a rule reads out of the try-it source. */
function readResultText(read: SpecTryRuleRead | null | undefined): string {
  if (!read) return 'nothing';
  if (read.value === null || read.value === undefined) {
    // A capped-and-dropped reading still carries an explanation ("540 from
    // (540MM) (above 5000, ignored)") - showing bare "nothing" would hide why the
    // row did not win. A row that truly found nothing has no evidence, so this
    // still reads as "nothing" for it.
    return read.evidence || 'nothing';
  }
  const value =
    typeof read.value === 'boolean'
      ? read.value
        ? 'yes'
        : 'no'
      : String(read.value);
  return read.evidence ? `${value} from \`${read.evidence}\`` : value;
}

/** One inline blank in a sentence row: a labelled text box sized to its content. */
function Blank({
  value,
  onChange,
  placeholder,
  width = 'w-32',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  width?: string;
}) {
  return (
    <Input
      className={`${width} font-mono text-xs`}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function BuilderRowBody({
  builder,
  onPatch,
}: {
  builder: SpecRuleBuilder;
  onPatch: (patch: Partial<SpecRuleBuilder>) => void;
}) {
  switch (builder.kind) {
    case 'number_after':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          Number after the word
          <Blank
            value={builder.word ?? ''}
            onChange={(word) => onPatch({ word })}
            placeholder="e.g. L"
          />
        </span>
      );
    case 'number_before':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          Number before
          <Blank
            value={builder.word ?? ''}
            onChange={(word) => onPatch({ word })}
            placeholder="e.g. MM"
          />
        </span>
      );
    case 'number_between':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          Number between
          <Blank
            value={builder.from ?? ''}
            onChange={(from) => onPatch({ from })}
            placeholder="e.g. S-TRAP"
          />
          and
          <Blank
            value={builder.to ?? ''}
            onChange={(to) => onPatch({ to })}
            placeholder="e.g. MM"
          />
        </span>
      );
    case 'text_contains':
    case 'text_ends_with':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          {builder.kind === 'text_contains'
            ? 'Text contains'
            : 'Text ends with'}
          <Blank
            value={builder.word ?? ''}
            onChange={(word) => onPatch({ word })}
            placeholder="e.g. RIMLESS"
          />
          <span className="text-muted-foreground">→</span>
          <Blank
            value={builder.value === undefined ? '' : String(builder.value)}
            onChange={(value) => onPatch({ value })}
            placeholder="yes"
          />
        </span>
      );
    case 'word_present':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          Word
          <Blank
            value={builder.word ?? ''}
            onChange={(word) => onPatch({ word })}
            placeholder="e.g. THERMOSTATIC"
          />
          is present → yes
        </span>
      );
    case 'code_contains':
    case 'code_starts_with':
    case 'code_ends_with': {
      const label =
        builder.kind === 'code_contains'
          ? 'Code contains'
          : builder.kind === 'code_starts_with'
            ? 'Code starts with'
            : 'Code ends with';
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          {label}
          <Blank
            value={builder.word ?? ''}
            onChange={(word) => onPatch({ word })}
            placeholder="e.g. -UF"
          />
          <span className="text-muted-foreground">→</span>
          <Blank
            value={builder.value === undefined ? '' : String(builder.value)}
            onChange={(value) => onPatch({ value })}
            placeholder="e.g. UF"
          />
        </span>
      );
    }
    case 'from_field':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          From
          <SearchableSelect
            value={builder.field ?? 'category'}
            onChange={(field) => onPatch({ field })}
            options={FROM_FIELD_OPTIONS}
            triggerClassName="w-56"
            size="sm"
          />
        </span>
      );
    case 'size_triple':
      return (
        <span className="flex flex-wrap items-center gap-1.5 text-sm">
          Size from <code className="font-mono">L x W x H</code>, take the
          <SearchableSelect
            value={String(builder.position ?? 1)}
            onChange={(position) => onPatch({ position: Number(position) })}
            options={SIZE_POSITION_OPTIONS}
            triggerClassName="w-32"
            size="sm"
          />
          number
        </span>
      );
    case 'name_head':
      return (
        <span className="text-sm">
          Product name head (text before the first bracket or WITH)
        </span>
      );
    default:
      return null;
  }
}

function SortableRule({
  rule,
  index,
  isClassKey,
  readResult,
  isWinner,
  onPatch,
  onRemove,
}: {
  rule: SpecDerivationRule;
  index: number;
  isClassKey: boolean;
  readResult?: SpecTryRuleRead | null;
  isWinner?: boolean;
  onPatch: (patch: Partial<SpecDerivationRule>) => void;
  onRemove: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: rule._uid ?? String(index),
  });
  const [advanced, setAdvanced] = useState(false);
  const shipped = rule.shipped || rule.shipped_backfill;
  const readsCode = rule.builder
    ? ['code_contains', 'code_starts_with', 'code_ends_with'].includes(
        rule.builder.kind,
      )
    : ['code_contains', 'code_starts_with', 'code_suffix'].includes(rule.match);

  const patchBuilder = (patch: Partial<SpecRuleBuilder>) => {
    if (!rule.builder) return;
    onPatch(withCompiled({ ...rule.builder, ...patch }));
  };

  const changeKind = (kind: string) => {
    onPatch(withCompiled(defaultBuilderFor(kind as SpecRuleBuilderKind)));
  };

  const editPattern = () => {
    // Drops the builder; `match`/`pattern`/`capture`/`value` are already the compiled
    // form (kept in sync on every patch), so nothing about how the rule runs changes.
    onPatch({ builder: undefined });
    setAdvanced(false);
  };

  const compiled = rule.builder ? compileBuilder(rule.builder) : rule;
  const isPatternCapture =
    !rule.builder && rule.match === 'regex' && rule.capture !== undefined;
  // A `from_field` row somebody dropped into Advanced and pressed "Edit pattern" on
  // still has to stay inside the whitelist (B3) - a free-text `pattern` box let
  // `column:currency` through, and the server's own guard is the only thing that
  // then stood between it and a crashed catalogue-wide derivation.
  const isBareFromField = !rule.builder && rule.match === 'from_field';

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex flex-col gap-2 rounded-md border bg-background p-2 ${
        isDragging ? 'z-10 shadow-lg' : ''
      } ${isWinner ? 'border-primary ring-1 ring-primary' : ''}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="cursor-grab rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground active:cursor-grabbing"
          aria-label={`Reorder rule ${index + 1}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </button>
        <span className="w-6 shrink-0 text-center font-mono text-xs text-muted-foreground">
          {index + 1}
        </span>

        {shipped && (
          <Badge
            variant="secondary"
            appearance="light"
            size="sm"
            className="shrink-0"
          >
            shipped
          </Badge>
        )}
        {isWinner && (
          <Badge
            variant="primary"
            appearance="light"
            size="sm"
            className="shrink-0"
          >
            winner
          </Badge>
        )}

        {rule.builder ? (
          <SearchableSelect
            value={rule.builder.kind}
            onChange={changeKind}
            options={SENTENCE_KIND_OPTIONS}
            triggerClassName="w-56"
            size="sm"
          />
        ) : null}

        <div className="min-w-[14rem] flex-1">
          {rule.builder ? (
            <BuilderRowBody builder={rule.builder} onPatch={patchBuilder} />
          ) : isBareFromField ? (
            <span className="flex flex-wrap items-center gap-1.5 text-sm">
              From
              <SearchableSelect
                value={rule.pattern}
                onChange={(pattern) => onPatch({ pattern })}
                options={FROM_FIELD_OPTIONS}
                triggerClassName="w-56"
                size="sm"
              />
            </span>
          ) : isPatternCapture ? (
            <span className="flex flex-wrap items-center gap-1.5 text-sm">
              Pattern
              <Input
                className="min-w-[10rem] flex-1 font-mono text-xs"
                value={rule.pattern}
                onChange={(e) => onPatch({ pattern: e.target.value })}
              />
              , capture the
              <Input
                type="number"
                min="1"
                className="w-16 text-xs"
                value={rule.capture ?? 1}
                onChange={(e) => onPatch({ capture: Number(e.target.value) })}
              />
              number
            </span>
          ) : (
            <span className="flex flex-wrap items-center gap-1.5 text-sm">
              Pattern
              <Input
                className="min-w-[10rem] flex-1 font-mono text-xs"
                value={rule.pattern}
                onChange={(e) => onPatch({ pattern: e.target.value })}
              />
              <span className="text-muted-foreground">→</span>
              <Input
                className="w-32 font-mono text-xs"
                value={rule.value === undefined ? '' : String(rule.value)}
                onChange={(e) => onPatch({ value: e.target.value })}
              />
            </span>
          )}
        </div>

        {!readsCode && !isClassKey && (
          <SearchableSelect
            value={rule.source ?? 'any'}
            onChange={(value) =>
              onPatch({ source: value === 'any' ? undefined : value })
            }
            options={SOURCES}
            triggerClassName="w-52"
            size="sm"
          />
        )}

        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="text-muted-foreground"
          onClick={() => setAdvanced((v) => !v)}
        >
          {advanced ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
          Advanced
        </Button>

        <Button
          size="icon"
          variant="ghost"
          className="ml-auto text-muted-foreground hover:text-destructive"
          onClick={onRemove}
          aria-label={`Remove rule ${index + 1}`}
        >
          <X className="size-4" />
        </Button>
      </div>

      {readResult !== undefined && (
        <div className="ml-8 text-xs text-muted-foreground">
          Reads: <span className="font-mono">{readResultText(readResult)}</span>
        </div>
      )}

      {advanced && (
        <div className="ml-8 flex flex-col gap-1.5 rounded-md border bg-muted/30 p-2">
          <div className="font-mono text-xs text-muted-foreground break-all">
            {compiled.pattern || '(nothing yet)'}
            {compiled.capture !== undefined
              ? ` - capture ${compiled.capture}`
              : ''}
          </div>
          {rule.builder && (
            <Button
              size="sm"
              variant="outline"
              className="w-fit"
              onClick={editPattern}
            >
              Edit pattern
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export default function SpecRuleEditor({
  rules,
  specKey,
  onChange,
  reads,
  winnerIndex,
}: {
  rules: SpecDerivationRule[];
  specKey?: string;
  onChange: (rules: SpecDerivationRule[]) => void;
  /** Per-row try-it reads, aligned to `rules` by index (AC-B.3). Absent (not just
   *  empty) when no try-it source is picked, so rows render with no read line at all
   *  rather than "nothing" for a question nobody asked. */
  reads?: SpecTryRuleRead[] | null;
  winnerIndex?: number | null;
}) {
  const isClassKey = specKey === 'class';
  const sensors = useSensors(
    // A few pixels of travel before a drag starts, so clicking into a field on the row
    // is still a click.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const update = (index: number, patch: Partial<SpecDerivationRule>) =>
    onChange(rules.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const remove = (index: number) =>
    onChange(rules.filter((_, i) => i !== index));

  const add = () =>
    onChange([
      ...rules,
      {
        _uid: `new-${Date.now()}-${rules.length}`,
        ...withCompiled(defaultBuilderFor('text_contains')),
      } as SpecDerivationRule,
    ]);

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = rules.findIndex((r, i) => (r._uid ?? String(i)) === active.id);
    const to = rules.findIndex((r, i) => (r._uid ?? String(i)) === over.id);
    if (from < 0 || to < 0) return;
    onChange(arrayMove(rules, from, to));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        How this is read from a product
      </div>

      {rules.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No rules yet, so nothing will ever fill this in. Add one below.
        </p>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        modifiers={[restrictToVerticalAxis, restrictToParentElement]}
        onDragEnd={onDragEnd}
      >
        <SortableContext
          items={rules.map((r, i) => r._uid ?? String(i))}
          strategy={verticalListSortingStrategy}
        >
          <div className="flex flex-col gap-2">
            {rules.map((rule, index) => (
              <SortableRule
                key={rule._uid ?? index}
                rule={rule}
                index={index}
                isClassKey={isClassKey}
                readResult={reads ? (reads[index] ?? null) : undefined}
                isWinner={winnerIndex === index}
                onPatch={(patch) => update(index, patch)}
                onRemove={() => remove(index)}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div>
        <Button size="sm" variant="outline" onClick={add}>
          Add a rule
        </Button>
      </div>
    </div>
  );
}
