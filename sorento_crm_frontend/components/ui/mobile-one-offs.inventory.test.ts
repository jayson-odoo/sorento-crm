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
 * The shared grid owns its own scroller (`DataGridScroller`), so it is the one
 * `<table>` in the tree that is allowed to stand unwrapped.
 */
const OWNS_ITS_SCROLLER = new Set(['components/ui/data-grid-table.tsx']);

describe('Mobile one-offs (S4-04)', () => {
  it('S4-04: Product Categories scrolls sideways and pins the Name column', () => {
    const src = read(
      'app/(protected)/master-data-management/product-categories/components/CategoryTree.tsx',
    );
    // Percentage `<col>` widths inside `table-fixed` are what squeezed six
    // columns into 375 and cut the category name to three characters.
    expect(src).not.toContain('<colgroup>');
    expect(src).not.toContain('table-fixed');
    expect(src).toContain('<ScrollArea');
    expect(src).toContain('orientation="horizontal"');
    // The identifier stays put while the rest scrolls, as the DataGrid does.
    expect(src).toContain('sticky start-0');
  });

  it('S4-04: the Product Specifications freshness banner wraps instead of pushing', () => {
    const src = read(
      'app/(protected)/master-data-management/product-specifications/components/CatalogueFreshness.tsx',
    );
    expect(src).toContain('min-w-0 flex-1');
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
    expect(src).toContain('grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3');
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
    expect(src).toContain('<ToolbarTitle>Dashboard</ToolbarTitle>');
  });

  it('S4-04: a dashboard task card wraps its identifier instead of cutting it', () => {
    const src = read(
      'app/(protected)/sla-management/conversation-sla-tracking/components/MyPendingSLAWidget.tsx',
    );
    expect(src).toContain('break-words text-sm font-medium');
  });

  it('S4-04: every raw table sits in its own horizontal scroller', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (OWNS_ITS_SCROLLER.has(file)) continue;
      const lines = read(file).split('\n');
      lines.forEach((line, i) => {
        // `<table` inside a prose comment is not markup.
        if (!/^\s*<table[\s>]/.test(line)) return;
        const before = lines.slice(Math.max(0, i - 14), i).join('\n');
        if (!/ScrollArea|overflow-x-auto|overflow-auto|overflow-x-scroll/.test(before)) {
          offenders.push(`${file}:${i + 1}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});
