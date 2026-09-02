/**
 * S4-04 - the screens the audit found broken at 375, and the raw tables.
 *
 * Every item here is a layout fact: a class that has to be on an element for the
 * screen to survive a phone. jsdom has no layout engine, so a render test can
 * only read back the same class names this reads out of the source, at the cost
 * of standing up each screen's hooks. What it cannot do either way is prove the
 * pixels; that is the recorded agent-browser run at 375 the UAC asks for. What
 * this file IS for is stopping the fix being deleted by the next person editing
 * that line, and pinning the raw-table sweep so table number 36 arrives wrapped.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

function read(file: string): string {
  return fs.readFileSync(file, 'utf8');
}

/** Every `.tsx` under `app/` and `components/`, tests excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  walk('app');
  walk('components');
  return out;
}

/**
 * Tables whose scroll container is real but out of this scan's reach, with the
 * reason. Each is re-checked below, so an entry cannot quietly become a lie.
 */
const SCROLLER_OUT_OF_REACH = new Map<string, string>([
  ['components/ui/data-grid-table.tsx', 'the shared grid IS the scroller'],
  [
    'app/(protected)/scm/components/ProductListDialog.tsx',
    'DialogBody is the scroller, past the loading and empty branches',
  ],
  [
    'app/(protected)/master-data-management/product-categories/components/CategoryTree.tsx',
    'CategoriesList wraps it in the ScrollArea; a second one here scrolled nothing',
  ],
]);

/**
 * Is the element on line `i` inside a scroll container?
 *
 * A window of preceding lines is not enough, and got this wrong twice. A
 * `</ScrollArea>` closing the PREVIOUS sibling reads as a scroller if you only
 * grep the window, which is how AIExtractDialog's second table passed while
 * standing bare. So `<ScrollArea>` is matched by depth walking backwards: an
 * opener with no matching close below it is a real ancestor.
 *
 * An `overflow` class still uses a window, because it can be on any wrapper and
 * carries no closing tag to count. Fourteen lines is what the tree needs.
 */
function insideScroller(lines: string[], i: number): boolean {
  let closes = 0;
  for (let k = i - 1; k >= 0; k--) {
    const line = lines[k];
    closes += (line.match(/<\/ScrollArea>/g) ?? []).length;
    const opens = (line.match(/<ScrollArea[\s>]/g) ?? []).length;
    for (let n = 0; n < opens; n += 1) {
      if (closes > 0) closes -= 1;
      else return true; // an opener still standing open above us
    }
    if (i - k <= 14 && /overflow-(x-)?(auto|scroll)/.test(line)) return true;
  }
  return false;
}

