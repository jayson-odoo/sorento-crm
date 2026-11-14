/**
 * The theme inputs (UI v2, D6). This is the ONLY file in the frontend allowed to hold brand hex
 * literals: every colour v2 paints is generated from one of these by `generate.ts`.
 */

export type PresetId = 'sorento-blue' | 'sorento-red' | 'teal' | 'graphite' | 'indigo';

export const PRESETS: ReadonlyArray<{ id: PresetId; label: string; hex: string }> = [
  { id: 'sorento-blue', label: 'Sorento Blue', hex: '#3b82f6' },
  { id: 'sorento-red', label: 'Sorento Red', hex: '#b44d2e' },
  { id: 'teal', label: 'Teal', hex: '#0f766e' },
  { id: 'graphite', label: 'Graphite', hex: '#3f3f46' },
  { id: 'indigo', label: 'Indigo', hex: '#4f46e5' },
];

export const DEFAULT_PRESET: PresetId = 'sorento-blue';

/** The page backgrounds the generator measures contrast against. */
export const PAGE_BACKGROUND = { light: '#ffffff', dark: '#111113' } as const;

/** Ink used on a primary fill when the ramp has a step dark enough for it. */
export const WHITE = '#ffffff';

export function presetHex(id: string | null | undefined): string {
  return (PRESETS.find((p) => p.id === id) ?? PRESETS[0]).hex;
}

/** The brand hex for a stored company theme `{preset, custom_hex}`. */
export function themeInputHex(theme: { preset?: string | null; custom_hex?: string | null } | null | undefined): string {
  const custom = theme?.custom_hex;
  if (custom && /^#[0-9a-fA-F]{6}$/.test(custom)) return custom.toLowerCase();
  return presetHex(theme?.preset);
}
