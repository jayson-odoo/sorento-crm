/**
 * QUOTE-DESC-RICHTEXT: the line Description cell on proposals and quotations is rich text, edited
 * with the shared RichTextEditor in a popover anchored to the cell (card Q3). A plain description
 * shows exactly as today. Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationLine, StagedQuotationLine } from '../../_shared/types/project.types';
import { serverToDraft } from './quotationLineDraft';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/hooks/useProjects')>();
  return {
    ...actual,
    useQuotationLineImages: () => ({ data: undefined, isLoading: false, isError: false }),
    useProductSetLineRef: () => ({ data: undefined, isLoading: false, isError: false }),
  };
});
vi.mock('./QuotationStockChip', () => ({ QuotationStockChip: () => null, SetStockChip: () => null }));
vi.mock('./QuotationLineFlags', () => ({
  LineFlags: () => null,
  MinimumPriceBadge: () => null,
  MinimumPriceFlag: () => null,
}));
vi.mock('@/hooks/useDeferredDeleteSeconds', () => ({ useDeferredDeleteSeconds: () => 10 }));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationLinesGrid } from './QuotationLinesGrid';
import { descriptionFromEditor } from './QuotationLinesGrid';

const STYLED =
  '<p><strong>ZZT ONE PIECE WC</strong> (S-TRAP 250MM) <span style="color: #dc2626">C/W SEAT COVER</span></p>';

const BASE: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'ZZT8518',
  description: 'BASIN MIXER\nc/w <b>waste</b>',
  unit_price: '45.00',
  quantity: '2.00',
  uom: 'PCS',
  line_total: '90.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
};

function staged(source: QuotationLine): StagedQuotationLine {
  return { id: source.id, key: source.id, line: source, draft: serverToDraft(source, false), removed: false };
}

function renderGrid(lines: StagedQuotationLine[], editing: boolean, onStage = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationLinesGrid
        lines={lines}
        editing={editing}
        quotationId="q1"
        emptyHint="No lines yet."
        filterEmptyHint="No line matches."
        fetchProducts={async () => []}
        resolveProduct={() => undefined}
        productCodeOf={() => null}
        fillFromProduct={() => ({})}
        uomOptions={[]}
        uomError={null}
        onUomRetry={() => {}}
        brandOptions={[]}
        onStage={editing ? onStage : undefined}
        onToggleRemoved={editing ? vi.fn() : undefined}
      />
    </QueryClientProvider>,
  );
  return { onStage };
}

beforeEach(() => vi.clearAllMocks());

describe('Description cell, view mode', () => {
  it('shows a plain description exactly as typed, tags as text and line break kept', () => {
    renderGrid([staged(BASE)], false);
    const cell = screen.getByText(/BASIN MIXER/);
    expect(cell.textContent).toBe('BASIN MIXER\nc/w <b>waste</b>');
    expect(cell.querySelector('b')).toBeNull();
  });

  it('draws a styled description with its marks and colour, never raw tags', () => {
    renderGrid([staged({ ...BASE, description: STYLED })], false);
    const strong = screen.getByText('ZZT ONE PIECE WC');
    expect(strong.closest('strong')).not.toBeNull();
    const red = screen.getByText('C/W SEAT COVER');
    expect((red.closest('span') as HTMLElement).style.color).toBe('rgb(220, 38, 38)');
    expect(document.body.textContent).not.toContain('<strong>');
  });
});

describe('Description cell, editing', () => {
  it('shows the styled text on a trigger that opens the shared editor in a popover', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    const trigger = screen.getByRole('button', { name: /Description on ZZT8518/ });
    expect(trigger.querySelector('strong')?.textContent).toBe('ZZT ONE PIECE WC');
    await act(async () => {
      fireEvent.click(trigger);
    });
    // The shared editor (TipTap) mounts its contenteditable with the stored value.
    await waitFor(() => {
      const editable = document.querySelector('[contenteditable="true"]');
      expect(editable).not.toBeNull();
      expect(editable?.querySelector('strong')?.textContent).toBe('ZZT ONE PIECE WC');
    });
    // Full shared toolbar (card Q1): colour is there.
    expect(screen.getByRole('button', { name: /^text colour$/i })).toBeInTheDocument();
  });

  it('opens from the keyboard too (Enter on the focused cell)', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    const trigger = screen.getByRole('button', { name: /Description on ZZT8518/ });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: 'Enter' });
    });
    await waitFor(() => expect(document.querySelector('[contenteditable="true"]')).not.toBeNull());
  });

  it('a plain description opens as one paragraph per line', async () => {
    renderGrid([staged({ ...BASE, description: 'LINE ONE\nLINE TWO' })], true);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Description on ZZT8518/ }));
    });
    await waitFor(() => {
      const editable = document.querySelector('[contenteditable="true"]');
      expect(editable?.querySelectorAll('p')).toHaveLength(2);
    });
  });
});

describe('descriptionFromEditor', () => {
  it('an emptied editor is an empty description, so the catalogue default applies', () => {
    expect(descriptionFromEditor('<p></p>')).toBe('');
    expect(descriptionFromEditor('<p>  </p><p></p>')).toBe('');
  });

  it('keeps what was typed', () => {
    expect(descriptionFromEditor(STYLED)).toBe(STYLED);
  });
});

/** The TipTap editor behind a mounted contenteditable (TipTap puts itself on its view's DOM). */
function editorOf(editable: Element): { state: { selection: { from: number }; doc: { content: { size: number } } } } {
  return (editable as unknown as { editor: never }).editor;
}

