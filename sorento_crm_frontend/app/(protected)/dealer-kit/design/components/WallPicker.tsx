'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SelectTriggerSize } from '@/components/common/select-trigger-variants';

export interface WallPickerProps {
  id?: string;
  /**
   * Wall lengths in mm, one per wall, indexed the same as `wallIndex`
   * everywhere else in the room model (`Opening.wallIndex`, `moveOpening`).
   */
  walls: number[];
  /** The currently selected wall index. */
  value: number;
  onChange: (wallIndex: number) => void;
  size?: SelectTriggerSize;
  triggerClassName?: string;
}

/** Which wall an opening (door/window) sits on. */
export function WallPicker({ id, walls, value, onChange, size, triggerClassName }: WallPickerProps) {
  return (
    <SearchableSelect
      id={id}
      size={size}
      triggerClassName={triggerClassName}
      value={String(value)}
      onChange={(next) => onChange(Number(next))}
      options={walls.map((length, index) => ({
        value: String(index),
        label: `${index + 1} (${Math.round(length)} mm)`,
      }))}
    />
  );
}
