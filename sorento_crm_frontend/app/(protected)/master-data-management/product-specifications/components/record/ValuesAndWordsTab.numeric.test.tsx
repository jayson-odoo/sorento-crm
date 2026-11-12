/**
 * PRICETAG-UPGRADE-VARIANTS FE test 10 (AC-F3): a NUMERIC spec key lists the values products hold
 * (`row.numeric_values`, e.g. trap_length 150 / 200 / 250) as rows with the same Icons column; no add,
 * rename or remove of values. Written test-FIRST. Chosen wire field: `numeric_values: string[]`.
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

import { ValuesAndWordsTab } from './ValuesAndWordsTab';
import { buildPatchBody, projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function waterSupply(): SpecRegistryKey {
  return {
    spec_key: 'water_supply',
    label: 'Water supply',
    data_type: 'enum',
    unit: null,
    allowed_values: ['cold_only', 'mixer'],
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
    value_labels: { cold_only: 'Cold Only', mixer: 'Mixer' },
    value_icons: { mixer: ['i-hot', 'i-cold'], cold_only: ['i-cold'] },
    value_icon_names: { 'i-hot': 'Hot', 'i-cold': 'Cold' },
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
    <ValuesAndWordsTab
      row={row}
      mode="edit"
      draft={draft}
      setDraft={(updater) => setDraft((current) => updater(current))}
      onEnterEdit={() => {}}
    />
  );
}


function trapLength(over: Record<string, unknown> = {}): SpecRegistryKey {
  return {
    ...waterSupply(),
    spec_key: 'trap_length',
    label: 'Trap length',
    data_type: 'numeric',
    unit: 'mm',
    allowed_values: [],
    value_labels: {},
    value_icons: { '150': ['i-hot'], '250': ['i-cold'] },
    value_icon_names: { 'i-hot': 'Hot', 'i-cold': 'Cold' },
    numeric_values: ['150', '200', '250'],
    ...over,
  } as unknown as SpecRegistryKey;
}

const cell = (value: string) => screen.getByTestId(`value-icons-${value}`);
const loaded = () => waitFor(() => expect(screen.queryByTestId('value-icons-loading')).toBeNull());

beforeEach(() => {
  canManage.value = true;
  permissionsLoading.value = false;
  libraryGate.hold = false;
  latest = null;
});

describe('ValuesAndWordsTab, numeric key', () => {
  it('lists each value the products hold as a row, not the "no choices" note', async () => {
    render(withClient(<ValuesAndWordsTab row={trapLength()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));
    await loaded();
    expect(screen.queryByText(/Numbers have no choices/)).toBeNull();
    for (const value of ['150', '200', '250']) expect(cell(value)).toBeInTheDocument();
  });

  it('shows the icons each value carries, by name', async () => {
    render(withClient(<ValuesAndWordsTab row={trapLength()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));
    await loaded();
    expect(within(cell('150')).getByTitle('Hot')).toBeInTheDocument();
    expect(within(cell('250')).getByTitle('Cold')).toBeInTheDocument();
    expect(within(cell('200')).queryByTitle('Hot')).toBeNull();
  });

  it('keeps an Icons column header', async () => {
    render(withClient(<ValuesAndWordsTab row={trapLength()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));
    await loaded();
    expect(screen.getByRole('columnheader', { name: /icons/i })).toBeInTheDocument();
  });

  it('edit mode adds icons to a value through the library; Done writes the draft', async () => {
    render(withClient(<EditHarness row={trapLength()} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Choose icons for 200' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select Steam' }));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(latest?.valueIcons['200']).toEqual(['i-new']);
  });

  it('offers no way to add, rename or remove a value', async () => {
    render(withClient(<EditHarness row={trapLength()} />));
    await loaded();
    expect(screen.queryByRole('button', { name: /add a choice/i })).toBeNull();
    expect(screen.queryByLabelText('New choice')).toBeNull();
    expect(screen.queryByRole('button', { name: /remove 150$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^remove choice/i })).toBeNull();
  });

  it('a numeric key no product holds a value for still says so', async () => {
    render(withClient(<ValuesAndWordsTab row={trapLength({ numeric_values: [], value_icons: {} })} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));
    expect(screen.getByText(/Numbers have no choices|No values/i)).toBeInTheDocument();
  });

  it('a non-numeric key is unchanged: its allowed values are its rows', async () => {
    render(withClient(<ValuesAndWordsTab row={waterSupply()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));
    await loaded();
    expect(screen.getByTestId('value-icons-mixer')).toBeInTheDocument();
  });
});
