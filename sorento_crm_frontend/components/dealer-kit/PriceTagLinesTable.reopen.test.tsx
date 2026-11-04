import React from 'react';
import { expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
import {
  emptyDraftLine,
  lineToDraft,
  restoreGroupCandidates,
  type DraftLine,
} from '@/lib/dealer-kit/price-tag-draft-lines';

const CODES = ['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'];
const id = (c: string) => `id-${c}`;
const combo = {
  combo_id: 'c1',
  name: 'Sink combo',
  parts: CODES.map((c) => ({ product_id: id(c), code: c, name: c, choice_group: 'Kitchen tap', is_discontinued: false })),
};

it('F2: a saved line with 3 picks reopens as ONE multi-select with the chips in saved order', () => {
  const saved = lineToDraft({
    id: 'l1', line_type: 'product', product_id: 'host', product_set_id: null, name: 'Host', code: 'H',
    quantity: 1, combo_id: 'c1',
    parts: [CODES[2], CODES[0], CODES[1]].map((c, i) => ({
      id: `p${i}`, product_id: id(c), code: c, name: c, role: 'Kitchen tap', candidates: [],
    })),
  } as never);
  const l = {
    ...emptyDraftLine(),
    ...saved,
    combos: [combo],
    combos_loaded: true,
    parts: restoreGroupCandidates(saved.parts, combo),
    tag_templates_for: 'host',
    tag_templates_combo: 'c1',
    tag_templates: [
      { id: 't3', name: 'T3', family: 'ala_carte', published: true, width_mm: 105, height_mm: 148, needs: { fixed: 0, groups: [3], upgrades: 0 } },
    ],
    tag_template_id: 't3',
  } as unknown as DraftLine;
  const editor = new Proxy({ linePricing: {} }, { get: (t, k) => (k in t ? (t as never)[k] : vi.fn()) }) as never;
  render(<PriceTagLinesTable lines={[l]} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />);
  expect(screen.getAllByTestId('multi')).toHaveLength(1);
  expect(screen.getByTestId('multi-value').textContent).toBe([CODES[2], CODES[0], CODES[1]].map(id).join(','));
  expect(screen.queryByText(/pick \d more\./)).toBeNull();
});
