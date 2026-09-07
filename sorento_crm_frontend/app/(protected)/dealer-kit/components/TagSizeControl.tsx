'use client';

/**
 * Tag Size control (S1, lifted from `RequestTagDesigner.tsx` so the template
 * editor can show the same one - the one thing it could not do before this
 * round was change a tag's size after creating it).
 *
 * Preset dropdown (published templates' own sizes, then saved sizes, each
 * deletable via `onDeleteSavedSize`) + custom W/H committed on blur/Enter,
 * not per keystroke - the caller's `width_mm`/`height_mm` changing on every
 * digit would remount whatever canvas is mounted on it before the second
 * one lands.
 *
 * Deliberately react-query-FREE: "Saved sizes" (`useTagSizesQuery`),
 * deleting one (`useDeleteTagSizePreset`) and "Save as size"
 * (`SaveAsSizeDialog`'s own `useCreateTagSize`) all need a
 * `QueryClientProvider`, which the template editor - one of this
 * component's two mount points - does not always have in the tree it is
 * unit-tested in. The caller owns all three (data, delete, the dialog) and
 * hands this component plain data plus callbacks; absent, this simply does
 * not offer that affordance rather than reaching for the hook itself.
 *
 * `onResizeAll` absent hides "Apply to all lines" (a template has no other
 * lines); `bounds` absent means the `MIN_TAG_SIZE_MM` floor only, no ceiling
 * (a template has no sheet to fit, unlike a request's imposition).
 */

import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import {
  MIN_TAG_SIZE_MM,
  resolveTagSize,
  type TagSizeBounds,
  type TagSizePreset,
} from '@/lib/dealer-kit/request-tags';
import type { TagSizeRecord } from '@/app/(protected)/dealer-kit/services/tagSizeService';

/** No ceiling, floor only - what an absent `bounds` prop means. */
const FLOOR_ONLY_BOUNDS: TagSizeBounds = {
  min_mm: MIN_TAG_SIZE_MM,
  max_width_mm: Infinity,
  max_height_mm: Infinity,
};

/**
 * Never a real option in the SELECT - a size nobody picked from the list has
 * nothing to select TO. `value` is set to this whenever the current size
 * matches no preset, so the trigger falls through to `placeholder="Custom"`
 * the same way every other unselected SearchableSelect shows its placeholder:
 * muted, and un-clickable in the list.
 */
const CUSTOM_SIZE_VALUE = '__custom__';

function sizeKey(width_mm: number, height_mm: number): string {
  return `${width_mm}x${height_mm}`;
}

export interface TagSizeControlProps {
  width_mm: number;
  height_mm: number;
  presets: TagSizePreset[];
  savedSizes?: TagSizeRecord[];
  bounds?: TagSizeBounds;
  onResize: (width_mm: number, height_mm: number) => void;
  onResizeAll?: (width_mm: number, height_mm: number) => void;
  /** Delete a saved size's `x` (absent hides it - no delete affordance without one). */
  onDeleteSavedSize?: (id: string, name: string) => void;
  /** Which saved size's delete is in flight, so its `x` can dim/disable. */
  deletingSavedSizeId?: string | null;
  /** "Save as size" button (absent hides it - the caller owns the dialog). */
  onSaveAsSize?: () => void;
}

