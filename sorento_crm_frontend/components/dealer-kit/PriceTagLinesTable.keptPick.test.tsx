/**
 * PRICETAG-COMBO-FORMAT R13 (the client matches server R5): a LOADED line that keeps its stored
 * template (pick unchanged, price type unchanged) shows no "No SP template linked" pill, its eye is
 * enabled, and no Submit / Approve reason is raised for it, even though the template no longer fits
 * and nothing fitting is linked. The pill, disabled eye and reason apply once the user flips the
 * line's LP / SP (or changes the pick) and nothing fits.
 *
 * Written test-FIRST. Real `usePriceTagLineEditor` + `PriceTagLinesTable` + `lineToDraft`, so the
 * "kept" state is whatever the implementation records on the line; the test never sets a marker.
 * The item here has ONE link, an LP-only template, and the line was saved as an SP line on it.
 *
 * Flow reading (flagged): the flip is SP -> LP -> SP. The first flip makes the stored template fit
 * again; the second makes it stop fitting by the user's own doing, which is "the user flipped".
 */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select aria-label={props.placeholder ?? ''} value={props.value ?? ''} onChange={(e) => props.onChange?.(e.target.value)}>
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { usePriceTagLineEditor } from '@/hooks/usePriceTagLineEditor';
import { lineProblemsOf, lineToDraft, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const LP_ONLY = {
  id: 'lp',
  name: 'Tpl lp',
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type: 'list',
  default_list: true,
  default_selling: false,
};

function savedSpLine(): DraftLine {
  return lineToDraft(
    {
      id: 'l1',
      line_type: 'product',
      product_id: 'p1',
      product_set_id: null,
      name: 'ZZT 1',
      code: 'ZZT-1',
      quantity: 1,
      price_type: 'selling',
      tag_template_id: 'lp',
      parts: [],
    } as never,
    'list',
  );
}

let latest: DraftLine[] = [];

function Harness() {
  const [lines, setLines] = useState<DraftLine[]>([savedSpLine()]);
  latest = lines;
  const lookups = React.useMemo(
    () => ({
      lookupTagItems: vi.fn(async () => []),
      lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
      lookupLinePricing: vi.fn(async () => []),
      lookupProductTagTemplates: vi.fn(async () => [LP_ONLY]),
    }),
    [],
  );
  const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups: lookups as never });
  return <PriceTagLinesTable lines={lines} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />;
}

async function loaded() {
  render(<Harness />);
  await waitFor(() => expect(latest[0].tag_templates_for).toBe('p1'));
}

const eye = () => screen.getByRole('button', { name: /Preview tag for line 1/ });
const reasons = () => lineProblemsOf(latest[0], null, 'list').filter((m) => /template linked/.test(m));

describe('a kept stored template raises nothing (R13)', () => {
  it('R13: no pill on a loaded line keeping a template that no longer fits', async () => {
    await loaded();
    expect(latest[0].tag_template_id).toBe('lp');
    expect(screen.queryByText('No SP template linked')).toBeNull();
  });

  it('R13: its eye is enabled', async () => {
    await loaded();
    expect(eye()).toBeEnabled();
  });

  it('R13: it has no entry in the Submit / Approve reasons', async () => {
    await loaded();
    expect(reasons()).toEqual([]);
  });

  it('R13: after the user flips the line away and back, nothing fits and the pill, disabled eye and reason appear', async () => {
    await loaded();
    fireEvent.click(screen.getByRole('radio', { name: 'LP' }));
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));

    expect(await screen.findByText('No SP template linked')).toBeInTheDocument();
    expect(eye()).toBeDisabled();
    expect(reasons()).toEqual(['ZZT-1: No SP template linked']);
  });
});
