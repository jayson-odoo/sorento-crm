/**
 * UI v2 phase 0, slice S2 (red first). UAC C-1, C-2, C-3, C-4; plan section 3 "Frontend".
 *
 * EXPORT CONTRACT (the modules do not exist yet; the coder implements exactly this):
 *   lib/theme/contrast.ts : contrastRatio(fgHex: string, bgHex: string): number   // WCAG 2.x
 *   lib/theme/presets.ts  : PRESETS: ReadonlyArray<{ id: PresetId; label: string; hex: string }>
 *                           PresetId = 'sorento-blue' | 'sorento-red' | 'teal' | 'graphite' | 'indigo'
 *   lib/theme/generate.ts : generateTheme(hex: string, mode: 'light' | 'dark'): {
 *                             ramp: Record<50|100|200|300|400|500|600|700|800|900|950, string>,
 *                             tokens: { primary; 'primary-hover'; 'primary-foreground';
 *                                       'primary-soft'; ring: string },
 *                             background: string   // '#ffffff' light, '#111113' dark
 *                           }
 *   All colours are lowercase 7-char hex. The algorithm is the "theme engine" of
 *   documentation/uiux/ui-v2-mocks/index.html (OKLCH ramp, AA-guarded pick); the pinned
 *   values below were produced by running that reference, not guessed.
 */
import { describe, expect, it } from 'vitest';
import { generateTheme } from './generate';
import { PRESETS } from './presets';
import { contrastRatio } from './contrast';

const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950] as const;
const HEX = /^#[0-9a-f]{6}$/;
const STRESS = ['#facc15', '#ffffff', '#000000'];

describe('contrastRatio', () => {
  it('matches the WCAG reference points', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 1);
  });
});

describe('generateTheme', () => {
  it('returns the ramp and semantic tokens', () => {
    const t = generateTheme('#3b82f6', 'light');
    expect(Object.keys(t.ramp).map(Number).sort((a, b) => a - b)).toEqual([...STEPS]);
    for (const s of STEPS) expect(t.ramp[s]).toMatch(HEX);
    for (const k of ['primary', 'primary-hover', 'primary-foreground', 'primary-soft', 'ring'] as const) {
      expect(t.tokens[k]).toMatch(HEX);
    }
    expect(t.background).toBe('#ffffff');
    expect(generateTheme('#3b82f6', 'dark').background).toBe('#111113');
  });

  it('every preset and stress input clears AA in light and dark', () => {
    expect(PRESETS.map((p) => p.id)).toEqual(['sorento-blue', 'sorento-red', 'teal', 'graphite', 'indigo']);
    const inputs = [...PRESETS.map((p) => p.hex), ...STRESS];
    for (const hex of inputs) {
      for (const mode of ['light', 'dark'] as const) {
        const t = generateTheme(hex, mode);
        const label = `${hex} ${mode}`;
        expect(contrastRatio(t.tokens.primary, t.tokens['primary-foreground']), `${label} text`).toBeGreaterThanOrEqual(4.5);
        expect(contrastRatio(t.tokens.primary, t.background), `${label} on page`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it('keeps the five preset hexes the UAC names', () => {
    expect(Object.fromEntries(PRESETS.map((p) => [p.id, p.hex]))).toEqual({
      'sorento-blue': '#3b82f6',
      'sorento-red': '#b44d2e',
      teal: '#0f766e',
      graphite: '#3f3f46',
      indigo: '#4f46e5',
    });
  });

  it('Sorento Blue light primary is #246bdd with white ink', () => {
    const t = generateTheme('#3b82f6', 'light');
    expect(t.tokens.primary).toBe('#246bdd');
    expect(t.tokens['primary-foreground']).toBe('#ffffff');
    // Reference engine values for the rest of the blue ramp and tokens.
    expect(t.tokens['primary-hover']).toBe('#1156c0');
    expect(t.tokens['primary-soft']).toBe('#f0f5fe');
    expect(t.ramp[50]).toBe('#f0f5fe');
    expect(t.ramp[600]).toBe('#246bdd');
    expect(t.ramp[950]).toBe('#00215c');
  });

  it('Sorento Blue dark picks the first of 400/300/200 that clears AA on #111113, with 950 ink', () => {
    const t = generateTheme('#3b82f6', 'dark');
    expect(t.tokens.primary).toBe('#68a1fe');
    expect(t.tokens['primary-foreground']).toBe('#00215c');
    expect(t.tokens['primary-soft']).toBe('#00215c');
  });

  it('a yellow input falls to a dark enough step, never white-on-yellow', () => {
    const t = generateTheme('#facc15', 'light');
    expect(t.tokens.primary).toBe('#886f0f');
    expect(t.tokens['primary-foreground']).toBe('#ffffff');
  });

  it('achromatic input yields a neutral ramp', () => {
    for (const hex of ['#ffffff', '#000000', '#808080']) {
      const t = generateTheme(hex, 'light');
      for (const s of STEPS) {
        const c = t.ramp[s];
        const [r, g, b] = [c.slice(1, 3), c.slice(3, 5), c.slice(5, 7)];
        expect(r, `${hex} step ${s}`).toBe(g);
        expect(g, `${hex} step ${s}`).toBe(b);
      }
    }
    expect(generateTheme('#ffffff', 'light').tokens.primary).toBe('#717171');
  });
});
