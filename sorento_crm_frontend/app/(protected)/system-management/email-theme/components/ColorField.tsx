'use client';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const HEX = /^#([0-9a-fA-F]{6})$/;

export interface ColorFieldProps {
  id: string;
  label: string;
  /** Blank = unset (falls back to `defaultValue`, AC-EM022). */
  value: string;
  onChange: (value: string) => void;
  /** The resolved default, shown both as the placeholder and as the swatch
   * colour while `value` is blank (D1: a blank field saves as null). */
  defaultValue: string;
}

/**
 * A colour field is a native swatch plus a hex text input, both bound to the
 * same value (the plan's spec for every colour on the Email Theme page) - no
 * new colour-picker dependency, since a hex box + native swatch already
 * covers "pick" and "type" without the drag-square `ColorPicker` (dealer-kit
 * tag canvas) needed for HSV precision on a design surface.
 */
export function ColorField({ id, label, value, onChange, defaultValue }: ColorFieldProps) {
  const swatchValue = HEX.test(value) ? value : defaultValue;

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} swatch`}
          value={swatchValue}
          onChange={(e) => onChange(e.target.value)}
          className="size-9 shrink-0 cursor-pointer rounded border border-input bg-transparent p-0.5"
        />
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={defaultValue}
          className="font-mono"
        />
      </div>
    </div>
  );
}

export default ColorField;
