/**
 * PRICETAG-DESIGNER-FEEDBACK AC-4.2 to AC-4.5 (owner hand test 14 Nov): Insert field opened from
 * the element's rich Content editor shows the element's EXISTING text, not an empty box.
 *
 * Written test-FIRST against a NEW dialog prop (the seam between the dialog and the TipTap caret):
 *
 *   context?: { before: string; after: string }
 *
 * The element's text before and after the rich editor's caret, as plain text, paragraphs joined
 * by "\n", tokens as written (`{{path}}`). Given:
 *  - the Content box (id `merge-field-content`) is READ-ONLY and shows before + picked + after,
 *    with an insert-point marker (`data-testid="insert-point"`, no text of its own) at the caret;
 *  - a picked field goes in at the insert point, the marker moves after it;
 *  - the Preview renders before + picked + after against the data (the placeholder with none);
 *  - Done hands back ONLY the picked tokens, in pick order (the caller inserts them at the caret).
 * Absent `context`: the dialog behaves exactly as today (InsertFieldDialog.test.tsx).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderMergeFields } from '@/lib/dealer-kit/merge-fields';
import type { TagBindingData } from '@/lib/dealer-kit/tag-template-types';
import { InsertFieldDialog } from './InsertFieldDialog';

const BEFORE = '{{combo.description}}\nLP: RM ';
const AFTER = '{{product.list_price}}';
const CONTEXT = { before: BEFORE, after: AFTER };

const DATA: TagBindingData = {
  kind: 'product',
  product: {
    id: 'p1',
    code: 'CBF3612',
    name: 'Carysil Big Bowl Sink',
    dimensions: '860 x 500 x 220 mm',
    spec_lines: [],
    specs: [],
    images: [],
    list_price: 2000,
    offer_price: 1500,
    promotion_id: null,
    barcode: null,
  },
};

type Props = Parameters<typeof InsertFieldDialog>[0] & { context?: { before: string; after: string } };

function open(props: Partial<Props> = {}) {
  const onDone = vi.fn();
  const onCancel = vi.fn();
  const Dialog = InsertFieldDialog as unknown as (p: Props) => React.ReactElement;
  render(
    <Dialog
      open
      value=""
      data={null}
      specKeys={[]}
      onCancel={onCancel}
      onDone={onDone}
      context={CONTEXT}
      {...props}
    />,
  );
  return { onDone, onCancel };
}

function contentBox(): HTMLElement {
  const box = document.getElementById('merge-field-content');
  expect(box, 'the Content box').not.toBeNull();
  return box!;
}

/** The Content box's text, as one string (a textarea's value or an element's text). */
function contentText(): string {
  const box = contentBox();
  return box instanceof HTMLTextAreaElement ? box.value : box.textContent ?? '';
}

/** The text before and after the insert-point marker inside the Content box. */
function aroundInsertPoint(): { before: string; after: string } {
  const box = contentBox();
  const marker = box.querySelector('[data-testid="insert-point"]');
  expect(marker, 'an insert point inside the Content box').not.toBeNull();
  let before = '';
  let after = '';
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (marker!.contains(node)) continue;
    const position = marker!.compareDocumentPosition(node);
    if (position & Node.DOCUMENT_POSITION_PRECEDING) before += node.textContent ?? '';
    else after += node.textContent ?? '';
  }
  return { before, after };
}

function previewText(): string {
  const label = screen.getByText('Preview:');
  return label.nextElementSibling?.textContent ?? '';
}

function pick(token: string) {
  fireEvent.click(screen.getByText(token).closest('button')!);
}

describe('AC-4.2: Insert field opens on the existing content', () => {
  it('AC-4.2: the Content box shows both lines, tokens as written, never empty', () => {
    open();
    expect(contentText()).not.toBe('');
    expect(contentText()).toContain('{{combo.description}}');
    expect(contentText()).toContain('LP: RM {{product.list_price}}');
  });

  it('AC-4.2: the insert point sits at the caret, between "RM " and the price token', () => {
    open();
    expect(aroundInsertPoint()).toEqual({ before: BEFORE, after: AFTER });
  });

  it('AC-4.2: the existing text is read-only (only the picked field is inserted)', () => {
    open();
    const box = contentBox();
    const readOnly =
      box instanceof HTMLTextAreaElement ? box.readOnly : box.getAttribute('aria-readonly') === 'true';
    expect(readOnly).toBe(true);
  });
});

describe('AC-4.3: a picked field shows at the caret, the preview renders the whole content', () => {
  it('AC-4.3: Code goes in between "RM " and the price token', () => {
    open();
    pick('{{product.code}}');
    expect(contentText()).toBe(`${BEFORE}{{product.code}}${AFTER}`);
    expect(aroundInsertPoint()).toEqual({ before: `${BEFORE}{{product.code}}`, after: AFTER });
  });

  it('AC-4.3: with data, the preview renders before + field + after, not the placeholder', () => {
    open({ data: DATA });
    pick('{{product.code}}');
    const expected = renderMergeFields(`${BEFORE}{{product.code}}${AFTER}`, DATA, 'print');
    expect(previewText()).toBe(expected);
    expect(previewText()).toContain('LP: RM CBF3612');
    expect(previewText()).not.toContain('(preview a product to see values)');
  });

  it('AC-4.3: with data and nothing picked yet, the preview is the existing content rendered, not empty', () => {
    open({ data: DATA });
    const expected = renderMergeFields(`${BEFORE}${AFTER}`, DATA, 'print');
    expect(previewText()).toBe(expected);
    expect(previewText()).toContain('LP: RM');
  });

  it('AC-4.3: with no data the preview says so', () => {
    open({ data: null });
    pick('{{product.code}}');
    expect(previewText()).toBe('(preview a product to see values)');
  });
});

describe('AC-4.4: Done hands back only the picked field(s)', () => {
  it('AC-4.4: one pick: Done returns just the token', () => {
    const { onDone } = open();
    pick('{{product.code}}');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith('{{product.code}}');
  });

  it('AC-4.4: two picks: both, in order', () => {
    const { onDone } = open();
    pick('{{product.code}}');
    pick('{{product.name}}');
    expect(contentText()).toBe(`${BEFORE}{{product.code}}{{product.name}}${AFTER}`);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('{{product.code}}{{product.name}}');
  });
});

describe('AC-4.5: Cancel changes nothing', () => {
  it('AC-4.5: Cancel after a pick calls onCancel and never onDone', () => {
    const { onDone, onCancel } = open();
    pick('{{product.code}}');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();
  });

  it('AC-4.5: without context the Content box is the editable textarea seeded with value, Done returns the whole content', () => {
    const { onDone } = open({ context: undefined, value: 'Code: ' });
    const box = contentBox() as HTMLTextAreaElement;
    expect(box.tagName).toBe('TEXTAREA');
    expect(box.readOnly).toBe(false);
    expect(box.value).toBe('Code: ');
    pick('{{product.code}}');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('Code: {{product.code}}');
  });
});
