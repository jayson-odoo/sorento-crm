/**
 * SPEC-ICON-COMBINED F4: in edit mode each icon chip has an "Only with conditions for <icon>"
 * button that opens a popover where conditions (another spec key + one of its values) are added
 * and removed. The draft the grid edits then builds a PATCH body carrying `value_icon_conditions`
 * (`{value: {icon_id: [{spec_key, value}]}}`), the payload the save sends.
 *
 * Assumptions the coder must meet: the popover lists the other registry keys by their label and,
 * once one is picked, that key's values by their display label (both `SearchableSelect`, mocked
 * here as option buttons); an "Add condition" button commits the pair; each existing condition has
 * a "Remove condition <Key label> = <value label>" button.
 */
import React, { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children?: React.ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}));
vi.mock('../../services/productSpecService', () => ({
  getSpecKeyProducts: vi.fn().mockResolvedValue({
    spec_key: 'water_supply',
    label: 'Water supply',
    total: 0,
    by_value: [],
    by_class: [],
    by_source: [],
    products: [],
  }),
}));

const { canManage, permissionsLoading, libraryGate } = vi.hoisted(() => ({
  canManage: { value: true },
  permissionsLoading: { value: false },
  // While `hold` is set, the icon library read waits until `release` is called.
  libraryGate: { hold: false, release: () => {} },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) =>
    !permissionsLoading.value && slug === 'dealer_kit.library.manage' && canManage.value,
  usePermissions: () => ({ isLoading: permissionsLoading.value }),
}));
vi.mock('@/app/(protected)/dealer-kit/services/assetService', () => ({
  listAssets: vi.fn(async () => {
    if (libraryGate.hold) {
      await new Promise<void>((resolve) => {
        libraryGate.release = resolve;
      });
    }
    return LIBRARY;
  }),
}));
const LIBRARY = [
    { id: 'i-hot', name: 'Hot', kind: 'icon', tags: [], url: 'https://cdn/hot.png', thumb_url: null, mime_type: 'image/png' },
    { id: 'i-cold', name: 'Cold', kind: 'icon', tags: [], url: 'https://cdn/cold.png', thumb_url: null, mime_type: 'image/png' },
    { id: 'i-new', name: 'Steam', kind: 'icon', tags: [], url: 'https://cdn/steam.png', thumb_url: null, mime_type: 'image/png' },
];
// The real picker is the dealer-kit one; here "Select Steam" adds one icon to the dialog's own
// selection, which reaches the choice only through Done (SPEC-ICON-PICKER-UX).
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/AssetPickerDialog', () => ({
  AssetPickerDialog: (props: PickerProps) => (props.open ? <MockPicker {...props} /> : null),
}));
type PickerProps = {
  open: boolean;
  libraryKind?: string;
  selectedIds?: string[];
  onCancel: () => void;
  onDone?: (ids: string[]) => void;
};
// Mounted on open, so it seeds from selectedIds the way the real dialog does on open.
function MockPicker(props: PickerProps) {
    const [picked, setPicked] = React.useState<string[]>(props.selectedIds ?? []);
    return (
      <div data-testid="icon-picker" data-kind={props.libraryKind} data-selected={(props.selectedIds ?? []).join(',')}>
        <button type="button" onClick={() => setPicked((ids) => [...ids, 'i-new'])}>
          Select Steam
        </button>
        <button type="button" onClick={() => setPicked((ids) => ids.filter((id) => id !== 'i-hot'))}>
          Deselect Hot
        </button>
        <button type="button" onClick={props.onCancel}>
          Cancel
        </button>
        <button type="button" onClick={() => props.onDone?.(picked)}>
          Done
        </button>
      </div>
    );
}


vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <div data-testid="searchable-select">
      {(props.options ?? []).map((o) => (
        <button key={o.value} type="button" onClick={() => props.onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock('../../hooks/useSpecRegistryQuery', () => ({
  SPEC_REGISTRY_QUERY_KEY: ['spec-registry'],
  useSpecRegistryQuery: () => ({ data: REGISTRY, isLoading: false }),
}));
const REGISTRY = vi.hoisted(() => [
  { spec_key: 'water_supply', label: 'Water supply', data_type: 'enum', is_active: true,
    allowed_values: ['cold_only', 'mixer'], value_labels: { cold_only: 'Cold Only', mixer: 'Mixer' },
    suppressed_values: [], user_values: [] },
  { spec_key: 'trap_type', label: 'Trap type', data_type: 'enum', is_active: true,
    allowed_values: ['s_trap', 'p_trap'], value_labels: { s_trap: 'S trap', p_trap: 'P trap' },
    suppressed_values: [], user_values: [] },
]);

import { ValuesAndWordsTab } from './ValuesAndWordsTab';
import { buildPatchBody, projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function waterSupply(extra: Record<string, unknown> = {}): SpecRegistryKey {
  return {
    spec_key: 'water_supply', label: 'Water supply', data_type: 'enum', unit: null,
    allowed_values: ['cold_only', 'mixer'], synonyms: {}, excluded_values: [], user_values: [],
    suppressed_values: [], value_weights: {}, derivation_rules: [], effective_rules: [],
    applies_when: {}, read_from: 'rules', rank_weight: 1, measured_coverage: null, source: 'seed',
    user_synonyms: {}, suppressed_synonyms: {}, match_tolerance: 0, match_decay: 0, is_active: true,
    value_labels: { cold_only: 'Cold Only', mixer: 'Mixer' },
    value_icons: { mixer: ['i-hot', 'i-cold'] },
    value_icon_names: { 'i-hot': 'Hot', 'i-cold': 'Cold' },
    value_icon_conditions: {},
    ...extra,
  } as unknown as SpecRegistryKey;
}

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

let latest: SpecKeyDraft | null = null;
function EditHarness({ row }: { row: SpecRegistryKey }) {
  const [draft, setDraft] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  latest = draft;
  return (
    <ValuesAndWordsTab row={row} mode="edit" draft={draft}
      setDraft={(updater) => setDraft((current) => updater(current))} onEnterEdit={() => {}} />
  );
}
const loaded = () => waitFor(() => expect(screen.queryByTestId('value-icons-loading')).toBeNull());

beforeEach(() => {
  canManage.value = true;
  permissionsLoading.value = false;
  libraryGate.hold = false;
  latest = null;
});

describe('F4 ValuesAndWordsTab only-with conditions', () => {
  it('F4 adds a condition from the chip popover and the save body carries it', async () => {
    const row = waterSupply();
    render(withClient(<EditHarness row={row} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Only with conditions for Hot' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Trap type' }));
    fireEvent.click(await screen.findByRole('button', { name: 'S trap' }));
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));

    const body = buildPatchBody(row, latest as SpecKeyDraft) as Record<string, unknown>;
    expect(body.value_icon_conditions).toEqual({
      mixer: { 'i-hot': [{ spec_key: 'trap_type', value: 's_trap' }] },
    });
    // Plain icons stay plain, and value_icons is untouched.
    expect('value_icons' in body).toBe(false);
  });

  it('F4 removes an existing condition and the save body drops it', async () => {
    const row = waterSupply({
      value_icon_conditions: { mixer: { 'i-hot': [{ spec_key: 'trap_type', value: 's_trap' }] } },
    });
    render(withClient(<EditHarness row={row} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Only with conditions for Hot' }));
    fireEvent.click(await screen.findByRole('button', { name: /remove condition trap type = s trap/i }));

    const body = buildPatchBody(row, latest as SpecKeyDraft) as Record<string, unknown>;
    expect(body.value_icon_conditions).toEqual({});
  });

  it('F4 a save that changed nothing about conditions leaves value_icon_conditions out', () => {
    const row = waterSupply({
      value_icon_conditions: { mixer: { 'i-hot': [{ spec_key: 'trap_type', value: 's_trap' }] } },
    });
    expect('value_icon_conditions' in buildPatchBody(row, projectSpecKeyDraft(row))).toBe(false);
  });

  it('F4 removing the icon from the value takes its conditions with it', async () => {
    const row = waterSupply({
      value_icon_conditions: { mixer: { 'i-hot': [{ spec_key: 'trap_type', value: 's_trap' }] } },
    });
    render(withClient(<EditHarness row={row} />));
    await loaded();
    fireEvent.click(within(screen.getByTestId('value-icons-mixer')).getByRole('button', { name: 'Remove Hot' }));
    const body = buildPatchBody(row, latest as SpecKeyDraft) as Record<string, unknown>;
    expect(body.value_icons).toEqual({ mixer: ['i-cold'] });
    expect(body.value_icon_conditions ?? {}).toEqual({});
  });

  it('F4 without the library permission there is no conditions button', async () => {
    canManage.value = false;
    render(withClient(<EditHarness row={waterSupply()} />));
    expect(screen.queryByRole('button', { name: /only with conditions/i })).toBeNull();
  });
});