export function TagSizeControl({
  width_mm,
  height_mm,
  presets,
  savedSizes = [],
  bounds = FLOOR_ONLY_BOUNDS,
  onResize,
  onResizeAll,
  onDeleteSavedSize,
  deletingSavedSizeId,
  onSaveAsSize,
}: TagSizeControlProps) {
  // Held as TEXT and committed on blur/Enter, not on every keystroke: the
  // control used to call `onResize` per keystroke, which changed a doc key
  // the canvas was mounted on and remounted the whole editor (this control's
  // own DOM included) after the first digit, so "95" typed as fast as
  // anyone can type landed as "9". `null` means "nothing typed right now" -
  // the field shows the live value, which is what lets a preset pick update
  // the boxes without an effect fighting whatever is mid-typed in them.
  const [wDraft, setWDraft] = useState<string | null>(null);
  const [hDraft, setHDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const commit = (axis: 'w' | 'h') => {
    const draft = axis === 'w' ? wDraft : hDraft;
    const setDraft = axis === 'w' ? setWDraft : setHDraft;
    if (draft === null) return;
    const n = parseFloat(draft);
    if (Number.isNaN(n)) {
      setDraft(null);
      setError(null);
      return;
    }
    const candidateW = axis === 'w' ? n : width_mm;
    const candidateH = axis === 'h' ? n : height_mm;
    const result = resolveTagSize(candidateW, candidateH, bounds);
    if (!result.ok) {
      // Keep the typed value on screen next to the reason - reverting it
      // silently would read as the edit never happened.
      setError(result.reason);
      return;
    }
    setError(null);
    onResize(result.width_mm, result.height_mm);
    setDraft(null);
  };

  const onEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur();
  };

  // Every size choice, template-derived AND saved, keyed the same way:
  // "Template sizes" first (not deletable here), then "Saved sizes" (each
  // with an `x`, when `onDeleteSavedSize` is given). `savedByKey` is what
  // lets `renderOption` find the RECORD behind a saved row - the option
  // itself only carries the size.
  const savedByKey = new Map(
    savedSizes.map((s) => [sizeKey(s.width_mm, s.height_mm), s] as const),
  );
  const options: SearchableSelectOption[] = [
    ...presets.map((p) => ({
      value: sizeKey(p.width_mm, p.height_mm),
      label: p.label,
      group: 'Template sizes',
    })),
    ...savedSizes.map((s) => ({
      value: sizeKey(s.width_mm, s.height_mm),
      label: `${s.name} (${s.width_mm} x ${s.height_mm} mm)`,
      group: 'Saved sizes',
    })),
  ];
  const allSizes: { width_mm: number; height_mm: number }[] = [...presets, ...savedSizes];
  const matchingPreset = allSizes.find(
    (p) => p.width_mm === width_mm && p.height_mm === height_mm,
  );

  const applySize = (nextWidth_mm: number, nextHeight_mm: number) => {
    const result = resolveTagSize(nextWidth_mm, nextHeight_mm, bounds);
    if (!result.ok) {
      setError(result.reason);
      return;
    }
    setError(null);
    onResize(result.width_mm, result.height_mm);
  };

  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-r p-3">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Tag Size
      </span>
      <SearchableSelect
        value={matchingPreset ? sizeKey(matchingPreset.width_mm, matchingPreset.height_mm) : CUSTOM_SIZE_VALUE}
        onChange={(value) => {
          const found = allSizes.find((p) => sizeKey(p.width_mm, p.height_mm) === value);
          if (!found) return;
          applySize(found.width_mm, found.height_mm);
        }}
        options={options}
        placeholder="Custom"
        renderOption={(opt) => {
          const saved = savedByKey.get(opt.value);
          return (
            <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
              <span className="truncate break-words">{opt.label}</span>
              {saved && onDeleteSavedSize && (
                (() => {
                  const pending = deletingSavedSizeId === saved.id;
                  return (
                    <button
                      type="button"
                      aria-label={`Delete saved size ${saved.name}`}
                      disabled={pending}
                      className={cn(
                        'shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-destructive',
                        pending && 'pointer-events-none opacity-50',
                      )}
                      onPointerDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onDeleteSavedSize(saved.id, saved.name);
                      }}
                    >
                      <X className="size-3.5" />
                    </button>
                  );
                })()
              )}
            </div>
          );
        }}
      />
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">W (mm)</Label>
          <Input
            type="number"
            className="h-7 px-2 text-xs"
            aria-label="Tag width (mm)"
            value={wDraft ?? width_mm}
            step={0.5}
            onChange={(e) => setWDraft(e.target.value)}
            onBlur={() => commit('w')}
            onKeyDown={onEnter}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">H (mm)</Label>
          <Input
            type="number"
            className="h-7 px-2 text-xs"
            aria-label="Tag height (mm)"
            value={hDraft ?? height_mm}
            step={0.5}
            onChange={(e) => setHDraft(e.target.value)}
            onBlur={() => commit('h')}
            onKeyDown={onEnter}
          />
        </div>
      </div>
      {error && <p className="text-2xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        {onResizeAll && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 flex-1 text-xs"
            onClick={() => onResizeAll(width_mm, height_mm)}
          >
            Apply to all lines
          </Button>
        )}
        {!matchingPreset && onSaveAsSize && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 flex-1 text-xs"
            onClick={onSaveAsSize}
          >
            Save as size
          </Button>
        )}
      </div>
    </div>
  );
}
