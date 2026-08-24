'use client';

/**
 * Simple colour picker for the tag canvas inspector.
 *
 * Shows the current colour as a swatch + hex input. Click the swatch to
 * expand a grid of brand swatches and a free hex entry.
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
    if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(trimmed) || trimmed === 'transparent') {
      onChange(trimmed);
    }
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
            backgroundImage:
              value === 'transparent'
                ? 'repeating-conic-gradient(#ccc 0% 25%, transparent 0% 50%) 50% / 8px 8px'
                : undefined,
          }}
          onClick={() => setExpanded(!expanded)}
          title={value}
        />
        <Input
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
        <div className="absolute top-full left-0 z-50 mt-1 rounded-md border bg-popover p-2 shadow-md">
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
                    swatch.value === 'transparent'
                      ? 'repeating-conic-gradient(#ccc 0% 25%, transparent 0% 50%) 50% / 6px 6px'
                      : undefined,
                }}
                title={swatch.label}
                onClick={() => {
                  onChange(swatch.value);
                  setInputValue(swatch.value);
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
