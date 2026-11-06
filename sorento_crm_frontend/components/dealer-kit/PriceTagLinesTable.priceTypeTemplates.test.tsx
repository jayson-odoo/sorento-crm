/**
 * PRICETAG-COMBO-FORMAT AC-35 / AC-36: a request line offers only the templates that fit its price
 * type, switches to the other type's default when the type flips, and says so when no linked
 * template fits.
 *
 * Written test-FIRST. The table offers every linked template whatever the line's type today.
 *
 * Contract read literally, flagged for the captain:
 * - each template option on a line carries `price_type` (list | selling | both | null),
 *   `default_list` and `default_selling` (the shape the portal lookup answers with);
 * - "fits": LP line -> list, both, null; SP line -> selling, both, null (a null type fits both);
 * - flipping LP -> SP is reported through `editor.updateLine(key, { price_type, ... })` and/or
 *   `editor.chooseTemplate(key, id)`; the test accepts either carrying the SP default;
 * - the pill text is "No SP template linked" / "No LP template linked"; the eye keeps its
 *   "Preview tag for line N" name and is disabled;
 * - R13: the no-fit scenarios use a line WITHOUT a kept pick (a new line, `tag_template_id: null`); a
 *   loaded line keeping a stored template that no longer fits is in `...keptPick.test.tsx`;
 * - the Submit reason is `"<code>: No SP template linked"` from `lineProblemsOf` for a product line
 *   (the combo-name label is a server-side/FE-form case not covered here).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
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
import { emptyDraftLine, lineProblemsOf, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const tpl = (id: string, price_type: string | null, flags: { l?: boolean; s?: boolean } = {}) => ({
  id,
  name: `Tpl ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type,
  default_list: !!flags.l,
  default_selling: !!flags.s,
});

const LP = tpl('lp', 'list', { l: true });
const SP = tpl('sp', 'selling', { s: true });
const BOTH = tpl('both', 'both');
const NONE = tpl('none', null);

function mk(patch: Record<string, unknown>): DraftLine {
  return {
    ...emptyDraftLine(),
    key: 'l1',
    product_id: 'p-l1',
    name: 'ZZT l1',
    code: 'ZZT-l1',
    tag_templates_for: 'p-l1',
    ...patch,
  } as DraftLine;
}

function renderTable(line: DraftLine) {
  const updateLine = vi.fn();
  const chooseTemplate = vi.fn();
  const editor = new Proxy({ linePricing: {}, updateLine, chooseTemplate }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  render(
    <PriceTagLinesTable lines={[line]} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />,
  );
  return { updateLine, chooseTemplate };
}

const optionIds = () =>
  Array.from(screen.getByLabelText('Tag template').querySelectorAll('option'))
    .map((o) => o.getAttribute('value'))
    .filter(Boolean);

/** Every template id the click handed to the editor, from either entry point. */
function templatesChosen(spies: ReturnType<typeof renderTable>): string[] {
  const fromUpdate = spies.updateLine.mock.calls
    .map((call) => (call[1] as { tag_template_id?: string | null } | undefined)?.tag_template_id)
    .filter((id): id is string => typeof id === 'string');
  const fromChoose = spies.chooseTemplate.mock.calls.map((call) => call[1] as string);
  return [...fromUpdate, ...fromChoose];
}

describe('template select offers what fits the line (AC-35)', () => {
  it('AC-35: an LP line lists LP, LP & SP and unset templates only', () => {
    renderTable(mk({ price_type: 'list', tag_templates: [LP, SP, BOTH, NONE], tag_template_id: 'lp' }));
    expect(optionIds()).toEqual(expect.arrayContaining(['lp', 'both', 'none']));
    expect(optionIds()).not.toContain('sp');
  });

  it('AC-35: an SP line lists SP, LP & SP and unset templates only', () => {
    renderTable(mk({ price_type: 'selling', tag_templates: [LP, SP, BOTH, NONE], tag_template_id: 'sp' }));
    expect(optionIds()).toEqual(expect.arrayContaining(['sp', 'both', 'none']));
    expect(optionIds()).not.toContain('lp');
  });

  it('AC-35: flipping an LP line to SP switches its template to the SP default', () => {
    const spies = renderTable(
      mk({ price_type: 'list', tag_templates: [LP, SP, BOTH], tag_template_id: 'lp' }),
    );
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));

    expect(spies.updateLine).toHaveBeenCalledWith('l1', expect.objectContaining({ price_type: 'selling' }));
    expect(templatesChosen(spies)).toContain('sp');
  });

  it('AC-35: a pick that fits both types is kept when the type flips', () => {
    const spies = renderTable(
      mk({ price_type: 'list', tag_templates: [LP, SP, BOTH], tag_template_id: 'both' }),
    );
    fireEvent.click(screen.getByRole('radio', { name: 'SP' }));

    expect(spies.updateLine).toHaveBeenCalledWith('l1', expect.objectContaining({ price_type: 'selling' }));
    expect(templatesChosen(spies).filter((id) => id !== 'both')).toEqual([]);
  });
});

describe('no template fits the line (AC-36)', () => {
  it('AC-36: an SP line whose links are all LP-only shows the pill and a disabled eye', () => {
    renderTable(mk({ price_type: 'selling', tag_templates: [LP], tag_template_id: null }));

    expect(screen.getByText('No SP template linked')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview tag for line 1/ })).toBeDisabled();
  });

  it('AC-36: the LP mirror case says "No LP template linked"', () => {
    renderTable(mk({ price_type: 'list', tag_templates: [SP], tag_template_id: null }));

    expect(screen.getByText('No LP template linked')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview tag for line 1/ })).toBeDisabled();
  });

  it('AC-36: a line whose item has no links at all keeps today\'s behaviour (no pill)', () => {
    renderTable(mk({ price_type: 'selling', tag_templates: [] }));

    expect(screen.queryByText(/template linked/)).toBeNull();
  });

  it('AC-36: a line with a fitting template shows no pill', () => {
    renderTable(mk({ price_type: 'selling', tag_templates: [LP, SP], tag_template_id: 'sp' }));
    expect(screen.queryByText(/template linked/)).toBeNull();
  });

  it('AC-36: Submit and Approve are refused with "<item>: No SP template linked"', () => {
    const line = mk({ price_type: 'selling', tag_templates: [LP], tag_template_id: null });
    expect(lineProblemsOf(line, null, 'list')).toContain('ZZT-l1: No SP template linked');
  });

  it('AC-36: the LP reason reads "No LP template linked"', () => {
    const line = mk({ price_type: 'list', tag_templates: [SP], tag_template_id: null });
    expect(lineProblemsOf(line, null, 'list')).toContain('ZZT-l1: No LP template linked');
  });

  it('AC-36: no reason when a template fits, or when the item has no links', () => {
    const fits = mk({ price_type: 'selling', tag_templates: [LP, SP], tag_template_id: 'sp' });
    const none = mk({ price_type: 'selling', tag_templates: [] });
    for (const line of [fits, none]) {
      expect(lineProblemsOf(line, null, 'list').filter((m) => /template linked/.test(m))).toEqual([]);
    }
  });
});
