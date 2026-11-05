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

function row(icon_order: number | null, over: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
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
    ...over,
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

describe('HeaderTab Icon order, fix round', () => {
  it('is not offered on a spec that cannot carry icons (free text, no fixed values)', () => {
    render(
      withQuery(
        <HeaderTab
          row={row(null, { data_type: 'text', allowed_values: [] })}
          mode="view"
          draft={null}
          setDraft={() => {}}
        />,
      ),
    );
    expect(screen.queryByText('Icon order')).toBeNull();
  });

  it('is offered on a yes/no spec', () => {
    render(
      withQuery(
        <HeaderTab row={row(1, { data_type: 'boolean', allowed_values: [] })} mode="view" draft={null} setDraft={() => {}} />,
      ),
    );
    expect(screen.getByText('Icon order')).toBeInTheDocument();
  });

  it('shows the inline error once a refused save set one, and clears it when fixed', () => {
    function Refused() {
      const [draft, setDraft] = useState<SpecKeyDraft>(() => ({
        ...projectSpecKeyDraft(row(2)),
        iconOrder: '0',
        iconOrderError: 'Enter a whole number between 1 and 999, or leave it blank.',
      }));
      return <HeaderTab row={row(2)} mode="edit" draft={draft} setDraft={(u) => setDraft((d) => u(d))} />;
    }
    render(withQuery(<Refused />));
    expect(screen.getByText(/whole number between 1 and 999/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Icon order'), { target: { value: '3' } });
    expect(screen.queryByText(/whole number between 1 and 999/)).toBeNull();
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
