'use client';

import { GripVertical, X } from 'lucide-react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SpecDerivationRule } from '../types/productSpec.types';

/**
 * How a spec key is read out of a product's text.
 *
 * This is the half that used to be a Python list, which made "add a spec key" a button
 * that created a key nothing would ever fill in. Rules are tried in order and the first
 * one to match wins, so the list is a priority list - "stainless steel" has to sit
 * above "steel" or every stainless product reads as plain steel.
 *
 * Order is set by dragging. It was a pair of arrow buttons, which is a fine way to
 * nudge one row and a miserable way to move rule 31 above rule 4.
 */
const MATCH_KINDS: { value: string; label: string; hint: string }[] = [
  {
    value: 'contains',
    label: 'Text contains',
    hint: 'Whole words anywhere in the text. "S/STEEL 304" → stainless steel.',
  },
  {
    value: 'ends_with',
    label: 'Text ends with',
    hint: 'The last thing named. "SQUATTING PAN" - an earlier word describes what it is FOR.',
  },
  {
    value: 'present',
    label: 'Word is present',
    hint: 'A flag: the word appears at all. "OVER ?FLOW" → yes, it has an overflow.',
  },
  {
    value: 'regex',
    label: 'Pattern, capture a number',
    hint: 'For measurements. "(\\d+)MM S-TRAP" with capture 1 reads 150 out of "150MM S-TRAP".',
  },
  {
    value: 'code_contains',
    label: 'Product code contains',
    hint: 'Anywhere in the code. "SRTSC" matches SRTSCBD312 - for facts only the code states.',
  },
  {
    value: 'code_starts_with',
    label: 'Product code starts with',
    hint: 'The code\'s opening letters. "BRSC" matches BRSCZ002W but not ACC-BRSC.',
  },
  {
    value: 'code_suffix',
    label: 'Product code ends in',
    hint: 'The last segment of the code. "BL" matches SRTWT1234-BL.',
  },
];

const SOURCES = [
  { value: 'any', label: 'Description and flyer' },
  { value: 'description', label: 'Product description only' },
  { value: 'flyer', label: 'Flyer only' },
];

/** Reads the code, so the description/flyer choice does not apply to it. */
const READS_THE_CODE = new Set(['code_contains', 'code_starts_with', 'code_suffix']);

function SortableRule({
  rule,
  index,
  isClassKey,
  onPatch,
  onRemove,
}: {
  rule: SpecDerivationRule;
  index: number;
  isClassKey: boolean;
  onPatch: (patch: Partial<SpecDerivationRule>) => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: rule._uid ?? String(index),
  });
  const capturesNumber = rule.match === 'regex';
  const isFlag = rule.match === 'present';
  const readsCode = READS_THE_CODE.has(rule.match);

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 ${
        isDragging ? 'z-10 shadow-lg' : ''
      }`}
    >
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
      <SearchableSelect
        value={rule.match}
        onChange={(value) => onPatch({ match: value })}
        options={MATCH_KINDS.map((k) => ({ value: k.value, label: k.label }))}
        triggerClassName="w-56"
      />
      <Input
        className="min-w-[10rem] flex-1 font-mono text-xs"
        placeholder={readsCode ? 'part of the product code' : 'what to look for'}
        value={rule.pattern}
        onChange={(e) => onPatch({ pattern: e.target.value })}
      />
      {!capturesNumber && (
        <>
          <span className="text-xs text-muted-foreground">→</span>
          <Input
            className="w-40 font-mono text-xs"
            placeholder={isFlag ? 'yes' : 'value'}
            value={rule.value === undefined ? '' : String(rule.value)}
            onChange={(e) => onPatch({ value: e.target.value })}
          />
        </>
      )}
      {capturesNumber && (
        <Input
          type="number"
          min="1"
          className="w-24 text-xs"
          placeholder="capture"
          value={rule.capture ?? 1}
          onChange={(e) => onPatch({ capture: Number(e.target.value) })}
        />
      )}
      {readsCode ? (
        <span className="w-56 shrink-0 text-xs text-muted-foreground">Reads the product code</span>
      ) : isClassKey ? (
        // Class rules read a cleaned tail, never the raw description, so offering the
        // description/flyer choice here would describe something that does not happen.
        <span className="w-56 shrink-0 text-xs text-muted-foreground">
          Reads what the product IS
        </span>
      ) : (
        <SearchableSelect
          value={rule.source ?? 'any'}
          onChange={(value) => onPatch({ source: value === 'any' ? undefined : value })}
          options={SOURCES}
          triggerClassName="w-56"
        />
      )}
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
  );
}

export default function SpecRuleEditor({
  rules,
  specKey,
  onChange,
}: {
  rules: SpecDerivationRule[];
  specKey?: string;
  onChange: (rules: SpecDerivationRule[]) => void;
}) {
  const isClassKey = specKey === 'class';
  const sensors = useSensors(
    // A few pixels of travel before a drag starts, so clicking into a field on the row
    // is still a click.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const update = (index: number, patch: Partial<SpecDerivationRule>) =>
    onChange(rules.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const remove = (index: number) => onChange(rules.filter((_, i) => i !== index));

  const add = () =>
    onChange([
      ...rules,
      { _uid: `new-${Date.now()}-${rules.length}`, match: 'contains', pattern: '', value: '' },
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