describe('Mobile one-offs (S4-04)', () => {
  it('S4-04: Product Categories scrolls sideways and pins the Name column', () => {
    const src = read(
      'app/(protected)/master-data-management/product-categories/components/CategoryTree.tsx',
    );
    // Percentage `<col>` widths inside `table-fixed` are what squeezed six
    // columns into 375 and cut the category name to three characters.
    expect(src).not.toContain('<colgroup>');
    expect(src).not.toContain('table-fixed');
    // The identifier stays put while the rest scrolls, as the DataGrid does...
    expect(src).toContain('sticky start-0');
    // ...which needs `border-separate`: a sticky cell in a COLLAPSED table has
    // its borders painted by the table, so the pin loses its rules and the
    // scrolling columns show through it.
    expect(src).toContain('border-separate border-spacing-0');
    expect(src).not.toContain('border-collapse');
    // And a pin the scrolling columns cannot be read through. It carries the
    // ROW's tint over an opaque `::before` base, so it is the row's own colour
    // rather than the darker stripe a flat `bg-muted` drew.
    expect(src).toContain("before:bg-card before:content-['']");
    expect(src).not.toContain('bg-muted backdrop-blur-xs');
  });

  it('S4-04: the Product Specifications freshness line wraps instead of pushing', () => {
    const src = read(
      'app/(protected)/master-data-management/product-specifications/components/CatalogueFreshnessLine.tsx',
    );
    // Measured 0px wide and 500px tall at 375 with `flex-1` alone: a wrapping
    // row breaks its lines on flex-BASIS, and basis 0 kept the paragraph on the
    // badge and button's line with nothing left over.
    expect(src).toContain('min-w-0 grow basis-full');
    expect(src).toContain('sm:basis-0');
    expect(src).toContain('flex-wrap');
  });

  it('S4-04: a ticket number never breaks mid-string', () => {
    const list = read('app/(protected)/ticket-management/tickets/components/TicketsList.tsx');
    const kanban = read('app/(protected)/ticket-management/tickets/components/TicketsKanban.tsx');
    const detail = read('app/(protected)/ticket-management/tickets/[id]/page.tsx');
    for (const [name, src] of [
      ['TicketsList', list],
      ['TicketsKanban', kanban],
      ['ticket detail', detail],
    ] as const) {
      expect(src, name).toContain('whitespace-nowrap');
    }
  });

  it('S4-04: Pricing Summary stacks under sm so its values never touch', () => {
    const src = read(
      'app/(protected)/master-data-management/products/[id]/components/ProductDetail.tsx',
    );
    expect(src).toContain('grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-3');
  });

  it('S4-04: the two floating buttons do not share a corner', () => {
    // The AI assistant handle is docked at `end-0`, 32px wide. The activities
    // launcher moves clear of it rather than sitting on top.
    for (const file of [
      'components/common/ActivitiesNotesPanel/index.tsx',
      'components/common/ActivitiesNotesPanel/EntityActivitiesLayout.tsx',
    ]) {
      const src = read(file);
      expect(src, file).toContain('fixed end-12 bottom-4');
      expect(src, file).not.toContain('fixed right-4 bottom-4');
    }
  });

  it('S4-04: the sign-in card is a card, not a 1152px band', () => {
    const src = read('app/(auth)/layouts/branded.tsx');
    expect(src).toContain('max-w-md');
    // The wide framing stays for the pages that print a table.
    expect(src).toContain('NARROW_ROUTES');
  });

  it('S4-04: the dashboard says what it is', () => {
    const src = read('app/(protected)/page.tsx');
    // S5-01 moved every page title into PageHeader; the dashboard's reads the
    // sidebar's own first entry.
    expect(src).toContain('<PageHeader title="Dashboards" />');
  });

  it('S4-04: a dashboard task card wraps its identifier instead of cutting it', () => {
    const src = read(
      'app/(protected)/sla-management/conversation-sla-tracking/components/MyPendingSLAWidget.tsx',
    );
    expect(src).toContain('break-words text-sm font-medium');
    // ...in a box that is allowed to have a width. `min-w-0` alone, beside a
    // `shrink-0` sibling, measured 0px wide and 120px tall: one letter per line.
    expect(src).not.toContain('<div className="min-w-0">');
    expect(src).toContain('min-w-0 flex-1');
  });

  it('S4-04: the out-of-reach scrollers named above are still there', () => {
    // Without this the allowlist is just three files nobody checks.
    const dialog = read('app/(protected)/scm/components/ProductListDialog.tsx');
    expect(dialog).toContain('<DialogBody className="max-h-[55dvh] overflow-auto">');

    // ProductPerspectiveGrid used to be allowlisted here for a totals row in a
    // <table> of its own. It is a real <tfoot> on the grid now, so there is no
    // second table to place and nothing to allow.
    const perspective = read('app/(protected)/scm/components/ProductPerspectiveGrid.tsx');
    expect(perspective).not.toMatch(/^\s*<table/m);
    expect(perspective).toContain('footer:');

    const grid = read('components/ui/data-grid-table.tsx');
    expect(grid).toContain('data-slot="data-grid-scroller"');

    // CategoryTree's scroller is its caller's. Nesting a second ScrollArea let
    // the inner Root size to its 774px of content inside a 341px viewport, so
    // nothing scrolled and the last three columns were simply clipped.
    const list = read(
      'app/(protected)/master-data-management/product-categories/components/CategoriesList.tsx',
    );
    expect(list).toContain('<ScrollArea>');
    expect(list).toContain('<CategoryTree');
    const tree = read(
      'app/(protected)/master-data-management/product-categories/components/CategoryTree.tsx',
    );
    expect(tree).not.toContain('<ScrollArea');
  });

  it('S4-04: every raw table sits in its own horizontal scroller', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (SCROLLER_OUT_OF_REACH.has(file)) continue;
      const lines = read(file).split('\n');
      lines.forEach((line, i) => {
        // `<table` inside a prose comment is not markup. The `$` alternative
        // matters: Prettier breaks a tag with three or more attributes onto
        // its own line, and `[\s>]` walked past three tables because of it.
        if (!/^\s*<table(\s|>|$)/.test(line)) return;
        if (!insideScroller(lines, i)) offenders.push(`${file}:${i + 1}`);
      });
    }
    expect(offenders).toEqual([]);
  });
});
