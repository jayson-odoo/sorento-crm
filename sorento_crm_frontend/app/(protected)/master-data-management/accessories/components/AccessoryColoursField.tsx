'use client';

import { useRef } from 'react';
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
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-2 rounded-md border bg-background p-2 ${isDragging ? 'z-10 shadow-md' : ''}`}
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
          <ColorPicker value={colour.hex} onChange={(hex) => onChange({ ...colour, hex: hex.toLowerCase() })} />
          <Input
            aria-label={`Colour name ${index + 1}`}
            className="h-8 min-w-0 flex-1"
            maxLength={40}
            placeholder={presetNameOf(colour.hex)}
            value={colour.name ?? ''}
            onChange={(e) => onChange({ ...colour, name: e.target.value || null })}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0"
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
          onClick={() => onChange([...colours, { name: null, hex: DEFAULT_HEX }])}
        >
          <Plus className="size-4" />
          Add colour
        </Button>
      ) : null}
    </div>
  );
}