describe('one-step editing (owner hand test, 10 Nov)', () => {
  it('a single click opens the editor already focused, full toolbar showing', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Description on ZZT8518/ }));
    });
    await waitFor(() => {
      const editable = document.querySelector('[contenteditable="true"]');
      expect(editable).not.toBeNull();
      expect(editable?.contains(document.activeElement)).toBe(true);
    });
    expect(screen.getByRole('button', { name: /^text colour$/i })).toBeInTheDocument();
  });

  it('puts the caret at the character that was clicked', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    const trigger = screen.getByRole('button', { name: /Description on ZZT8518/ });
    // "ZZT ONE PIECE WC" is the first run; the click lands after "ZZT " (offset 4).
    const textNode = Array.from(trigger.querySelectorAll('strong'))[0].firstChild as Text;
    const original = (document as unknown as { caretRangeFromPoint?: unknown }).caretRangeFromPoint;
    (document as unknown as { caretRangeFromPoint: unknown }).caretRangeFromPoint = () => {
      const range = document.createRange();
      range.setStart(textNode, 4);
      return range;
    };
    try {
      await act(async () => {
        fireEvent.click(trigger, { clientX: 10, clientY: 10 });
      });
      await waitFor(() => {
        const editable = document.querySelector('[contenteditable="true"]');
        expect(editable?.contains(document.activeElement)).toBe(true);
        // Paragraph opens at 0, its text starts at 1: offset 4 is position 5.
        expect(editorOf(editable as Element).state.selection.from).toBe(5);
      });
    } finally {
      (document as unknown as { caretRangeFromPoint: unknown }).caretRangeFromPoint = original;
    }
  });

  it('tabbing into the cell opens the editor with the caret at the end', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    const trigger = screen.getByRole('button', { name: /Description on ZZT8518/ });
    await act(async () => {
      trigger.focus();
    });
    await waitFor(() => {
      const editable = document.querySelector('[contenteditable="true"]');
      expect(editable?.contains(document.activeElement)).toBe(true);
      const editor = editorOf(editable as Element);
      expect(editor.state.selection.from).toBe(editor.state.doc.content.size - 1);
    });
  });

  it('Escape closes the editor and focus back on the cell does not reopen it', async () => {
    renderGrid([staged({ ...BASE, description: STYLED })], true);
    const trigger = screen.getByRole('button', { name: /Description on ZZT8518/ });
    await act(async () => {
      fireEvent.click(trigger);
    });
    await waitFor(() => expect(document.querySelector('[contenteditable="true"]')).not.toBeNull());
    await act(async () => {
      fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' });
    });
    await waitFor(() => expect(document.querySelector('[contenteditable="true"]')).toBeNull());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(document.querySelector('[contenteditable="true"]')).toBeNull();
  });
});

describe('click point to editor position', () => {
  it('counts the text before the click, skipping list markers and line breaks', async () => {
    const { textOffsetAt } = await import('./quotationDescriptionCaret');
    const root = document.createElement('div');
    root.innerHTML =
      '<p><span data-rt-marker>•</span><span>ab</span></p><p><span>cd</span></p><span>x\ny</span>';
    const c = root.querySelectorAll('span')[2].firstChild as Text; // "cd"
    expect(textOffsetAt(root, c, 1)).toBe(3); // a b c|
    const xy = root.querySelectorAll('span')[3].firstChild as Text; // "x\ny"
    expect(textOffsetAt(root, xy, 3)).toBe(6); // a b c d x y|
  });

  it('maps a text offset to the editor position, end when past the text', async () => {
    const { docPosAtTextOffset } = await import('./quotationDescriptionCaret');
    const { Editor } = await import('@tiptap/core');
    const StarterKit = (await import('@tiptap/starter-kit')).default;
    const editor = new Editor({ extensions: [StarterKit], content: '<p>ab</p><ul><li><p>cd</p></li></ul>' });
    try {
      expect(docPosAtTextOffset(editor.state.doc, 0)).toBe(1);
      expect(docPosAtTextOffset(editor.state.doc, 2)).toBe(3);
      // "c" sits inside ul > li > p: positions 4 (ul) 5 (li) 6 (p) then text from 7.
      expect(docPosAtTextOffset(editor.state.doc, 3)).toBe(8);
      const { Selection } = await import('@tiptap/pm/state');
      expect(docPosAtTextOffset(editor.state.doc, 99)).toBe(Selection.atEnd(editor.state.doc).from);
    } finally {
      editor.destroy();
    }
  });
});
