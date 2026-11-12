/**
 * UI v2 holistic guard (UAC G-1, D-6; rules R15/R16; decisions D6, D8, D9, D10).
 *
 * Every v2 decision is ONE shared token, component or pattern. This walk fails the moment a file works around
 * one. All five rules have ZERO allowance: there is no allowlist here, a hit is a defect to fix in the shared
 * thing, not a line to add to a list.
 *
 *   1. D6   No raw Tailwind palette class (`bg-blue-600`, `text-amber-900`, ...) in `components/v2` or
 *           `lib/theme`. Colour comes from tokens (`bg-primary`, `text-muted-foreground`, `bg-warn`, ...).
 *   2. D6   No hex colour literal (`#246bdd`) in `components/v2` or `lib/theme`, except `lib/theme/presets.ts`
 *           (the one file that names the five brand inputs).
 *   3. D9   No `bg-primary` fill on a SELECTED state in `components/v2`. A selected toggle, toggle-group item or
 *           pill tab uses `--toggle-selected-bg/fg` (soft tint, primary text), so the only filled control is the
 *           primary action.
 *   4. D8   No `PhoneCard*`-like list-card component defined anywhere under `app/` or `components/` except
 *           `components/v2/grid/PhoneCardList.tsx`, the one generic card driven by the grid columns.
 *   5. D10  `usePageView` is not referenced outside `components/v2/shell` (D-6): pages never import the hook,
 *           the shell mounts it once.
 *
 * Source scan with comments stripped (prose that names a pattern is not a hit). Test files are not scanned.
 * Detector self-checks at the bottom keep the scan from going vacuous if a regex is edited.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const V2_ROOTS = ['components/v2', 'lib/theme'];
const PRODUCT_ROOTS = ['app', 'components', 'lib', 'hooks'];

/** The one file allowed to carry brand hex literals. */
const HEX_ALLOWED = ['lib/theme/presets.ts'];
/** The one file allowed to define a phone card component. */
const PHONE_CARD_HOME = 'components/v2/grid/PhoneCardList.tsx';
/** The only directory that may reference usePageView. */
const PAGE_VIEW_HOME = 'components/v2/shell/';

const PALETTE_NAMES =
  'red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone';
const RAW_PALETTE = new RegExp(
  `\\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|divide|decoration|shadow|accent|caret|placeholder)-(?:${PALETTE_NAMES})-\\d{2,3}\\b`,
);
const HEX_LITERAL =
  /(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/;
/** A state selector that paints a selected state with the solid primary fill. */
const SELECTED_VARIANT_PRIMARY =
  /(?:data-\[state=(?:on|active|checked|selected)\]|data-\[selected[^\]]*\]|aria-(?:selected|pressed|checked)|aria-\[(?:selected|pressed|checked)[^\]]*\]|data-(?:selected|active)):bg-primary(?![\w/-])/;
/** A line that branches on a selected-ish flag and names `bg-primary` as a solid fill. */
const SELECTED_BRANCH_PRIMARY =
  /\b(?:selected|isSelected|active|isActive|pressed|isPressed|checked|isChecked)\b[^\n]*\bbg-primary(?![\w/-])/;
const PHONE_CARD_DEF =
  /\b(?:function|const|class)\s+\w*(?:Phone|Mobile)\w*Card\w*/;
const USE_PAGE_VIEW = /\busePageView\b/;

