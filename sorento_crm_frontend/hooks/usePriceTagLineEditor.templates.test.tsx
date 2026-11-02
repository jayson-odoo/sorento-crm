/** PRICETAG-TEMPLATE-PER-PRODUCT AC-11/AC-14: the templates lookup, once per product on a line. */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

const opt = (id: string) => ({ id, name: id, family: 'ala_carte', published: true, width_mm: 80, height_mm: 50 });

function setup(initial: DraftLine[], answer: Record<string, ReturnType<typeof opt>[]>) {
  const lookupProductTagTemplates = vi.fn(async (productId: string) => answer[productId] ?? []);
  const lookups = {
    lookupTagItems: vi.fn(async () => []),
    lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
    lookupLinePricing: vi.fn(async () => []),
    lookupProductTagTemplates,
  };
  const hook = renderHook(() => {
    const [lines, setLines] = useState(initial);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups });
    return { lines, setLines, editor };
  });
  return { hook, lookupProductTagTemplates };
}

describe('usePriceTagLineEditor templates', () => {
  it('applies a single template on its own', async () => {
    const { hook } = setup([{ ...emptyDraftLine(), key: 'l1', product_id: 'p1' }], { p1: [opt('only')] });
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('only');
  });

  it('keeps a valid pick on a reopened draft and drops one that is no longer offered', async () => {
    const { hook } = setup(
      [
        { ...emptyDraftLine(), key: 'l1', product_id: 'p1', tag_template_id: 'b' },
        { ...emptyDraftLine(), key: 'l2', product_id: 'p2', tag_template_id: 'gone' },
      ],
      { p1: [opt('a'), opt('b')], p2: [opt('a'), opt('c')] },
    );
    await waitFor(() => expect(hook.result.current.lines[1].tag_templates_for).toBe('p2'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('b');
    expect(hook.result.current.lines[1].tag_template_id).toBeNull();
  });

  it('chooseTemplate sets the pick, and a re-picked product asks again', async () => {
    const { hook, lookupProductTagTemplates } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1' }],
      { p1: [opt('a'), opt('b')], p2: [opt('x'), opt('y')] },
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    act(() => hook.result.current.editor.chooseTemplate('l1', 'a'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('a');
    act(() =>
      hook.result.current.setLines((prev) => prev.map((l) => ({ ...l, product_id: 'p2' }))),
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p2'));
    expect(hook.result.current.lines[0].tag_template_id).toBeNull();
    expect(lookupProductTagTemplates).toHaveBeenCalledWith('p2');
  });

  it('picking a template clears the row\'s missing-template message only', async () => {
    const { hook } = setup(
      [
        { ...emptyDraftLine(), key: 'l1', product_id: 'p1', guard_error: 'Pick a tag template for this line.' },
        { ...emptyDraftLine(), key: 'l2', product_id: 'p2', guard_error: 'X is already on this request.' },
      ],
      { p1: [opt('a'), opt('b')], p2: [opt('a'), opt('b')] },
    );
    await waitFor(() => expect(hook.result.current.lines[1].tag_templates_for).toBe('p2'));
    act(() => hook.result.current.editor.chooseTemplate('l1', 'a'));
    act(() => hook.result.current.editor.chooseTemplate('l2', 'a'));
    expect(hook.result.current.lines[0].guard_error).toBeNull();
    expect(hook.result.current.lines[1].guard_error).toBe('X is already on this request.');
  });
});
