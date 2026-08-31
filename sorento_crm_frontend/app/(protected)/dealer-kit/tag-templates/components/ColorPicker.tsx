'use client';

/**
 * The colour control for the tag canvas inspector (D54).
 *
 * Three ways in, one colour. The popover leads with the browser's own
 * `input[type=color]` - the full spectrum, and Chrome's eyedropper for nothing -
 * because twelve swatches and a hex box meant the designer who wanted the
 * thirteenth colour had to already know its hex code, which is not how anybody
 * picks a colour. The brand swatches stay under it as the quick path and the
 * hex box stays editable, and the three are kept in step both ways: the
 * spectrum rewrites the box, a valid hex moves the spectrum, and a half-typed
 * one changes nothing until it becomes a colour.
 *
 * No library. The native control already is the spectrum, and the one thing it
 * gets wrong for us is its 20px default size, which CSS fixes.
 */

import { useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';

const BRAND_SWATCHES = [
  { label: 'Sorento Red', value: '#b44d2e' },
  { label: 'Black', value: '#000000' },
  { label: 'White', value: '#ffffff' },
  { label: 'Dark Grey', value: '#333333' },
  { label: 'Grey', value: '#666666' },
  { label: 'Light Grey', value: '#999999' },
  { label: 'Pale Grey', value: '#cccccc' },
  { label: 'Off White', value: '#f5f5f5' },
  { label: 'Badge Green', value: '#2e7d32' },
  { label: 'Badge Blue', value: '#1565c0' },
  { label: 'Gold', value: '#c69c3a' },
  { label: 'Transparent', value: 'transparent' },
];

const HEX = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** The chequerboard that says "no colour here", used by the swatches too. */
const CHEQUER = 'repeating-conic-gradient(#ccc 0% 25%, transparent 0% 50%)';

/**
 * A hex the native control will accept: always `#rrggbb`.
 *
 * `#f00` is a colour a person types and the input silently rejects, so it is
 * expanded rather than dropped. `transparent` has no place on a spectrum at
 * all, so the control falls back to black while the swatch keeps drawing the
 * chequerboard that says what is really set.
 */
function toSpectrumHex(value: string): string {
  if (!HEX.test(value)) return '#000000';
  if (value.length === 4) {
    return `#${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`;
  }
  return value.toLowerCase();
}

interface ColorPickerProps {
  value: string;
  onChange: (color: string) => void;
  label?: string;
}

export function ColorPicker({ value, onChange, label }: ColorPickerProps) {
  const [expanded, setExpanded] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync local input with external value changes.
  useEffect(() => {
    setInputValue(value);
  }, [value]);

  // Close when clicking outside.
  useEffect(() => {
    if (!expanded) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [expanded]);

  const commitHex = (hex: string) => {
    const trimmed = hex.trim();
    if (HEX.test(trimmed) || trimmed === 'transparent') {
      onChange(trimmed);
    }
  };

  /**
   * What the spectrum is showing. The typed box wins while it holds a colour,
   * so the picker follows the keyboard live rather than waiting for a blur.
   */
  const spectrumValue = toSpectrumHex(HEX.test(inputValue.trim()) ? inputValue.trim() : value);

  const pick = (hex: string) => {
    setInputValue(hex);
    onChange(hex);
  };

  return (
    <div ref={containerRef} className="relative">
      {label && <span className="mb-1 block text-xs text-muted-foreground">{label}</span>}
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="size-7 shrink-0 rounded border border-input shadow-sm"
          style={{
            backgroundColor: value === 'transparent' ? undefined : value,
            backgroundImage: value === 'transparent' ? `${CHEQUER} 50% / 8px 8px` : undefined,
          }}
          onClick={() => setExpanded(!expanded)}
          title={value}
        />
        <Input
          aria-label="Hex colour"
          className="h-7 px-2 text-xs font-mono"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onBlur={() => commitHex(inputValue)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitHex(inputValue);
          }}
        />
      </div>

      {expanded && (
        <div className="absolute top-full left-0 z-50 mt-1 w-48 rounded-md border bg-popover p-2 shadow-md">
          {/* The spectrum, given a swatch-sized area rather than the browser's
              20px default so it can actually be aimed at. */}
          <input
            type="color"
            aria-label="Pick a colour"
            value={spectrumValue}
            onChange={(e) => pick(e.target.value)}
            className="mb-2 h-16 w-full cursor-pointer rounded border border-input bg-transparent p-0"
          />

          <div className="grid grid-cols-6 gap-1">
            {BRAND_SWATCHES.map((swatch) => (
              <button
                key={swatch.value}
                type="button"
                className="size-6 rounded border border-input hover:ring-2 hover:ring-primary/40"
                style={{
                  backgroundColor:
                    swatch.value === 'transparent' ? undefined : swatch.value,
                  backgroundImage:
                    swatch.value === 'transparent' ? `${CHEQUER} 50% / 6px 6px` : undefined,
                }}
                title={swatch.label}
                onClick={() => {
                  pick(swatch.value);
                  setExpanded(false);
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
