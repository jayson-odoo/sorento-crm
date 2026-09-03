/**
 * S2 Tokens and CSS - apple-alignment acceptance criteria S2-01 .. S2-07.
 *
 * jsdom does not run Tailwind and does not resolve a CSS custom property that is
 * declared in a stylesheet the test never linked, so a `getComputedStyle` assertion
 * here would pass against an empty string. These tests read the stylesheet text
 * instead and assert the declarations that the browser will resolve, plus the class
 * strings in the shell components that consume them.
 *
 * See documentation/plans/design-system/apple-alignment-acceptance-criteria.md
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const root = path.resolve(__dirname, '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

/**
 * A hard-coded transition duration: `duration-150` and `duration-[150ms]` alike.
 * `duration-(--duration-fast)` is the token form and is what these tests want to
 * see instead, so it deliberately does not match.
 */
const LITERAL_DURATION = /\bduration-(?:\d+\b|\[)/;

const configCss = read('css/config.reui.css');
const stylesCss = read('css/styles.css');

/** Body of the first `{...}` that follows `selector`, brace-balanced so nested at-rules survive. */
function block(css: string, selector: string): string {
  const at = css.indexOf(selector);
  if (at === -1) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf('{', at);
  if (open === -1) throw new Error(`no block for: ${selector}`);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    else if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error(`unbalanced block for: ${selector}`);
}

/** Top-level `--name: value;` declarations of a block body (nested blocks ignored). */
function declarations(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  // Comments go first: a prose semicolon inside one would otherwise split a
  // declaration in half and the token would read as undefined.
  const withoutComments = body.replace(/\/\*[\s\S]*?\*\//g, '');
  let depth = 0;
  let buffer = '';
  for (const char of withoutComments) {
    if (char === '{') depth += 1;
    if (char === '}') depth -= 1;
    if (depth === 0 && char !== '{' && char !== '}') buffer += char;
  }
  for (const line of buffer.split(';')) {
    const match = /^\s*(--[a-z0-9-]+)\s*:\s*([\s\S]+)$/i.exec(line);
    if (match) out[match[1]] = match[2].trim();
  }
  return out;
}

/**
 * Darkness rank of a zinc-ramp token value: higher = darker ink in light mode.
 * white 0, zinc-50 50 ... zinc-950 950, black 1000.
 */
function step(value: string): number {
  if (/--color-white\b/.test(value)) return 0;
  if (/--color-black\b/.test(value)) return 1000;
  const match = /--color-[a-z]+-(\d+)/.exec(value);
  if (!match) throw new Error(`not a ramp token: ${value}`);
  return Number(match[1]);
}

/**
 * WCAG contrast between two palette tokens.
 *
 * Tailwind ships its palette as OKLCH, so getting to a luminance means converting
 * OKLCH -> OKLab -> LMS -> linear sRGB, which is what the two functions below do.
 * The palette is read from the installed Tailwind rather than copied here, so the
 * assertion tracks the real values rather than a snapshot of them.
 */
const palette: Record<string, string> = (() => {
  const theme = fs.readFileSync(path.join(root, 'node_modules/tailwindcss/theme.css'), 'utf8');
  const out: Record<string, string> = {};
  for (const [, name, value] of theme.matchAll(/(--color-[a-z0-9-]+):\s*([^;]+);/g)) {
    out[name] = value.trim();
  }
  return out;
})();

/** Linear-light sRGB channels of a palette value (`oklch(...)`, `#fff` or `#000`). */
function linearRgb(value: string): [number, number, number] {
  const hex = /^#([0-9a-f]{3,6})$/i.exec(value.trim());
  if (hex) {
    const digits = hex[1].length === 3 ? [...hex[1]].map((d) => d + d).join('') : hex[1];
    return [0, 2, 4].map((i) => {
      const channel = parseInt(digits.slice(i, i + 2), 16) / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    }) as [number, number, number];
  }

  const oklch = /oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)/.exec(value);
  if (!oklch) throw new Error(`unsupported colour: ${value}`);
  const L = Number(oklch[1]) / 100;
  const C = Number(oklch[2]);
  const h = (Number(oklch[3]) * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s2 = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;

  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s2,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s2,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s2,
  ];
}

/** Resolves `var(--color-x)` against the Tailwind palette, then returns luminance. */
function luminance(tokenValue: string): number {
  const ref = /var\((--color-[a-z0-9-]+)\)/.exec(tokenValue);
  const raw = ref ? palette[ref[1]] : tokenValue;
  if (!raw) throw new Error(`palette miss: ${tokenValue}`);
  const [r, g, b] = linearRgb(raw).map((c) => Math.min(1, Math.max(0, c)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const rootVars = declarations(block(configCss, ':root'));
const darkVars = declarations(block(configCss, '.dark'));
const themeInline = declarations(block(configCss, '@theme inline'));
const themeVars = declarations(block(configCss, '@theme {'));

describe('S2-01 semantic colour tokens', () => {
  const semantic = ['mono', 'success', 'info', 'warning'];

  it.each(semantic)('defines --%s and its foreground in :root and .dark', (name) => {
    expect(rootVars[`--${name}`]).toBeTruthy();
    expect(rootVars[`--${name}-foreground`]).toBeTruthy();
    expect(darkVars[`--${name}`]).toBeTruthy();
    expect(darkVars[`--${name}-foreground`]).toBeTruthy();
  });

  it.each(semantic)('exposes --%s through @theme inline so the utility exists', (name) => {
    expect(themeInline[`--color-${name}`]).toBe(`var(--${name})`);
    expect(themeInline[`--color-${name}-foreground`]).toBe(`var(--${name}-foreground)`);
  });

  it.each(semantic)('pairs --%s with a foreground at 4.5:1 or better in light mode', (name) => {
    expect(contrast(rootVars[`--${name}`], rootVars[`--${name}-foreground`])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(semantic)('pairs --%s with a foreground at 4.5:1 or better in dark mode', (name) => {
    expect(contrast(darkVars[`--${name}`], darkVars[`--${name}-foreground`])).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps semantic ink legible as text on the page background', () => {
    // text-success / text-info / text-destructive are used as toast ink, so the
    // token has to work as ink on --background, not only as a solid fill.
    for (const name of ['success', 'info', 'warning', 'mono']) {
      expect(contrast(rootVars[`--${name}`], rootVars['--background']), `${name} light`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(darkVars[`--${name}`], darkVars['--background']), `${name} dark`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps secondary ink legible on the dark card', () => {
    expect(contrast(darkVars['--muted-foreground'], darkVars['--card'])).toBeGreaterThanOrEqual(4.5);
  });

  it('renders text-mono darker than body text in light mode', () => {
    expect(step(rootVars['--mono'])).toBeGreaterThan(step(rootVars['--secondary-foreground']));
    expect(step(rootVars['--mono'])).toBeGreaterThan(step(rootVars['--muted-foreground']));
  });

  it('renders text-mono brighter than body text in dark mode', () => {
    expect(step(darkVars['--mono'])).toBeLessThan(step(darkVars['--secondary-foreground']));
    expect(step(darkVars['--mono'])).toBeLessThan(step(darkVars['--muted-foreground']));
  });

  it('colours toast success and error ink', () => {
    const sonner = read('components/ui/sonner.tsx');
    expect(sonner).toContain('[&_[data-type=success]_[data-title]]:text-success');
    expect(sonner).toContain('[&_[data-type=error]_[data-title]]:text-destructive');
    // text-success only exists once --color-success is a theme colour.
    expect(themeInline['--color-success']).toBe('var(--success)');
    expect(themeInline['--color-destructive']).toBe('var(--destructive)');
  });
});

describe('S2-02 dark surface ramp', () => {
  it('gives --background, --card and --popover three distinct lightness steps', () => {
    const steps = [darkVars['--background'], darkVars['--card'], darkVars['--popover']].map(step);
    expect(new Set(steps).size).toBe(3);
    // background is the deepest, popover the most raised.
    expect(steps[0]).toBeGreaterThan(steps[1]);
    expect(steps[1]).toBeGreaterThan(steps[2]);
  });

  it('renders the active tab lighter than its track', () => {
    const tabs = read('components/ui/tabs.tsx');
    expect(tabs).toContain("default: 'bg-muted p-1'");
    expect(tabs).toContain('data-[state=active]:bg-popover');
    expect(step(darkVars['--popover'])).toBeLessThan(step(darkVars['--muted']));
  });
});

describe('S2-03 type scale and typeface', () => {
  const scale: Array<[string, string, string | null]> = [
    ['2xl', '-0.02em', '1.15'],
    ['xl', '-0.015em', '1.2'],
    ['lg', '-0.01em', '1.3'],
    ['base', '0em', '1.5'],
    ['xs', '0.01em', null],
    ['2xs', '0.02em', null],
  ];

  it.each(scale)('bakes tracking and leading into text-%s', (size, tracking, leading) => {
    expect(themeVars[`--text-${size}--letter-spacing`]).toBe(tracking);
    if (leading) expect(themeVars[`--text-${size}--line-height`]).toBe(leading);
  });

  it('resolves --font-sans to Inter', () => {
    expect(themeVars['--font-sans']).toContain('var(--font-inter)');
    expect(themeVars['--font-sans']).toContain('ui-sans-serif');

    const layout = read('app/layout.tsx');
    expect(layout).toContain("variable: '--font-inter'");
    // The variable has to sit on <html>, which is where preflight reads --font-sans.
    expect(/<html[\s\S]*?inter\.variable/.test(layout)).toBe(true);
  });

  it('turns optical sizing on for the body', () => {
    expect(stylesCss).toMatch(/body\s*\{[^}]*font-optical-sizing:\s*auto/);
  });
});

describe('S2-04 accessibility preference blocks', () => {
  const reducedMotion = () => block(stylesCss, '@media (prefers-reduced-motion: reduce)');
  const reducedTransparency = () => block(stylesCss, '@media (prefers-reduced-transparency: reduce)');
  const moreContrast = () => block(stylesCss, '@media (prefers-contrast: more)');

  it('turns overlay slides and zooms into 150ms fades', () => {
    const reduced = reducedMotion();
    expect(reduced).toContain('[data-slot$=\'-content\']');
    expect(reduced).toContain('[data-radix-popper-content-wrapper]');
    for (const v of [
      '--tw-enter-translate-x',
      '--tw-enter-translate-y',
      '--tw-exit-translate-x',
      '--tw-exit-translate-y',
    ]) {
      expect(reduced).toMatch(new RegExp(`${v}:\\s*0`));
    }
    expect(reduced).toMatch(/--tw-enter-scale:\s*1/);
    expect(reduced).toMatch(/--tw-exit-scale:\s*1/);
    expect(reduced).toMatch(/animation-duration:\s*150ms/);
  });

  it('excludes dialog/sheet content from the 150ms CSS transition (S8-01 fix)', () => {
    // Radix `asChild` merges DialogContent/SheetContent straight onto the `motion.div`
    // Framer Motion animates (dialog.tsx, sheet.tsx), so this rule's own
    // `transition-duration: 150ms` would otherwise land on that very node and smear the
    // JS spring's one-frame opacity commit (`REDUCED_MOTION_TRANSITION`, lib/motion.ts)
    // over 150ms instead of applying it instantly.
    const reduced = reducedMotion();
    const selector = /^[^{]*\{/.exec(reduced)?.[0] ?? '';
    expect(selector).toMatch(/\[data-slot\$='-content'\]:not\(\[data-slot='dialog-content'\]\):not\(\[data-slot='sheet-content'\]\)/);
    // AlertDialog joined the same asChild/motion.div pattern (M2-05), so it
    // needs the same exclusion for the same reason.
    expect(selector).toContain("[data-slot='alert-dialog-content']");
  });

  it('gives every -content slot the reduced-motion rule to bite on', () => {
    // The rule keys off [data-slot$='-content'], so a primitive without the attribute
    // keeps sliding under prefers-reduced-motion.
    for (const file of ['dialog.tsx', 'alert-dialog.tsx', 'sheet.tsx']) {
      expect(read(`components/ui/${file}`), file).toMatch(/data-slot="[a-z-]+-content"/);
    }
  });

  it('stops pulse and bounce but keeps spinners spinning', () => {
    const reduced = reducedMotion();
    expect(reduced).toContain('.animate-pulse');
    expect(reduced).toContain('.animate-bounce');
    expect(reduced).not.toContain('.animate-spin');
  });

  it('drops the backdrop filter and uses a 72% scrim under reduced transparency', () => {
    const reducedTransparencyBlock = reducedTransparency();
    expect(reducedTransparencyBlock).toContain('backdrop-filter: none');
    expect(reducedTransparencyBlock).toContain('[data-pinned]');
    expect(reducedTransparencyBlock).toContain('dialog-overlay');
    expect(reducedTransparencyBlock).toMatch(/--scrim:[^;]*72%/);
  });

  it('drops the backdrop filter and uses a 72% scrim under prefers-contrast: more', () => {
    const moreContrastBlock = moreContrast();
    expect(moreContrastBlock).toContain('backdrop-filter: none');
    expect(moreContrastBlock).toContain('[data-pinned]');
    expect(moreContrastBlock).toMatch(/--scrim:[^;]*72%/);
  });
});

describe('S2-05 materials and the z-scale', () => {
  // Only the steps with a consumer are defined; a thin material, the --elev-* shadow
  // steps and an overlay/toast z step go in when one arrives.
  const materialTokens = ['--material-regular', '--material-thick', '--scrim'];
  const zTokens = ['--z-header', '--z-sidebar', '--z-banner', '--z-modal'];

  it.each(materialTokens)('defines %s in :root and .dark', (token) => {
    expect(rootVars[token]).toBeTruthy();
    expect(darkVars[token]).toBeTruthy();
  });

  it.each(zTokens)('defines %s once, as a named step', (token) => {
    expect(rootVars[token]).toMatch(/^\d+$/);
  });

  it('orders the z-scale so the banner sits above the shell and below the lightbox', () => {
    expect(Number(rootVars['--z-header'])).toBeLessThan(Number(rootVars['--z-sidebar']));
    expect(Number(rootVars['--z-sidebar'])).toBeLessThan(Number(rootVars['--z-banner']));
    expect(Number(rootVars['--z-banner'])).toBeLessThan(Number(rootVars['--z-modal']));
  });

  it('ships the material utilities and the hairline edge', () => {
    for (const name of ['material-regular', 'material-thick', 'material-edge']) {
      expect(stylesCss).toContain(`@utility ${name}`);
    }
  });

  it('dresses the header and the sidebar in materials, not a flat background', () => {
    const header = read('app/components/layouts/demo1/components/header.tsx');
    const sidebar = read('app/components/layouts/demo1/components/sidebar.tsx');
    expect(header).toContain('material-regular');
    expect(header).not.toContain('bg-background');
    expect(sidebar).toContain('material-thick');
    expect(sidebar).not.toContain('bg-background');
  });

  it('offsets the header and the sidebar below the impersonation banner', () => {
    const offset = 'top-[var(--impersonation-banner-height,0px)]';
    expect(read('app/components/layouts/demo1/components/header.tsx')).toContain(offset);
    expect(read('app/components/layouts/demo1/components/sidebar.tsx')).toContain(`lg:${offset}`);
  });

  it('leaves no ad-hoc z-[N] in the shell', () => {
    const shell = [
      'app/components/layouts/demo1/components/header.tsx',
      'app/components/layouts/demo1/components/sidebar.tsx',
      'components/impersonation/ImpersonationBanner.tsx',
    ];
    for (const file of shell) {
      expect(read(file), file).not.toMatch(/\bz-\[/);
      expect(read(file), file).not.toMatch(/\bz-\d+\b/);
      expect(read(file), file).toMatch(/z-\(--z-[a-z]+\)/);
    }
  });
});

describe('S2-06 motion tokens', () => {
  const uiDir = path.join(root, 'components/ui');
  const uiFiles = fs.readdirSync(uiDir).filter((f) => f.endsWith('.tsx'));

  /**
   * `animate-caret-blink duration-1000` sets an animation PERIOD, not a transition,
   * so it is not one of the three motion steps. Any other literal is a regression.
   */
  const animationPeriodAllowlist = new Set(['input-otp.tsx']);

  it('defines --ease-standard and the three durations', () => {
    expect(rootVars['--ease-standard']).toMatch(/^cubic-bezier\(/);
    expect(rootVars['--duration-fast']).toBe('150ms');
    expect(rootVars['--duration-base']).toBe('200ms');
    expect(rootVars['--duration-slow']).toBe('300ms');
  });

  it('leaves no literal transition duration in components/ui', () => {
    const offenders = uiFiles.filter(
      (file) => !animationPeriodAllowlist.has(file) && LITERAL_DURATION.test(fs.readFileSync(path.join(uiDir, file), 'utf8')),
    );
    expect(offenders).toEqual([]);
  });

  it('leaves no bespoke bezier in a components/ui class string', () => {
    const offenders = uiFiles.filter((file) =>
      /transition-timing-function:\s*cubic-bezier/.test(fs.readFileSync(path.join(uiDir, file), 'utf8')),
    );
    expect(offenders).toEqual([]);
  });

  it('gives the sheet one shared open/close transition, not a bespoke CSS one (S8-01)', () => {
    // The slide is a JS spring now, not a `data-state`-keyed CSS transition - a
    // bespoke duration per direction is exactly the drift this token exists to
    // prevent, and a spring can't have one anyway (its settle time emerges from
    // the spring, it has no fixed duration to key per direction).
    const sheet = read('components/ui/sheet.tsx');
    expect(sheet).not.toMatch(/data-\[state=(open|closed)\]:duration-/);
    expect(sheet).not.toMatch(LITERAL_DURATION);
    expect(sheet).toContain("from '@/lib/motion'");
    expect(sheet).toContain('surfaceTransition(');
  });
});

/**
 * M1-02 .. M1-04 - motion perimeter hygiene, widened from `components/ui`
 * (S2-06 above) out to `app/**`, `components/**` and `css/**`. The audit that
 * sized this slice found 12 `transition-all` sites and 10 literal `duration-N`
 * classes outside `components/ui`; this is the guardrail that keeps both at
 * zero (or explicitly, narrowly allowlisted) from here on.
 *
 * Same reasoning as the other inventory tests in this repo: these are source
 * scans, not renders, because the property being asserted ("nothing in the
 * whole tree does X") is not one a mounted component can speak for.
 */
describe('M1 motion perimeter hygiene', () => {
  /**
   * `app/components/layouts/demo2` through `demo10` are vendor Metronic shells
   * with zero live routes - see the identical exclusion, and its justification,
   * in `components/ui/a11y-guardrails.inventory.test.ts`. Scanning them here
   * would force a "fix" on dead markup nothing in the app can reach; `demo1` (the
   * layout `app/(protected)/layout.tsx` actually mounts) is NOT excluded.
   */
  const DEAD_LAYOUT_PREFIX = /^app\/components\/layouts\/demo(?:[2-9]|10)\//;

  function sourceFiles(): string[] {
    const out: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
        const rel = path.posix.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === 'node_modules' || entry.name === '.next') continue;
          walk(rel);
        } else if (/\.(tsx?|css)$/.test(entry.name) && !entry.name.includes('.test.')) {
          if (DEAD_LAYOUT_PREFIX.test(rel)) continue;
          out.push(rel);
        }
      }
    };
    walk('app');
    walk('components');
    walk('css');
    // `lib/motion.ts` is where the springs and the reduced-motion transition
    // live, so a raw cubic-bezier or a hard-coded duration there is exactly the
    // leak these scans exist to catch.
    walk('lib');
    return out;
  }

  const files = sourceFiles();

  /**
   * A comment MENTIONING a class token (the OTP caret note) must not read as the
   * class itself. Blanks out comment bodies char-by-char rather than deleting
   * them, so every line number below the comment stays what `grep`/the editor
   * would report - a multi-line `/* ... *\/` collapsed by a plain `.replace(..., '')`
   * shifts every later match's reported line by the comment's own height.
   */
  function stripBlockComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
  }

  /**
   * An allowlist entry is a claim about ONE line. When the line moves, or the
   * class it exempts leaves it, the entry stops describing anything and silently
   * exempts whatever moved in - so a key that no longer matches its own matcher
   * fails the same test its live siblings pass.
   */
  function staleAllowlistKeys(keys: string[], matches: (line: string) => boolean): string[] {
    return keys.filter((key) => {
      const at = key.lastIndexOf(':');
      const file = key.slice(0, at);
      if (!fs.existsSync(path.join(root, file))) return true;
      const lines = stripBlockComments(read(file)).split('\n');
      return !matches(lines[Number(key.slice(at + 1)) - 1] ?? '');
    });
  }

  /**
   * Every string literal in a source file, with the line its opening quote sits on.
   *
   * A class string is the only place a bare `transition` can be a Tailwind
   * utility, so the M1-02 scan below needs literals, not lines. One pass over the
   * characters rather than a per-line regex, because the two shapes that matter
   * most both defeat a per-line one: a template literal opened by
   * `` className={`... transition ${ `` closes on a LATER line (five of the
   * offenders this guard exists for are exactly that), and a `//` comment can
   * carry an apostrophe that would otherwise read as an opening quote.
   *
   * `${...}` interpolations are blanked (brace-balanced) so an expression inside
   * one cannot donate tokens to the literal that holds it.
   */
  function stringLiterals(src: string): { text: string; line: number }[] {
    const out: { text: string; line: number }[] = [];
    let line = 1;
    let i = 0;
    while (i < src.length) {
      const ch = src[i];
      if (ch === '\n') {
        line += 1;
        i += 1;
      } else if (ch === '/' && src[i + 1] === '/') {
        while (i < src.length && src[i] !== '\n') i += 1;
      } else if (ch === '/' && src[i + 1] === '*') {
        i += 2;
        while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) {
          if (src[i] === '\n') line += 1;
          i += 1;
        }
        i += 2;
      } else if (ch === "'" || ch === '"' || ch === '`') {
        const quote = ch;
        const startLine = line;
        let text = '';
        i += 1;
        while (i < src.length && src[i] !== quote) {
          if (src[i] === '\\') {
            i += 2;
            text += ' ';
          } else if (src[i] === '\n') {
            line += 1;
            text += '\n';
            i += 1;
          } else if (quote === '`' && src[i] === '$' && src[i + 1] === '{') {
            const interpolationLine = line;
            i += 1; // the `{` itself, so the brace count below starts at 1
            const from = i + 1;
            let depth = 0;
            do {
              if (src[i] === '{') depth += 1;
              else if (src[i] === '}') depth -= 1;
              else if (src[i] === '\n') line += 1;
              i += 1;
            } while (i < src.length && depth > 0);
            // The expression is scanned in its own right: a class string can hide
            // one level down, as `${interactive ? 'hover:bg-muted/70 transition' : ''}`.
            for (const nested of stringLiterals(src.slice(from, i - 1))) {
              out.push({ text: nested.text, line: interpolationLine + nested.line - 1 });
            }
            text += ' ';
          } else {
            text += src[i];
            i += 1;
          }
        }
        i += 1;
        out.push({ text, line: startLine });
      } else {
        i += 1;
      }
    }
    return out;
  }

  /**
   * A whitespace-run token that looks like a Tailwind utility: lower-case head,
   * then at least one of `-` `:` `/` `[` (`w-full`, `hover:bg-muted/70`,
   * `-translate-y-1/2`, `text-2xs`, `active:scale-[0.97]`). Deliberately shallow -
   * it only has to tell a class string apart from a sentence, and every sentence
   * in this tree that contains the word "transition" ("Failed to create the
   * transition", "Who can use this transition") carries no token of this shape.
   */
  const UTILITY_TOKEN = /^-?[a-z][a-z0-9.]*(?:[-:/[][^\s]*)+$/;

  describe('M1-02 no transition-all, no bare `transition` shorthand', () => {
    it('leaves zero transition-all sites (audit baseline: 12)', () => {
      const offenders: string[] = [];
      for (const file of files) {
        const src = stripBlockComments(read(file));
        src.split('\n').forEach((line, i) => {
          if (/\btransition-all\b/.test(line) || /transition:\s*all\b/.test(line)) {
            offenders.push(`${file}:${i + 1}`);
          }
        });
      }
      expect(offenders).toEqual([]);
    });

    it('leaves zero bare `transition` (multi-property shorthand) utility classes', () => {
      // A bare `transition` is only a Tailwind utility, not the English word (a
      // "status transition", a destructured `transition` from useSortable /
      // lib/motion, a "Delete transition" aria-label), when it stands as its own
      // token INSIDE A STRING LITERAL that also carries another Tailwind utility.
      //
      // The first cut of this guard gated on the same LINE also naming
      // `duration-` or `ease-`, on the theory that every real class string pairs
      // the two. It does not: a bare `transition` is exactly the site that
      // inherits both from the theme and names neither, so that matcher fired on
      // 0 lines while 19 bare `transition` utilities survived in `app/**`.
      const offenders: string[] = [];
      for (const file of files) {
        for (const literal of stringLiterals(read(file))) {
          const tokens = literal.text.split(/\s+/).filter(Boolean);
          if (!tokens.includes('transition')) continue;
          if (!tokens.some((t) => t !== 'transition' && UTILITY_TOKEN.test(t))) continue;
          // A template literal can open on one line and carry the offending token
          // on another, so report the token's line, not the quote's.
          const at = literal.text.search(/(^|\s)transition(\s|$)/);
          const ahead = literal.text.slice(0, Math.max(at, 0)).split('\n').length - 1;
          offenders.push(`${file}:${literal.line + ahead}`);
        }
      }
      expect(offenders).toEqual([]);
    });
  });

  describe('M1-03 no literal duration-<N>, no ease-in on an entering element', () => {
    /**
     * Every entry here is a documented exception, not a miss: the OTP caret's
     * blink PERIOD, not a transition duration. The three countdown/panel bars
     * this allowlist used to carry are gone - M3 converted them to a `scaleX`
     * transform on the tokens, so they no longer name a literal duration.
     */
    const DURATION_ALLOWLIST: Record<string, string> = {
      'components/ui/input-otp.tsx:54': 'OTP caret blink PERIOD, not a transition duration',
    };

    it('leaves zero literal duration-<N> classes outside the allowlist (audit baseline: 10)', () => {
      expect(staleAllowlistKeys(Object.keys(DURATION_ALLOWLIST), (line) => LITERAL_DURATION.test(line))).toEqual([]);

      const offenders: string[] = [];
      for (const file of files) {
        // css/** is out of scope for this assertion (M1-03 globs are app/** and
        // components/**); css/** literal timings are covered by M1-02 and the
        // ease-in check below instead.
        if (!file.startsWith('app/') && !file.startsWith('components/')) continue;
        const src = stripBlockComments(read(file));
        src.split('\n').forEach((line, i) => {
          if (LITERAL_DURATION.test(line)) {
            const key = `${file}:${i + 1}`;
            if (!DURATION_ALLOWLIST[key]) offenders.push(key);
          }
        });
      }
      expect(offenders).toEqual([]);
    });

    /**
     * The two accepted alternating pulses - guide-spotlight and takeover-flash -
     * repeat forever and never "enter", which is what the hard-fail in
     * DESIGN-LANGUAGE.md section 3 actually bans.
     *
     * Everything else is banned FLAT, entering or not, and that is a choice
     * rather than a shortcut in the matcher: `ease-in` accelerating out of rest
     * is the one curve the house language has no use for, and deciding "is this
     * element entering?" from source text is guesswork. An exit that genuinely
     * wants it argues its case here, on its own line, the way these two did.
     */
    const EASE_IN_ALLOWLIST = new Set(['css/styles.css:49', 'css/styles.css:73']);

    it('leaves zero ease-in/ease-in-out on an entering element outside the allowlist', () => {
      expect(staleAllowlistKeys([...EASE_IN_ALLOWLIST], (line) => /\bease-in\b/.test(line))).toEqual([]);

      const offenders: string[] = [];
      for (const file of files) {
        const src = stripBlockComments(read(file));
        src.split('\n').forEach((line, i) => {
          if (/\bease-in\b/.test(line)) {
            const key = `${file}:${i + 1}`;
            if (!EASE_IN_ALLOWLIST.has(key)) offenders.push(key);
          }
        });
      }
      expect(offenders).toEqual([]);
    });
  });

  describe('M1-04 raw cubic-bezier stays in config.reui.css only', () => {
    it('leaves zero raw cubic-bezier( outside css/config.reui.css', () => {
      const offenders: string[] = [];
      for (const file of files) {
        if (file === 'css/config.reui.css') continue;
        // A comment quoting the house curve, next to the token that replaced it,
        // is documentation and not a second curve.
        stripBlockComments(read(file))
          .split('\n')
          .forEach((line, i) => {
            if (line.includes('cubic-bezier(')) offenders.push(`${file}:${i + 1}`);
          });
      }
      expect(offenders).toEqual([]);
    });
  });

  describe('M1-07 drawer overlay shares the one scrim', () => {
    it('drawer.tsx overlay uses OVERLAY_CLASS_STATIC instead of its own bg-black/80', () => {
      const drawer = read('components/ui/drawer.tsx');
      expect(drawer).toContain('OVERLAY_CLASS_STATIC');
      expect(drawer).not.toContain('bg-black/80');
    });
  });

  describe('M1-01 the shared press token carries the house curve', () => {
    it('PRESSED_CLASS names duration-fast and ease-standard', () => {
      const primitiveClasses = read('components/ui/primitive-classes.ts');
      expect(primitiveClasses).toContain('duration-(--duration-fast)');
      expect(primitiveClasses).toContain('ease-(--ease-standard)');
    });

    it('@theme points the Tailwind transition-* utility defaults at the same tokens', () => {
      expect(themeVars['--default-transition-timing-function']).toBe('var(--ease-standard)');
      expect(themeVars['--default-transition-duration']).toBe('var(--duration-fast)');
    });
  });

  /**
   * One more widening, after every fix above: no `transition-[...]` naming a
   * layout-affecting property (`width`, `height`, `margin*`, `padding*`,
   * `inset*`) outside a narrow allowlist. This allowlist used to carry the
   * countdown/budget bars, but M3 converted every one of them to a `scaleX`
   * transform instead, so it is empty. The three accordion/collapsible
   * content sites never reach this list: their transition was DROPPED
   * outright in M1-02 (their height comes from the animate-accordion and
   * animate-collapsible keyframes, not a transition).
   */
  describe('M1 no transition-[width|height|margin|padding|inset] outside M3', () => {
    const PROPERTY_ALLOWLIST: Record<string, string> = {};
    const LAYOUT_PROPERTY =
      /transition-\[[^\]]*\b(width|height|margin(?:-[a-z]+)?|padding(?:-[a-z]+)?|inset(?:-[a-z]+)?)\b[^\]]*\]/;

    it('leaves zero transition-[width|height|margin|padding|inset] outside the M3 allowlist', () => {
      expect(staleAllowlistKeys(Object.keys(PROPERTY_ALLOWLIST), (line) => LAYOUT_PROPERTY.test(line))).toEqual([]);

      const offenders: string[] = [];
      for (const file of files) {
        const src = stripBlockComments(read(file));
        src.split('\n').forEach((line, i) => {
          if (LAYOUT_PROPERTY.test(line)) {
            const key = `${file}:${i + 1}`;
            if (!PROPERTY_ALLOWLIST[key]) offenders.push(key);
          }
        });
      }
      expect(offenders).toEqual([]);
    });
  });
});
