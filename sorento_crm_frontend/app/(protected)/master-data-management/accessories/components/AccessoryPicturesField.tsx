'use client';

import { useRef, useState } from 'react';
import { GripVertical, ImagePlus, LoaderCircleIcon, X } from 'lucide-react';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useRowPending } from '@/hooks/useDeferredRowAction';
import {
  useAccessoryPictures,
  useDeleteAccessoryPicture,
  useFreshAccessoryPictures,
} from '../hooks/useAccessories';
import type { AccessoryPicture } from '../types/accessory.types';

/** The short palette; anything else is a custom hex. */
export const PICTURE_COLOURS = [
  { value: '#1f2937', label: 'Black' },
  { value: '#9ca3af', label: 'Grey' },
  { value: '#c0c0c0', label: 'Silver' },
  { value: '#ffffff', label: 'White' },
  { value: '#d4af37', label: 'Gold' },
  { value: '#2c3539', label: 'Gunmetal' },
];
const CUSTOM = 'custom';
const COLOUR_OPTIONS = [...PICTURE_COLOURS, { value: CUSTOM, label: 'Custom' }];
const HEX = /^#[0-9a-fA-F]{6}$/;

function colourChoice(hex: string | null): string {
  if (!hex) return '';
  const match = PICTURE_COLOURS.find((colour) => colour.value === hex.toLowerCase());
  return match ? match.value : CUSTOM;
}

function PictureRow({
  picture,
  index,
  canEdit,
  pending,
  onColour,
  onRemove,
}: {
  picture: AccessoryPicture;
  index: number;
  canEdit: boolean;
  /** Its removal is counting down. */
  pending: boolean;
  onColour: (colour: { colour_name: string | null; colour_hex: string | null }) => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: picture.id,
  });
  const [custom, setCustom] = useState(colourChoice(picture.colour_hex) === CUSTOM);
  const [hex, setHex] = useState(colourChoice(picture.colour_hex) === CUSTOM ? (picture.colour_hex ?? '') : '');
  const choice = custom ? CUSTOM : colourChoice(picture.colour_hex);

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-2 rounded-md border bg-background p-2 ${isDragging ? 'z-10 shadow-md' : ''} ${pending ? 'opacity-50' : ''}`}
    >
      {canEdit ? (
        <button
          type="button"
          className="shrink-0 cursor-grab touch-none text-muted-foreground"
          aria-label={`Reorder picture ${index + 1}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </button>
      ) : null}
      <img src={picture.url} alt="" className="size-14 shrink-0 rounded-md border object-cover" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        {canEdit ? (
          <>
            <SearchableSelect
              aria-label={`Colour of picture ${index + 1}`}
              value={choice}
              options={COLOUR_OPTIONS}
              clearable
              placeholder="No colour"
              onChange={(value: string) => {
                if (!value) {
                  setCustom(false);
                  onColour({ colour_name: null, colour_hex: null });
                } else if (value === CUSTOM) {
                  setCustom(true);
                } else {
                  setCustom(false);
                  const picked = PICTURE_COLOURS.find((colour) => colour.value === value);
                  onColour({ colour_name: picked?.label ?? null, colour_hex: value });
                }
              }}
            />
            {custom ? (
              <Input
                aria-label={`Custom colour of picture ${index + 1}`}
                className="h-8"
                placeholder="#d4af37"
                maxLength={7}
                value={hex}
                onChange={(e) => {
                  setHex(e.target.value);
                  if (HEX.test(e.target.value)) {
                    onColour({ colour_name: null, colour_hex: e.target.value.toLowerCase() });
                  }
                }}
              />
            ) : null}
          </>
        ) : (
          <span className="text-sm">{picture.colour_name ?? picture.colour_hex ?? ''}</span>
        )}
      </div>
      {canEdit ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="shrink-0"
          aria-label={`Remove picture ${index + 1}`}
          disabled={pending}
          onClick={onRemove}
        >
          <X className="size-4" />
        </Button>
      ) : null}
    </li>
  );
}

/**
 * An accessory's ordered pictures, each with a colour (PRICETAG-ACCESSORY-DESIGNER S4). Adding,
 * recolouring, removing and dragging into a new order each save at once; the first picture is the
 * default. `onChanged` hands the new set up so the open modal shows it without waiting for the list.
 */
export function AccessoryPicturesField({
  accessoryId,
  pictures,
  canEdit,
  onChanged,
}: {
  accessoryId: string;
  pictures: AccessoryPicture[];
  canEdit: boolean;
  onChanged: (pictures: AccessoryPicture[]) => void;
}) {
  const { addMutateAsync, patchMutateAsync, orderMutateAsync, busy } = useAccessoryPictures();
  const freshPictures = useFreshAccessoryPictures();
  const latest = useRef({ onChanged });
  latest.current = { onChanged };
  // Several countdowns can overlap, and a cancelled one never commits: when ANY removal commits the
  // list is read back from the server, so each picture leaves exactly when it was really removed.
  const removal = useDeleteAccessoryPicture(() => {
    void freshPictures(accessoryId)
      .then((fresh) => latest.current.onChanged(fresh))
      .catch(() => undefined);
  });
  const isPending = useRowPending<AccessoryPicture>('accessory_image');
  const inputRef = useRef<HTMLInputElement | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const run = async (action: () => Promise<void>) => {
    try {
      await action();
    } catch {
      // The hook has already toasted the reason.
    }
  };

  const onFile = (file: File | undefined) =>
    run(async () => {
      if (!file) return;
      const added = await addMutateAsync({ id: accessoryId, file });
      onChanged([...pictures, added]);
    }).finally(() => {
      if (inputRef.current) inputRef.current.value = '';
    });

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = pictures.findIndex((p) => p.id === active.id);
    const to = pictures.findIndex((p) => p.id === over.id);
    if (from < 0 || to < 0) return;
    const next = arrayMove(pictures, from, to);
    onChanged(next);
    void run(async () => {
      onChanged(await orderMutateAsync({ id: accessoryId, ids: next.map((p) => p.id) }));
    });
  };

  return (
    <div className="space-y-1.5">
      <Label>Pictures</Label>
      {pictures.length === 0 ? <p className="text-sm text-muted-foreground">No pictures</p> : null}
      {pictures.length > 0 ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis, restrictToParentElement]}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={pictures.map((p) => p.id)} strategy={verticalListSortingStrategy}>
            <ul className="space-y-1.5">
              {pictures.map((picture, index) => (
                <PictureRow
                  key={picture.id}
                  picture={picture}
                  index={index}
                  canEdit={canEdit}
                  onColour={(colour) =>
                    void run(async () => {
                      const saved = await patchMutateAsync({ id: accessoryId, imageId: picture.id, colour });
                      onChanged(pictures.map((p) => (p.id === saved.id ? saved : p)));
                    })
                  }
                  pending={isPending(picture)}
                  onRemove={() => {
                    removal.run({ id: picture.id, subject: picture.colour_name ?? `Picture ${index + 1}` });
                  }}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      ) : null}
      {canEdit ? (
        <>
          <input
            ref={inputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            aria-label="Picture file"
            className="hidden"
            onChange={(event) => void onFile(event.target.files?.[0])}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={busy || pictures.length >= 12}
          >
            {busy ? <LoaderCircleIcon className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}
            Add picture
          </Button>
        </>
      ) : null}
    </div>
  );
}
