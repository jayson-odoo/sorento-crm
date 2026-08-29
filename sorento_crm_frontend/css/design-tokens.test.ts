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
  const materialTokens = ['--material-thin', '--material-regular', '--material-thick', '--scrim', '--elev-1', '--elev-3'];
  const zTokens = ['--z-header', '--z-sidebar', '--z-banner', '--z-overlay', '--z-modal', '--z-toast'];

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
    expect(Number(rootVars['--z-banner'])).toBeLessThan(Number(rootVars['--z-overlay']));
    expect(Number(rootVars['--z-overlay'])).toBeLessThan(Number(rootVars['--z-modal']));
    expect(Number(rootVars['--z-modal'])).toBeLessThan(Number(rootVars['--z-toast']));
  });

  it('ships the material utilities and the hairline edge', () => {
    for (const name of ['material-thin', 'material-regular', 'material-thick', 'material-edge']) {
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
      (file) => !animationPeriodAllowlist.has(file) && /\bduration-\d+/.test(fs.readFileSync(path.join(uiDir, file), 'utf8')),
    );
    expect(offenders).toEqual([]);
  });

  it('leaves no bespoke bezier in a components/ui class string', () => {
    const offenders = uiFiles.filter((file) =>
      /transition-timing-function:\s*cubic-bezier/.test(fs.readFileSync(path.join(uiDir, file), 'utf8')),
    );
    expect(offenders).toEqual([]);
  });

  it('gives the sheet equal open and close durations', () => {
    const sheet = read('components/ui/sheet.tsx');
    expect(sheet).not.toMatch(/data-\[state=(open|closed)\]:duration-/);
    expect(sheet).toContain('duration-(--duration-slow)');
    expect(sheet).toContain('ease-(--ease-standard)');
  });
});
