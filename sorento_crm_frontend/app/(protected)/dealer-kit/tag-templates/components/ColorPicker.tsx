'use client';

/**
 * The colour control for the tag canvas inspector (D54, S3/D6).
 *
 * The popover is now a Figma-style spectrum: a saturation/value square plus a
 * hue bar, both plain divs driven by pointer events - no dependency, because
 * the square is one gradient-on-gradient background and a dot, and the hue
 * bar is a CSS rainbow gradient and a knob. Dragging updates the hex live so
 * the box never lags the finger, but the layer itself (and the canvas
 * repaint that follows) only commits on release - a drag across the square
 * is one history entry, not sixty.
 *
 * Three more ways to the same colour: the hex box (typed, still the source
 * of truth when it holds a real colour), the eyedropper (`window.EyeDropper`,
 * hidden where the browser has none), and two rows of ready-made swatches -
 * "This tag" (derived from what is already on the canvas, `tagColours`) and
 * "Brand" (the same twelve as before).
 */

import { useEffect, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { Pipette } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { hexToHsv, hsvToHex, type Hsv } from '@/lib/dealer-kit/colour';

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
 * A hex the HSV math will accept: always `#rrggbb`.
 *
 * `#f00` is a colour a person types and `hexToHsv` already expands, so this
 * only has to catch `transparent` and half-typed input, both of which fall
 * back to black - the same fallback the old native-input version used.
 */
function toSpectrumHex(value: string): string {
  return HEX.test(value) ? value : '#000000';
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

// ---------------------------------------------------------------------------
// Saturation/value square
// ---------------------------------------------------------------------------

interface SvChange {
  s: number;
  v: number;
}

function SaturationValueField({
  hue,
  s,
  v,
  onLiveChange,
  onCommit,
}: {
  hue: number;
  s: number;
  v: number;
  onLiveChange: (next: SvChange) => void;
  onCommit: (next: SvChange) => void;
}) {
  const fromPoint = (el: HTMLDivElement, clientX: number, clientY: number): SvChange => {
    const rect = el.getBoundingClientRect();
    const ns = clamp01((clientX - rect.left) / rect.width) * 100;
    const nv = (1 - clamp01((clientY - rect.top) / rect.height)) * 100;
    return { s: Math.round(ns), v: Math.round(nv) };
  };

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    let latest = fromPoint(el, e.clientX, e.clientY);
    onLiveChange(latest);

    const onMove = (ev: PointerEvent) => {
      latest = fromPoint(el, ev.clientX, ev.clientY);
      onLiveChange(latest);
    };
    const onUp = (ev: PointerEvent) => {
      el.releasePointerCapture(ev.pointerId);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      onCommit(latest);
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
  };

  return (
    <div
      role="slider"
      aria-label="Saturation and brightness"
      aria-valuenow={v}
      onPointerDown={handlePointerDown}
      className="relative mb-2 h-32 w-full touch-none rounded-md border border-input"
      style={{
        backgroundColor: `hsl(${hue}, 100%, 50%)`,
        backgroundImage:
          'linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, transparent)',
      }}
    >
      <div
        className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,0.35)]"
        style={{ left: `${s}%`, top: `${100 - v}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hue slider
// ---------------------------------------------------------------------------

function HueSlider({
  hue,
  onLiveChange,
  onCommit,
}: {
  hue: number;
  onLiveChange: (h: number) => void;
  onCommit: (h: number) => void;
}) {
  const fromPoint = (el: HTMLDivElement, clientX: number): number => {
    const rect = el.getBoundingClientRect();
    return Math.round(clamp01((clientX - rect.left) / rect.width) * 360);
  };

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    let latest = fromPoint(el, e.clientX);
    onLiveChange(latest);

    const onMove = (ev: PointerEvent) => {
      latest = fromPoint(el, ev.clientX);
      onLiveChange(latest);
    };
    const onUp = (ev: PointerEvent) => {
      el.releasePointerCapture(ev.pointerId);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      onCommit(latest);
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
  };

  return (
    <div
      role="slider"
      aria-label="Hue"
      aria-valuenow={hue}
      aria-valuemin={0}
      aria-valuemax={360}
      onPointerDown={handlePointerDown}
      className="relative mb-2 h-2.5 w-full touch-none rounded-full"
      style={{
        background: 'linear-gradient(to right, #f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)',
      }}
    >
      <div
        className="pointer-events-none absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-input bg-white shadow"
        style={{ left: `${(hue / 360) * 100}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Swatch grid (shared by "This tag" and "Brand")
// ---------------------------------------------------------------------------

function SwatchGrid({
  swatches,
  onPick,
}: {
  swatches: { label: string; value: string }[];
  onPick: (value: string) => void;
}) {
  return (
    <div className="grid grid-cols-6 gap-1">
      {swatches.map((swatch) => (
        <button
          key={swatch.value}
          type="button"
          aria-label={swatch.label}
          className="size-6 rounded border border-input hover:ring-2 hover:ring-primary/40"
          style={{
            backgroundColor: swatch.value === 'transparent' ? undefined : swatch.value,
            backgroundImage: swatch.value === 'transparent' ? `${CHEQUER} 50% / 6px 6px` : undefined,
          }}
          title={swatch.label}
          onClick={() => onPick(swatch.value)}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ColorPickerProps {
  value: string;
  onChange: (color: string) => void;
  label?: string;
  /** Colours already used on this tag (S3, AC-S3-5), most-used first. */
  usedColours?: string[];
}

export function ColorPicker({ value, onChange, label, usedColours = [] }: ColorPickerProps) {
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const [hsv, setHsv] = useState<Hsv>(() => hexToHsv(toSpectrumHex(value)));
  const [hasEyeDropper, setHasEyeDropper] = useState(false);

  // Sync local state with external value changes.
  useEffect(() => {
    setInputValue(value);
    setHsv(hexToHsv(toSpectrumHex(value)));
  }, [value]);

  // `window.EyeDropper` is Chrome/Edge only (AC-S3-4); no polyfill, no button
  // where the API does not exist. Checked after mount - SSR has no `window`.
  useEffect(() => {
    setHasEyeDropper(typeof window !== 'undefined' && 'EyeDropper' in window);
  }, []);

  const commitHex = (hex: string) => {
    const trimmed = hex.trim();
    if (HEX.test(trimmed) || trimmed === 'transparent') {
      onChange(trimmed);
    }
  };

  const applyHexText = (text: string) => {
    setInputValue(text);
    const trimmed = text.trim();
    if (HEX.test(trimmed)) setHsv(hexToHsv(trimmed));
  };

  const pick = (hex: string, close = false) => {
    setInputValue(hex);
    setHsv(hexToHsv(toSpectrumHex(hex)));
    onChange(hex);
    if (close) setOpen(false);
  };

  const handleSvLive = (next: SvChange) => {
    const nextHsv = { ...hsv, ...next };
    setHsv(nextHsv);
    setInputValue(hsvToHex(nextHsv));
  };
  const handleSvCommit = (next: SvChange) => {
    onChange(hsvToHex({ ...hsv, ...next }));
  };
  const handleHueLive = (h: number) => {
    const nextHsv = { ...hsv, h };
    setHsv(nextHsv);
    setInputValue(hsvToHex(nextHsv));
  };
  const handleHueCommit = (h: number) => {
    onChange(hsvToHex({ ...hsv, h }));
  };

  const handleEyedropper = async () => {
    const EyeDropperCtor = (
      window as unknown as { EyeDropper?: new () => { open: () => Promise<{ sRGBHex: string }> } }
    ).EyeDropper;
    if (!EyeDropperCtor) return;
    try {
      const result = await new EyeDropperCtor().open();
      pick(result.sRGBHex);
    } catch {
      // Cancelled (Escape) or denied - leave the colour as it was.
    }
  };

  return (
    <div>
      {label && <span className="mb-1 block text-xs text-muted-foreground">{label}</span>}
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={label ? `${label} colour` : 'Colour'}
              className="size-7 shrink-0 rounded border border-input shadow-sm"
              style={{
                backgroundColor: value === 'transparent' ? undefined : value,
                backgroundImage: value === 'transparent' ? `${CHEQUER} 50% / 8px 8px` : undefined,
              }}
              title={value}
            />
          </PopoverTrigger>
          <PopoverPortal>
            <PopoverContent align="start" collisionPadding={8} className="w-56 p-3">
              <SaturationValueField
                hue={hsv.h}
                s={hsv.s}
                v={hsv.v}
                onLiveChange={handleSvLive}
                onCommit={handleSvCommit}
              />
              <HueSlider hue={hsv.h} onLiveChange={handleHueLive} onCommit={handleHueCommit} />

              <div className="mb-2 flex items-center gap-2">
                {hasEyeDropper && (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="size-7 shrink-0"
                    aria-label="Pick colour from screen"
                    title="Pick colour from screen"
                    onClick={handleEyedropper}
                  >
                    <Pipette className="size-3.5" />
                  </Button>
                )}
                <Input
                  aria-label="Hex"
                  className="h-7 flex-1 px-2 text-xs font-mono"
                  value={inputValue}
                  onChange={(e) => applyHexText(e.target.value)}
                  onBlur={() => commitHex(inputValue)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitHex(inputValue);
                  }}
                />
              </div>

              {usedColours.length > 0 && (
                <>
                  <div className="mb-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                    This tag
                  </div>
                  <SwatchGrid
                    swatches={usedColours.map((hex) => ({ label: hex, value: hex }))}
                    onPick={(hex) => pick(hex, true)}
                  />
                  <div className="my-2" />
                </>
              )}

              <div className="mb-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                Brand
              </div>
              <SwatchGrid swatches={BRAND_SWATCHES} onPick={(hex) => pick(hex, true)} />
            </PopoverContent>
          </PopoverPortal>
        </Popover>
        <Input
          aria-label="Hex colour"
          className="h-7 px-2 text-xs font-mono"
          value={inputValue}
          onChange={(e) => applyHexText(e.target.value)}
          onBlur={() => commitHex(inputValue)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitHex(inputValue);
          }}
        />
      </div>
    </div>
  );
}
