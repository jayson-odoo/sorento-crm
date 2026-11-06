/**
 * Feature icons on the spec VALUE (owner ruling 5 Nov 20:35, addition 20:4x): the Values and
 * words grid has an Icons column. View mode shows each value's icons in the admin's order, by
 * name (no ids); edit mode adds icons through the Dealer Kit icon library (pick appends), and
 * moves (earlier / later) or removes each one. Without the Dealer Kit library permission the
 * names still show, with no way to change them.
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

const mixerCell = () => screen.getByTestId('value-icons-mixer');
/** The cell shows a placeholder until the icon library has loaded (crew pass). */
const loaded = () => waitFor(() => expect(screen.queryByTestId('value-icons-loading')).toBeNull());

beforeEach(() => {
  canManage.value = true;
  permissionsLoading.value = false;
  libraryGate.hold = false;
  latest = null;
});

describe('ValuesAndWordsTab icons column', () => {
  it('view mode names each value\'s icons in the admin\'s order, no ids and no edit buttons', async () => {
    render(
      withClient(
        <ValuesAndWordsTab row={waterSupply()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />,
      ),
    );
    await loaded();
    const names = within(mixerCell())
      .getAllByTitle(/^(Hot|Cold)$/)
      .map((node) => node.getAttribute('title'));
    expect(names).toEqual(['Hot', 'Cold']);
    expect(screen.queryByText(/i-hot|i-cold/)).toBeNull();
    expect(screen.queryByRole('button', { name: /choose icons/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /remove hot/i })).toBeNull();
  });

  it('opens the icon library with the choice\'s icons selected; Done applies the selection in order', async () => {
    render(withClient(<EditHarness row={waterSupply()} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Choose icons for Mixer' }));
    expect(screen.getByTestId('icon-picker')).toHaveAttribute('data-kind', 'icon');
    expect(screen.getByTestId('icon-picker')).toHaveAttribute('data-selected', 'i-hot,i-cold');
    fireEvent.click(screen.getByRole('button', { name: 'Select Steam' }));
    // Selecting changes nothing until Done.
    expect(latest?.valueIcons.mixer).toEqual(['i-hot', 'i-cold']);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByTestId('icon-picker')).toBeNull();
    expect(latest?.valueIcons.mixer).toEqual(['i-hot', 'i-cold', 'i-new']);
    // Re-queried each time: the grid remounts a cell when its column definitions change.
    await waitFor(() => expect(within(mixerCell()).getByTitle('Steam')).toBeInTheDocument());
  });

  it('removes one icon and moves another earlier or later', async () => {
    render(withClient(<EditHarness row={waterSupply()} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Move Cold earlier' }));
    expect(latest?.valueIcons.mixer).toEqual(['i-cold', 'i-hot']);
    fireEvent.click(within(mixerCell()).getByRole('button', { name: 'Move Cold later' }));
    expect(latest?.valueIcons.mixer).toEqual(['i-hot', 'i-cold']);
    fireEvent.click(within(mixerCell()).getByRole('button', { name: 'Remove Hot' }));
    expect(latest?.valueIcons.mixer).toEqual(['i-cold']);
  });

  it('without the Dealer Kit library permission the names show but nothing changes them', () => {
    canManage.value = false;
    render(withClient(<EditHarness row={waterSupply()} />));
    expect(within(mixerCell()).getByTitle('Hot')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /choose icons/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /remove hot/i })).toBeNull();
  });
});

describe('ValuesAndWordsTab icon picker, fix round', () => {
  it('Cancel discards the selection, and either close refreshes the icon library', async () => {
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
    render(withClient(<EditHarness row={waterSupply()} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Choose icons for Mixer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select Steam' }));
    spy.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('icon-picker')).toBeNull();
    expect(latest?.valueIcons.mixer).toEqual(['i-hot', 'i-cold']);
    // An icon uploaded in the picker (then cancelled) is still in the library the cell names from.
    expect(spy).toHaveBeenCalledWith({ queryKey: ['dealer-kit', 'icon-library'] });
    spy.mockRestore();
  });

  it('Done with the selection unchanged keeps the choice as it was', async () => {
    render(withClient(<EditHarness row={waterSupply()} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Choose icons for Cold Only' }));
    expect(screen.getByTestId('icon-picker')).toHaveAttribute('data-selected', 'i-cold');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(latest?.valueIcons.cold_only).toEqual(['i-cold']);
  });

  it('gives each move and remove button a 28px hit area', async () => {
    render(withClient(<EditHarness row={waterSupply()} />));
    await loaded();
    const remove = within(mixerCell()).getByRole('button', { name: 'Remove Hot' });
    expect(remove.className).toMatch(/\bsize-7\b/);
    expect(within(mixerCell()).getByRole('button', { name: 'Move Hot later' }).className).toMatch(/\bsize-7\b/);
  });
});

describe('ValuesAndWordsTab icons on a yes/no specification', () => {
  it("lets the Yes value carry icons (Pull-out shower = Yes)", async () => {
    const pullOut = {
      ...waterSupply(),
      spec_key: 'has_pull_out_shower',
      label: 'Pull-out shower',
      data_type: 'boolean',
      allowed_values: [],
      value_labels: {},
      value_icons: {},
      value_icon_names: {},
    } as unknown as SpecRegistryKey;
    render(withClient(<EditHarness row={pullOut} />));
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'Choose icons for Yes' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select Steam' }));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(latest?.valueIcons.true).toEqual(['i-new']);
  });
});

describe('buildPatchBody value_icons', () => {
  it('sends value_icons when they changed, with empty lists dropped', () => {
    const row = waterSupply();
    const draft = projectSpecKeyDraft(row);
    const body = buildPatchBody(row, { ...draft, valueIcons: { mixer: ['i-cold'], cold_only: [] } });
    expect(body.value_icons).toEqual({ mixer: ['i-cold'] });
  });

  it('leaves value_icons out when nothing about them changed', () => {
    const row = waterSupply();
    expect('value_icons' in buildPatchBody(row, projectSpecKeyDraft(row))).toBe(false);
  });
});

describe('ValuesAndWordsTab icons column while loading (crew pass)', () => {
  function emptyIcons(): SpecRegistryKey {
    return { ...waterSupply(), value_icons: {}, value_icon_names: {} } as SpecRegistryKey;
  }

  it('shows a loading placeholder, not "No icons", until the icon library has loaded', async () => {
    libraryGate.hold = true;
    render(
      withClient(
        <ValuesAndWordsTab row={emptyIcons()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />,
      ),
    );
    expect(within(mixerCell()).getByTestId('value-icons-loading')).toBeInTheDocument();
    expect(screen.queryByText('No icons')).toBeNull();

    libraryGate.release();
    await waitFor(() => expect(within(mixerCell()).getByText('No icons')).toBeInTheDocument());
    expect(screen.queryByTestId('value-icons-loading')).toBeNull();
  });

  it('shows the placeholder while permissions are still loading', () => {
    permissionsLoading.value = true;
    render(
      withClient(
        <ValuesAndWordsTab row={emptyIcons()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />,
      ),
    );
    expect(within(mixerCell()).getByTestId('value-icons-loading')).toBeInTheDocument();
    expect(screen.queryByText('No icons')).toBeNull();
  });
});