/** Drop block and line comments so prose that names the pattern is not a hit. */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`])\/\/[^\n]*/g, '$1');
}

function walkFiles(roots: string[]): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const rel = full.split(path.sep).join('/');
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (
        (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) &&
        !entry.name.endsWith('.d.ts') &&
        !/\.(test|spec)\./.test(entry.name) &&
        !/\.inventory\./.test(entry.name)
      ) {
        out.push(rel);
      }
    }
  };
  for (const root of roots) walk(root);
  return out;
}

const hits = (files: string[], test: (src: string) => boolean) =>
  files.filter((f) => test(stripComments(fs.readFileSync(f, 'utf8'))));

describe('UI v2 holistic guard (zero allowance)', () => {
  it('D6: no raw Tailwind palette class in components/v2 or lib/theme', () => {
    expect(hits(walkFiles(V2_ROOTS), (s) => RAW_PALETTE.test(s))).toEqual([]);
  });

  it('D6: no hex colour literal in components/v2 or lib/theme except lib/theme/presets.ts', () => {
    const files = walkFiles(V2_ROOTS).filter((f) => !HEX_ALLOWED.includes(f));
    expect(hits(files, (s) => HEX_LITERAL.test(s))).toEqual([]);
  });

  it('D9: no bg-primary fill on a selected state in components/v2', () => {
    const files = walkFiles(['components/v2']);
    expect(
      hits(
        files,
        (s) =>
          SELECTED_VARIANT_PRIMARY.test(s) || SELECTED_BRANCH_PRIMARY.test(s),
      ),
    ).toEqual([]);
  });

  it('D8: no PhoneCard-like component is defined outside components/v2/grid/PhoneCardList.tsx', () => {
    const files = walkFiles(['app', 'components']).filter(
      (f) => f !== PHONE_CARD_HOME,
    );
    expect(hits(files, (s) => PHONE_CARD_DEF.test(s))).toEqual([]);
  });

  it('D10 / D-6: usePageView is referenced only inside components/v2/shell', () => {
    const files = walkFiles(PRODUCT_ROOTS).filter(
      (f) => !f.startsWith(PAGE_VIEW_HOME),
    );
    expect(hits(files, (s) => USE_PAGE_VIEW.test(s))).toEqual([]);
  });
});

describe('detector self-checks', () => {
  it('raw palette matches numbered scale classes and not tokens', () => {
    for (const bad of [
      'bg-blue-600',
      'text-amber-900',
      'border-zinc-200',
      'hover:bg-red-50',
      'ring-indigo-500',
    ]) {
      expect(RAW_PALETTE.test(bad), bad).toBe(true);
    }
    for (const ok of [
      'bg-primary',
      'bg-primary-soft',
      'text-muted-foreground',
      'bg-warn',
      'border-border',
    ]) {
      expect(RAW_PALETTE.test(ok), ok).toBe(false);
    }
  });

  it('hex literal matches colours and not entities or words', () => {
    for (const bad of ["'#246bdd'", '"#fff"', 'fill="#3b82f680"'])
      expect(HEX_LITERAL.test(bad), bad).toBe(true);
    for (const ok of ['&#123;', 'href="#section"', 'const id = a#b', 'value'])
      expect(HEX_LITERAL.test(ok), ok).toBe(false);
  });

  it('selected-state primary fill is caught in variant and branch form, soft tint is not', () => {
    for (const bad of [
      'data-[state=on]:bg-primary',
      'aria-selected:bg-primary text-primary-foreground',
      "isSelected ? 'bg-primary text-white' : 'bg-muted'",
      "className={cn('px-2', active && 'bg-primary')}",
    ]) {
      expect(
        SELECTED_VARIANT_PRIMARY.test(bad) || SELECTED_BRANCH_PRIMARY.test(bad),
        bad,
      ).toBe(true);
    }
    for (const ok of [
      'data-[state=on]:bg-(--toggle-selected-bg)',
      'data-[state=on]:bg-primary-soft',
      "isSelected ? 'bg-(--toggle-selected-bg)' : 'bg-muted'",
      "<Button variant='primary'>Save</Button>",
    ]) {
      expect(
        SELECTED_VARIANT_PRIMARY.test(ok) || SELECTED_BRANCH_PRIMARY.test(ok),
        ok,
      ).toBe(false);
    }
  });

  it('phone card definitions and usePageView references are caught', () => {
    for (const bad of [
      'function PhoneCard()',
      'const MobileOrderCard = ()',
      'class PhoneCardRow',
    ]) {
      expect(PHONE_CARD_DEF.test(bad), bad).toBe(true);
    }
    expect(PHONE_CARD_DEF.test('function CardHeader()')).toBe(false);
    expect(
      USE_PAGE_VIEW.test("import { usePageView } from './usePageView'"),
    ).toBe(true);
    expect(USE_PAGE_VIEW.test('usePageViewCount')).toBe(false);
  });

  it('comment stripping hides prose but keeps code and URLs', () => {
    expect(stripComments('// bg-blue-600 is banned\nconst a = 1;')).not.toMatch(
      /bg-blue-600/,
    );
    expect(stripComments('/* #fff */ const a = 1;')).not.toMatch(/#fff/);
    expect(stripComments("const u = 'http://x.test'; // note")).toMatch(
      /http:\/\/x\.test/,
    );
  });
});
