/**
 * PRICETAG-COMBO-RENDER K5 / AC-C1, C2, C5, C6, B4 on the lines table.
 *
 * Written test-FIRST. Today every group is a single select, there is no pick hint, no
 * Discontinued marker and the Template select offers every template with no needs text.
 *
 * Decisions where the plan is open:
 * - The multi-select reports through a new editor method `resolvePicks(lineKey, partKey, ids)`.
 * - A group needing k >= 2 is a SearchableMultiSelect with `max={k}`, placeholder `Pick k`,
 *   one option per candidate, in the candidate order.
 * - A discontinued candidate: multi = option `disabled` + `badgeText: 'Discontinued'`;
 *   single = option `disabled` + description `Discontinued`. The flag is read from the candidate
 *   or from the line's combo part (both are given here).
 * - The hint is a paragraph reading exactly `<group>: pick n more.`
 * - The Template select keeps only templates whose `fitReason` is null for the line's combo,
 *   with description `105 x 148 mm. <needs text>`.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

type Opt = {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
  badgeText?: string;
};

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Opt[];
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
          {o.description ? ` | ${o.description}` : ''}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    placeholder?: string;
    max?: number;
    value: string[];
    onChange: (v: string[]) => void;
    options?: Opt[];
  }) => (
    <div data-testid="multi" data-max={String(props.max)} data-placeholder={props.placeholder ?? ''}>
      <span data-testid="multi-value">{props.value.join(',')}</span>
      <ul>
        {(props.options ?? []).map((o) => (
          <li key={o.value} data-testid={`multi-opt-${o.value}`} data-disabled={String(!!o.disabled)} data-badge={o.badgeText ?? ''}>
            {o.label}
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => props.onChange(['id-SRTKT1880SS', 'id-SRTKT1862SS'])}>
        pick two
      </button>
    </div>
  ),
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const CODES = ['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'];
const id = (c: string) => `id-${c}`;

const combo = (discontinued: string[] = []) => ({
  combo_id: 'c1',
  name: 'Sink combo',
  parts: [
    ...CODES.map((c) => ({
      product_id: id(c),
      code: c,
      name: c,
      choice_group: 'Kitchen tap',
      is_discontinued: discontinued.includes(c),
    })),
    { product_id: id('SRTKT71SS'), code: 'SRTKT71SS', name: 'Upgrade', choice_group: null, is_upgrade: true, is_discontinued: false },
  ],
});

const candidates = (discontinued: string[] = []) =>
  CODES.map((c) => ({ product_id: id(c), code: c, name: c, is_discontinued: discontinued.includes(c) }));

const tpl = (tid: string, groups: number[], upgrades = 0) => ({
  id: tid,
  name: `Template ${tid}`,
  family: 'ala_carte',
  published: true,
  width_mm: 105,
  height_mm: 148,
  needs: { fixed: 0, groups, upgrades },
});

function renderTable(patch: Partial<DraftLine> & Record<string, unknown> = {}, discontinued: string[] = []) {
  const resolvePicks = vi.fn();
  const resolvePart = vi.fn();
  const chooseTemplate = vi.fn();
  const editor = new Proxy({ linePricing: {}, resolvePicks, resolvePart, chooseTemplate }, {
    get: (target, key) => (key in target ? (target as never)[key] : vi.fn()),
  }) as never;
  const l = {
    ...emptyDraftLine(),
    key: 'l1',
    product_id: 'host',
    name: 'Host',
    code: 'SRTKS7061',
    combo_id: 'c1',
    combos: [combo(discontinued)],
    combos_loaded: true,
    tag_templates_for: 'host',
    tag_templates_combo: 'c1',
    tag_templates: [tpl('t3', [3], 1), tpl('t1', [1])],
    tag_template_id: 't3',
    parts: [
      {
        key: 'g1',
        product_id: null,
        code: '',
        name: '',
        role: 'Kitchen tap',
        candidates: candidates(discontinued),
        product_ids: [],
      },
    ],
    ...patch,
  } as unknown as DraftLine;
  render(<PriceTagLinesTable lines={[l]} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />);
  return { resolvePicks, resolvePart, chooseTemplate };
}

describe('a group the template needs three from', () => {
  it('renders the multi-select with max 3, "Pick 3", and the group name', () => {
    renderTable();
    const multi = screen.getByTestId('multi');
    expect(multi.dataset.max).toBe('3');
    expect(multi.dataset.placeholder).toBe('Pick 3');
    expect(screen.getByText('Kitchen tap')).toBeInTheDocument();
    expect(within(multi).getAllByRole('listitem')).toHaveLength(5);
    expect(screen.queryByLabelText('Not sure, any of 5')).toBeNull();
  });

  it('shows the picks held so far, in pick order', () => {
    renderTable({
      parts: [
        {
          key: 'g1', product_id: null, code: '', name: '', role: 'Kitchen tap', candidates: candidates(),
          product_ids: [id('SRTKT1863SS'), id('SRTKT1862SS')],
        },
      ],
    } as never);
    expect(screen.getByTestId('multi-value').textContent).toBe(`${id('SRTKT1863SS')},${id('SRTKT1862SS')}`);
  });

  it('reports picks through the editor with the line and part keys', () => {
    const { resolvePicks, resolvePart } = renderTable();
    fireEvent.click(screen.getByText('pick two'));
    expect(resolvePicks).toHaveBeenCalledWith('l1', 'g1', [id('SRTKT1880SS'), id('SRTKT1862SS')]);
    expect(resolvePart).not.toHaveBeenCalled();
  });
});

describe('a group the template needs one or none from', () => {
  it('needs one: today\'s single select', () => {
    const { resolvePart } = renderTable({ tag_template_id: 't1' });
    expect(screen.queryByTestId('multi')).toBeNull();
    fireEvent.change(screen.getByLabelText('Not sure, any of 5'), { target: { value: id('SRTKT1863SS') } });
    expect(resolvePart).toHaveBeenCalledWith('l1', 'g1', id('SRTKT1863SS'));
  });

  it('needs none from this group: single select too', () => {
    renderTable({ tag_templates: [tpl('t0', []), tpl('t1', [1])], tag_template_id: 't0' });
    expect(screen.queryByTestId('multi')).toBeNull();
    expect(screen.getByLabelText('Not sure, any of 5')).toBeInTheDocument();
  });

  it('no template chosen yet: single select', () => {
    renderTable({ tag_template_id: null });
    expect(screen.queryByTestId('multi')).toBeNull();
  });
});

describe('discontinued options', () => {
  it('multi: the option is disabled and badged Discontinued, the others are not', () => {
    renderTable({}, ['SRTKT1871SS']);
    const bad = screen.getByTestId(`multi-opt-${id('SRTKT1871SS')}`);
    expect(bad.dataset.disabled).toBe('true');
    expect(bad.dataset.badge).toBe('Discontinued');
    const fine = screen.getByTestId(`multi-opt-${id('SRTKT1862SS')}`);
    expect(fine.dataset.disabled).toBe('false');
    expect(fine.dataset.badge).toBe('');
  });

  it('single: the option is disabled with Discontinued as its description', () => {
    renderTable({ tag_template_id: 't1' }, ['SRTKT1871SS']);
    const bad = screen.getByRole('option', { name: /SRTKT1871SS/ });
    expect(bad).toBeDisabled();
    expect(bad.textContent).toContain('Discontinued');
    expect(screen.getByRole('option', { name: /SRTKT1862SS/ })).not.toBeDisabled();
  });
});

describe('the pick hint', () => {
  const held = (ids: string[]) => ({
    parts: [
      { key: 'g1', product_id: null, code: '', name: '', role: 'Kitchen tap', candidates: candidates(), product_ids: ids },
    ],
  });

  it('says how many more under a short group', () => {
    renderTable(held([id('SRTKT1862SS')]) as never);
    expect(screen.getByText('Kitchen tap: pick 2 more.')).toBeInTheDocument();
  });

  it('asks for all k when nothing is picked', () => {
    renderTable();
    expect(screen.getByText('Kitchen tap: pick 3 more.')).toBeInTheDocument();
  });

  it('is gone once k are picked', () => {
    renderTable(held([id('SRTKT1862SS'), id('SRTKT1863SS'), id('SRTKT1871SS')]) as never);
    expect(screen.queryByText(/pick \d more\./)).toBeNull();
  });

  it('is not shown for a group needing one', () => {
    renderTable({ tag_template_id: 't1' });
    expect(screen.queryByText(/pick \d more\./)).toBeNull();
  });
});

describe('the Template select (AC-B4)', () => {
  it('offers only templates that fit the combo, with the needs in the combo words', () => {
    renderTable({
      tag_templates: [tpl('t3', [3], 1), tpl('t6', [6]), tpl('t0', [])],
      tag_template_id: 't3',
    });
    const select = screen.getByLabelText('Tag template');
    const options = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(options).toContain('Template t3 | 105 x 148 mm. Needs 3 from Kitchen tap, upgrade');
    expect(options).toContain('Template t0 | 105 x 148 mm. Needs the main product only');
    expect(options.some((o) => o?.includes('Template t6'))).toBe(false);
  });
});
