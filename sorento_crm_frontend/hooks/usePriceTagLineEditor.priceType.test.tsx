/**
 * PRICETAG-LPSP S6: the line editor gives a new line the header default (AC-19), preselects the
 * default template (AC-21) and asks the combo's own templates for a combo line (AC-11 on the form).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2).
 *
 * Assumptions the coder may tighten with the captain:
 * - a new line from `addLine` carries `price_type` = the header's mode at that moment;
 * - changing the header later does NOT rewrite lines already set (Q2: "default for new lines");
 * - `ProductTagTemplateOption.is_default` marks the default among the answered options;
 * - `lookupProductTagTemplates(productId, comboId)` gets the line's combo as its second argument.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { PriceMode } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

type Opt = {
  id: string;
  name: string;
  family: string;
  published: boolean;
  width_mm: number;
  height_mm: number;
  is_default?: boolean;
};
const opt = (id: string, isDefault = false): Opt => ({
  id,
  name: id,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  is_default: isDefault,
});

function setup(
  initial: DraftLine[],
  answer: (productId: string, comboId?: string | null) => Opt[],
  startMode: PriceMode = 'list',
) {
  const lookupProductTagTemplates = vi.fn(async (productId: string, comboId?: string | null) =>
    answer(productId, comboId),
  );
  const lookups = {
    lookupTagItems: vi.fn(async () => []),
    lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
    lookupLinePricing: vi.fn(async () => []),
    lookupProductTagTemplates,
  };
  const hook = renderHook(() => {
    const [lines, setLines] = useState(initial);
    const [priceMode, setPriceMode] = useState<PriceMode>(startMode);
    const editor = usePriceTagLineEditor({
      lines,
      setLines,
      priceMode,
      lookups: lookups as never,
    });
    return { lines, setLines, priceMode, setPriceMode, editor };
  });
  return { hook, lookupProductTagTemplates };
}

const typeOf = (line: DraftLine) => (line as unknown as { price_type?: string | null }).price_type;

describe('usePriceTagLineEditor new line price type (AC-19)', () => {
  // Owner, 4 Nov: a line never set explicitly FOLLOWS Preferred Default, so a new line is untyped.
  it.each(['list', 'selling'] as const)('a new line is untyped and follows the header (%s)', (mode) => {
    const { hook } = setup([], () => [], mode);
    act(() => hook.result.current.editor.addLine());
    expect(hook.result.current.lines).toHaveLength(1);
    expect(typeOf(hook.result.current.lines[0]) ?? null).toBeNull();
  });

  it('changing the header default leaves an untyped line untyped and an explicit one alone', () => {
    const { hook } = setup([], () => [], 'list');
    act(() => hook.result.current.editor.addLine());
    act(() => hook.result.current.editor.addLine());
    const [first, second] = hook.result.current.lines.map((l) => l.key);
    act(() => hook.result.current.editor.updateLine(second, { price_type: 'list' } as never));
    act(() => hook.result.current.setPriceMode('selling'));
    expect(hook.result.current.lines.map((l) => typeOf(l) ?? null)).toEqual([null, 'list']);
    expect(first).toBeTruthy();
  });

  it('a line can be set to the other type on its own', () => {
    const { hook } = setup([], () => [], 'list');
    act(() => hook.result.current.editor.addLine());
    const key = hook.result.current.lines[0].key;
    act(() => hook.result.current.editor.updateLine(key, { price_type: 'selling' } as never));
    expect(typeOf(hook.result.current.lines[0])).toBe('selling');
  });
});

describe('usePriceTagLineEditor default template (AC-21)', () => {
  it('preselects the default among several templates', async () => {
    const { hook } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1' }],
      () => [opt('a'), opt('b', true), opt('c')],
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('b');
  });

  it('keeps a valid pick on a reopened draft over the default', async () => {
    const { hook } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1', tag_template_id: 'a' }],
      () => [opt('a'), opt('b', true)],
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('a');
  });

  it('falls to the default when the old pick is no longer offered', async () => {
    const { hook } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1', tag_template_id: 'gone' }],
      () => [opt('a'), opt('b', true)],
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('b');
  });

  it('leaves the pick empty when there are several templates and no default', async () => {
    const { hook } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1' }],
      () => [opt('a'), opt('b')],
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBeNull();
  });

  it('still applies a single template on its own', async () => {
    const { hook } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'p1' }],
      () => [opt('only')],
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('only');
  });
});

describe('usePriceTagLineEditor combo templates (AC-11 on the form)', () => {
  it('asks for the combo own templates and preselects the combo default', async () => {
    const { hook, lookupProductTagTemplates } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'host-1', combo_id: 'combo-1' }],
      (_product, combo) => (combo ? [opt('c1'), opt('c2', true)] : [opt('h')]),
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('host-1'));
    expect(lookupProductTagTemplates).toHaveBeenCalledWith('host-1', 'combo-1');
    expect(hook.result.current.lines[0].tag_template_id).toBe('c2');
  });

  it('asks again when the package changes, and drops the previous pick', async () => {
    const { hook, lookupProductTagTemplates } = setup(
      [{ ...emptyDraftLine(), key: 'l1', product_id: 'host-1' }],
      (_product, combo) => (combo ? [opt('c1'), opt('c2', true)] : [opt('h1'), opt('h2')]),
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('host-1'));
    act(() => hook.result.current.editor.chooseTemplate('l1', 'h1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('h1');

    act(() => hook.result.current.editor.updateLine('l1', { combo_id: 'combo-1' }));
    await waitFor(() =>
      expect(lookupProductTagTemplates).toHaveBeenCalledWith('host-1', 'combo-1'),
    );
    await waitFor(() => expect(hook.result.current.lines[0].tag_template_id).toBe('c2'));
  });
});
