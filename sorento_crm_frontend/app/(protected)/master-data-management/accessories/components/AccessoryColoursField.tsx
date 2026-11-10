'use client';

import { useRef, useState } from 'react';
import { GripVertical, Plus, X } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { ColorPicker } from '@/components/common/ColorPicker';
import type { AccessoryColour } from '../types/accessory.types';

/** Names offered as the placeholder when a colour has none and its hex is one of these. */
const PRESET_NAMES: Record<string, string> = {
  '#1f2937': 'Black',
  '#9ca3af': 'Grey',
  '#c0c0c0': 'Silver',
  '#ffffff': 'White',
  '#d4af37': 'Gold',
  '#2c3539': 'Gunmetal',
};
const DEFAULT_HEX = '#1f2937';

/** What the picker may hand back, as a stored hex: `#rgb` expanded, lower case; null for anything else
 *  (Transparent, half-typed text), which a colour dot cannot be. */
export function normaliseHex(value: string): string | null {
  const v = value.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(v)) return v;
  if (/^#[0-9a-f]{3}$/.test(v)) return `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}`;
  return null;
}

/** The first preset colour the list does not use yet, else Black (validation says what is wrong). */
function nextDefaultHex(colours: AccessoryColour[]): string {
  const used = new Set(colours.map((c) => c.hex.toLowerCase()));
  return Object.keys(PRESET_NAMES).find((hex) => !used.has(hex)) ?? DEFAULT_HEX;
}
const MAX_COLOURS = 12;

export const presetNameOf = (hex: string): string => PRESET_NAMES[hex.toLowerCase()] ?? '';

function ColourRow({
  id,
  index,
  colour,
  canEdit,
  onChange,
  onRemove,
}: {
  id: string;
  index: number;
  colour: AccessoryColour;
  canEdit: boolean;
  onChange: (next: AccessoryColour) => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const shown = colour.name || presetNameOf(colour.hex);
  // A value the list cannot hold (Transparent) is refused; the picker is reopened on the old colour.
  const [reset, setReset] = useState(0);
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 ${isDragging ? 'z-10 shadow-md' : ''}`}
    >
      {canEdit ? (
        <>
          <button
            type="button"
            className="shrink-0 cursor-grab touch-none text-muted-foreground"
            aria-label={`Reorder colour ${index + 1}`}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-4" />
          </button>
          <ColorPicker
            key={reset}
            value={colour.hex}
            ariaLabel={`Colour ${index + 1}`}
            onChange={(picked) => {
              const hex = normaliseHex(picked);
              if (hex) onChange({ ...colour, hex });
              else setReset((n) => n + 1);
            }}
          />
          <Input
            aria-label={`Colour name ${index + 1}`}
            className="order-last h-8 min-w-0 basis-full sm:order-none sm:basis-0 sm:flex-1"
            maxLength={40}
            placeholder={presetNameOf(colour.hex)}
            value={colour.name ?? ''}
            onChange={(e) => onChange({ ...colour, name: e.target.value || null })}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto shrink-0 sm:ml-0"
            aria-label={`Remove colour ${index + 1}`}
            onClick={onRemove}
          >
            <X className="size-4" />
          </Button>
        </>
      ) : (
        <>
          <span
            className="size-6 shrink-0 rounded-full border"
            style={{ backgroundColor: colour.hex }}
            title={colour.hex}
          />
          <span className="text-sm">{shown || colour.hex}</span>
        </>
      )}
    </li>
  );
}

/**
 * An accessory's colours: an ordered list of their own, independent of its pictures (one dot per colour on
 * a card). Each row is the shared colour picker (spectrum, hue, eyedropper, swatches) plus an optional name;
 * the list is saved with the dialog's Save.
 */
export function AccessoryColoursField({
  colours,
  canEdit,
  onChange,
}: {
  colours: AccessoryColour[];
  canEdit: boolean;
  onChange: (next: AccessoryColour[]) => void;
}) {
  // A stable id per row, kept in step with the list as it is added to, removed from and reordered.
  const counter = useRef(0);
  const ids = useRef<string[]>([]);
  while (ids.current.length < colours.length) ids.current.push(`colour-${(counter.current += 1)}`);
  ids.current.length = colours.length;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = ids.current.indexOf(String(active.id));
    const to = ids.current.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    ids.current = arrayMove(ids.current, from, to);
    onChange(arrayMove(colours, from, to));
  };

  return (
    <div className="space-y-1.5">
      <Label>Colours</Label>
      {colours.length > 0 ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis, restrictToParentElement]}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={ids.current} strategy={verticalListSortingStrategy}>
            <ul className="space-y-1.5">
              {colours.map((colour, index) => (
                <ColourRow
                  key={ids.current[index]}
                  id={ids.current[index]}
                  index={index}
                  colour={colour}
                  canEdit={canEdit}
                  onChange={(next) => onChange(colours.map((c, i) => (i === index ? next : c)))}
                  onRemove={() => {
                    ids.current = ids.current.filter((_, i) => i !== index);
                    onChange(colours.filter((_, i) => i !== index));
                  }}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      ) : null}
      {canEdit ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={colours.length >= MAX_COLOURS}
          onClick={() => onChange([...colours, { name: null, hex: nextDefaultHex(colours) }])}
        >
          <Plus className="size-4" />
          Add colour
        </Button>
      ) : null}
    </div>
  );
}
