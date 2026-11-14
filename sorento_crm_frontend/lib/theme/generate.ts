/**
 * The UI v2 theme engine (D6, UAC C-1..C-4): one brand colour -> an 11-step OKLCH ramp -> the
 * semantic tokens, with the primary picked so its text clears WCAG AA. A port of the reference
 * engine in documentation/uiux/ui-v2-mocks/index.html; the test pins its output.
 */
import { contrastRatio, hexToRgb, srgbToLinear } from './contrast';
import { PAGE_BACKGROUND, WHITE } from './presets';

export const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950] as const;
export type Step = (typeof STEPS)[number];
export type ThemeMode = 'light' | 'dark';

const LIGHTNESS = [0.97, 0.93, 0.87, 0.79, 0.71, 0.63, 0.55, 0.48, 0.41, 0.34, 0.27];
const CHROMA = [0.12, 0.25, 0.45, 0.7, 0.9, 1, 1, 0.95, 0.85, 0.72, 0.6];

export interface Theme {
  ramp: Record<Step, string>;
  tokens: {
    primary: string;
    'primary-hover': string;
    'primary-foreground': string;
    'primary-soft': string;
    ring: string;
  };
  background: string;
}

function linearToSrgb(c: number): number {
  const v = Math.max(0, Math.min(1, c));
  return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
}

function toOklch(hex: string): [number, number, number] {
  const [r, g, b] = hexToRgb(hex).map(srgbToLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [L, Math.sqrt(A * A + B * B), Math.atan2(B, A)];
}

function oklchToLinearRgb(L: number, C: number, H: number): [number, number, number] {
  const a = C * Math.cos(H);
  const b = C * Math.sin(H);
  const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
  const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
  const s = Math.pow(L - 0.0894841775 * a - 1.291485548 * b, 3);
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

const inGamut = (c: number[]) => c.every((v) => v >= -0.0005 && v <= 1.0005);

/** OKLCH to hex, reducing chroma until the colour fits sRGB. */
function toHex(L: number, C: number, H: number): string {
  let c = C;
  let rgb = oklchToLinearRgb(L, c, H);
  while (!inGamut(rgb) && c > 0) {
    c -= 0.005;
    rgb = oklchToLinearRgb(L, c, H);
  }
  return `#${rgb.map((v) => `0${Math.round(linearToSrgb(v) * 255).toString(16)}`.slice(-2)).join('')}`;
}

export function generateRamp(hex: string): Record<Step, string> {
  const [, c, h] = toOklch(hex);
  const chroma = c < 0.02 ? 0 : c;
  const ramp = {} as Record<Step, string>;
  STEPS.forEach((step, i) => {
    ramp[step] = toHex(LIGHTNESS[i], chroma * CHROMA[i], h);
  });
  return ramp;
}

const next = (s: Step, by: number): Step => STEPS[Math.max(0, Math.min(STEPS.length - 1, STEPS.indexOf(s) + by))];

export function generateTheme(hex: string, mode: ThemeMode): Theme {
  const ramp = generateRamp(hex);
  const background = PAGE_BACKGROUND[mode];
  let primary: string;
  let hover: string;
  let foreground: string;
  let soft: string;
  if (mode === 'light') {
    const pick = ([600, 700, 800, 900] as const).find((s) => contrastRatio(ramp[s], WHITE) >= 4.5);
    if (pick) {
      primary = ramp[pick];
      foreground = WHITE;
      hover = ramp[next(pick, 1)];
    } else {
      primary = ramp[500];
      foreground = ramp[950];
      hover = ramp[600];
    }
    soft = ramp[50];
  } else {
    const pick = ([400, 300, 200] as const).find((s) => contrastRatio(ramp[s], background) >= 4.5) ?? 200;
    primary = ramp[pick];
    hover = ramp[next(pick, -1)];
    foreground = ramp[950];
    soft = ramp[950];
  }
  return {
    ramp,
    tokens: { primary, 'primary-hover': hover, 'primary-foreground': foreground, 'primary-soft': soft, ring: primary },
    background,
  };
}
