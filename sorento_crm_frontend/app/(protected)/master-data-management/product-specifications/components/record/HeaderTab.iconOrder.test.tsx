/**
 * Owner 5 Nov 21:0x: each specification has an "Icon order" (Pull-out = 1, Water supply = 2,
 * Steel grade = 3) placing its feature icons in the tag's one sequence. Read on Details; edited in
 * place as a number; blank clears it. Saved through the registry PATCH as `icon_order`.
 */
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HeaderTab } from './HeaderTab';
import { buildPatchBody, projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

function row(icon_order: number | null): SpecRegistryKey {
  return {
    spec_key: 'water_supply',
    label: 'Water supply',
    data_type: 'enum',
    unit: null,
    allowed_values: ['mixer'],
    synonyms: {},
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [],
    applies_when: {},
    read_from: 'rules',
    rank_weight: 1,
    measured_coverage: null,
    source: 'seed',
    user_synonyms: {},
    suppressed_synonyms: {},
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
    icon_order,
  } as unknown as SpecRegistryKey;
}

function withQuery(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

let latest: SpecKeyDraft | null = null;
function EditHarness({ r }: { r: SpecRegistryKey }) {
  const [draft, setDraft] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(r));
  latest = draft;
  return <HeaderTab row={r} mode="edit" draft={draft} setDraft={(u) => setDraft((d) => u(d))} />;
}

describe('HeaderTab Icon order', () => {
  it('reads the number in view mode, and a dash when blank', () => {
    const { unmount } = render(
      withQuery(<HeaderTab row={row(2)} mode="view" draft={null} setDraft={() => {}} />),
    );
    expect(screen.getByText('Icon order')).toBeInTheDocument();
    expect(screen.getByTestId('icon-order-value')).toHaveTextContent('2');
    unmount();
    render(withQuery(<HeaderTab row={row(null)} mode="view" draft={null} setDraft={() => {}} />));
    expect(screen.getByTestId('icon-order-value')).toHaveTextContent('-');
  });

  it('edits in place and blank clears it', () => {
    render(withQuery(<EditHarness r={row(2)} />));
    const input = screen.getByLabelText('Icon order');
    expect(input).toHaveValue(2);
    fireEvent.change(input, { target: { value: '1' } });
    expect(latest?.iconOrder).toBe('1');
    fireEvent.change(input, { target: { value: '' } });
    expect(latest?.iconOrder).toBe('');
  });
});

describe('buildPatchBody icon_order', () => {
  it('sends the number, and null for blank', () => {
    const r = row(2);
    const draft = projectSpecKeyDraft(r);
    expect(buildPatchBody(r, { ...draft, iconOrder: '1' }).icon_order).toBe(1);
    expect(buildPatchBody(r, { ...draft, iconOrder: '' }).icon_order).toBeNull();
  });
});
