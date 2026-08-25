/**
 * StockVisibilitySection - the one card that serves all three policy tiers
 * (PLAN-stock-visibility-policy, UAC E1-E8).
 *
 *   E1 effective mode + warehouses as `CODE - name` + source badge, never a UUID
 *   E2 mode is a three-option non-clearable select; Locations is an async
 *      server-search multi-select whose chips clear one at a time
 *   E3 "Dealer pool" fills the `segment=dealer` warehouses
 *   E4 Save PUTs, invalidates and toasts; the error path toasts the
 *      `extractApiError` message the service threw
 *   E5 Remove goes through ConfirmDeleteDialog (never `confirm()`), DELETEs, and
 *      the card falls back to the inherited policy
 *   E8 empty Locations reads "All locations" and saves `warehouse_ids: null`
 *   E9 "Hide zero-quantity locations" renders from the effective policy, toggles,
 *      and rides the same wholesale Save
 *
 * Mocked at the SERVICE boundary: the card + hooks are real, `stockVisibilityService`
 * is not. Which URL each of those functions calls is the service's own contract and is
 * proven in `services/stockVisibilityService.test.ts`.
 *
 * SearchableSelect / SearchableMultiSelect are stubbed as deterministic controls (the
 * technique `product-discontinued-scope-editor.test.tsx` established) so a pick is a
 * plain fireEvent rather than a Radix popover interaction. The stubs deliberately
 * expose which MODE the picker was handed - static `options` or async `fetchOptions` -
 * because "the Locations picker server-searches" is the assertion, and a stub that
 * accepted either would prove nothing.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
    message: vi.fn(),
  },
}));

/**
 * Two assertions here are about the SHARED controls, not about the card: that the
 * mode select offers no way to clear itself, and that no UUID reaches the DOM. A
 * stub can only answer those about itself, so it renders the real component for
 * those tests and the deterministic stub for the rest.
 */
const pickers = vi.hoisted(() => ({ real: false }));

vi.mock('@/components/common/SearchableSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableSelect')>();
  const Real = actual.SearchableSelect;
  const Stub = ({
    id,
    value,
    onChange,
    options,
    placeholder,
    disabled,
    clearable,
  }: Parameters<typeof Real>[0]) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      // 'unset' vs 'false': the card passes NO clearable prop, and asserting
      // `String(!!undefined)` would have read 'false' whatever it passed.
      data-clearable={clearable === undefined ? 'unset' : String(clearable)}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return {
    ...actual,
    SearchableSelect: (props: Parameters<typeof Real>[0]) =>
      pickers.real ? <Real {...props} /> : <Stub {...props} />,
  };
});

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const ReactModule = await import('react');
  const actual =
    await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const Real = actual.SearchableMultiSelect;
  type Option = { value: string; label: string };
  const Stub = ({
      value,
      onChange,
      options,
      fetchOptions,
      selectedOptions,
      placeholder,
      disabled,
    }: Parameters<typeof Real>[0]) => {
      const [found, setFound] = ReactModule.useState<Option[]>([]);
      return (
        <div
          data-testid="locations-picker"
          data-picker-mode={typeof fetchOptions === 'function' ? 'async' : 'static'}
          data-static-option-count={options ? String(options.length) : 'none'}
          data-placeholder={placeholder ?? ''}
          aria-disabled={!!disabled}
        >
          {(selectedOptions ?? []).map((o) => (
            <span key={o.value} data-testid="location-chip">
              {o.label}
              <button
                type="button"
                aria-label={`Remove ${o.label}`}
                onClick={() => onChange(value.filter((v) => v !== o.value))}
              >
                x
              </button>
            </span>
          ))}
          <input
            aria-label="Search locations"
            onChange={(e) => {
              const q = e.target.value;
              void (async () => {
                const rows = (await fetchOptions?.(q)) ?? [];
                setFound(rows);
              })();
            }}
          />
          {found.map((o) => (
            <button
              key={o.value}
              type="button"
              data-testid="location-result"
              onClick={() => onChange([...value, o.value])}
            >
              {o.label}
            </button>
          ))}
        </div>
      );
    };
  return {
    ...actual,
    SearchableMultiSelect: (props: Parameters<typeof Real>[0]) =>
      pickers.real ? <Real {...props} /> : <Stub {...props} />,
  };
});

const service = vi.hoisted(() => ({
  getStockVisibility: vi.fn(),
  saveStockVisibility: vi.fn(),
  deleteStockVisibility: vi.fn(),
  searchStockVisibilityWarehouses: vi.fn(),
  getDealerPoolWarehouses: vi.fn(),
}));

vi.mock('@/services/stockVisibilityService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/stockVisibilityService')>();
  return { ...actual, ...service };
});

import { toast } from 'sonner';
import { StockVisibilitySection } from './StockVisibilitySection';
import type {
  StockVisibilityMode,
  StockVisibilityPolicy,
  StockVisibilityPolicyResponse,
  StockVisibilityScope,
  StockVisibilityWarehouse,
} from '@/services/stockVisibilityService';

/* Real-shaped UUIDs, because "no UUID reaches the DOM" is only a test if a UUID exists. */
const BRW: StockVisibilityWarehouse = {
  id: '9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a01',
  code: 'BRW',
  name: 'Rawang Main Warehouse',
};
const MWH: StockVisibilityWarehouse = {
  id: '9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a02',
  code: 'MWH',
  name: 'Meru Warehouse',
};
const DC1: StockVisibilityWarehouse = {
  id: '9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a03',
  code: 'DC1',
  name: 'Distribution Centre 1',
};
const BRW_BB: StockVisibilityWarehouse = {
  id: '9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a04',
  code: 'BRW-BB',
  name: 'Rawang Bulk Bay',
};

const CONTACT_SCOPE: StockVisibilityScope = { kind: 'contact', contactId: 'contact-77' };
const ACCESS_TYPE_SCOPE: StockVisibilityScope = { kind: 'access_type', accessTypeCode: 'dealer' };
const DEFAULT_SCOPE: StockVisibilityScope = { kind: 'default' };

function policy(
  mode: StockVisibilityMode,
  warehouses: StockVisibilityWarehouse[] | null,
  source: StockVisibilityPolicy['source'],
  sourceLabel: string | null = null,
  hideZeroLocations = false,
): StockVisibilityPolicy {
  return {
    mode,
    warehouses,
    hide_zero_locations: hideZeroLocations,
    source,
    source_label: sourceLabel,
  };
}

/**
 * A fresh object per call on purpose: react-query hands back a new reference on every
 * background refetch, and the draft-reseed guard is exactly the code that must not
 * mistake a new reference for a new value.
 */
function respondWith(build: () => StockVisibilityPolicyResponse) {
  service.getStockVisibility.mockImplementation(async () => build());
}

function renderSection(scope: StockVisibilityScope) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <StockVisibilitySection scope={scope} />
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}

async function waitForCard() {
  await waitFor(() => expect(screen.getByLabelText('Select mode')).toBeInTheDocument());
}

function modeSelect(): HTMLSelectElement {
  return screen.getByLabelText('Select mode') as HTMLSelectElement;
}

function chipLabels(): string[] {
  return screen.queryAllByTestId('location-chip').map((el) => el.textContent?.replace(/x$/, '') ?? '');
}

beforeEach(() => {
  pickers.real = false;
  vi.clearAllMocks();
  service.searchStockVisibilityWarehouses.mockResolvedValue([BRW, BRW_BB]);
  service.getDealerPoolWarehouses.mockResolvedValue([BRW, MWH, DC1]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('E1 - the policy in force, and where it comes from', () => {
  it('shows the effective mode, the locations as CODE - name, and the source badge', async () => {
    const own = policy('compact', [BRW, BRW_BB], 'contact');
    respondWith(() => ({ effective: own, override: own }));

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByText('Stock visibility')).toBeInTheDocument();
    expect(modeSelect().value).toBe('compact');
    expect(chipLabels()).toEqual(['BRW - Rawang Main Warehouse', 'BRW-BB - Rawang Bulk Bay']);
    expect(screen.getByText('Contact override')).toBeInTheDocument();
  });

  it('puts no UUID in the DOM, with the real Locations picker rendering the chips', async () => {
    // The stub renders `selectedOptions` and nothing else, so it could never have
    // shown an id whatever the card did. The claim is about the shared control,
    // so the shared control is what renders here.
    pickers.real = true;
    const own = policy('compact', [BRW, BRW_BB], 'contact');
    respondWith(() => ({ effective: own, override: own }));

    const { container } = renderSection(CONTACT_SCOPE);
    await waitFor(() =>
      expect(screen.getByText('BRW - Rawang Main Warehouse')).toBeInTheDocument(),
    );

    expect(screen.getByText('BRW-BB - Rawang Bulk Bay')).toBeInTheDocument();
    expect(container.innerHTML).not.toContain(BRW.id);
    expect(container.innerHTML).not.toContain(BRW_BB.id);
  });

  it('names the access type it inherits from, and reads Default at the floor of the chain', async () => {
    respondWith(() => ({
      effective: policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer'),
      override: null,
    }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByText('Access type: Dealer')).toBeInTheDocument();

    respondWith(() => {
      const row = policy('detailed', null, 'default');
      return { effective: row, override: row };
    });
    renderSection(DEFAULT_SCOPE);
    await waitFor(() => expect(screen.getAllByLabelText('Select mode')).toHaveLength(2));
    expect(screen.getByText('Default')).toBeInTheDocument();
  });
});

describe('E2 - the two controls', () => {
  beforeEach(() => {
    const own = policy('detailed', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
  });

  it('offers exactly the three modes, and does not let the admin clear the mode', async () => {
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    const options = within(modeSelect()).getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options.map((o) => o.textContent)).toEqual(['Detailed', 'Compact', 'Availability only']);
    expect(options.map((o) => (o as HTMLOptionElement).value)).toEqual([
      'detailed',
      'compact',
      'availability',
    ]);
    // A policy row always has a mode, so there is nothing to clear back to: the
    // card passes no `clearable` prop at all.
    expect(modeSelect().getAttribute('data-clearable')).toBe('unset');
  });

  it('renders no clear control on the real mode select', async () => {
    // What `clearable` actually decides, asserted where it is decided. Passing
    // the prop is only a proxy for this.
    pickers.real = true;
    renderSection(CONTACT_SCOPE);
    await waitFor(() => expect(screen.getByText('Detailed')).toBeInTheDocument());

    expect(screen.queryByLabelText('Clear selection')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
  });

  it('server-searches the locations rather than filtering a list it was handed', async () => {
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    const picker = screen.getByTestId('locations-picker');
    expect(picker.getAttribute('data-picker-mode')).toBe('async');
    expect(picker.getAttribute('data-static-option-count')).toBe('none');

    fireEvent.change(screen.getByLabelText('Search locations'), { target: { value: 'br' } });
    await waitFor(() =>
      expect(service.searchStockVisibilityWarehouses).toHaveBeenCalledWith('br'),
    );
    await waitFor(() =>
      expect(screen.getAllByTestId('location-result').map((el) => el.textContent)).toEqual([
        'BRW - Rawang Main Warehouse',
        'BRW-BB - Rawang Bulk Bay',
      ]),
    );
  });

  it('clears one chip at a time', async () => {
    const own = policy('detailed', [BRW, BRW_BB], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(chipLabels()).toHaveLength(2);

    fireEvent.click(screen.getByLabelText('Remove BRW - Rawang Main Warehouse'));
    await waitFor(() => expect(chipLabels()).toEqual(['BRW-BB - Rawang Bulk Bay']));
  });
});

describe('E3 - the Dealer pool preset', () => {
  it('replaces the selection with the segment=dealer warehouses', async () => {
    const own = policy('detailed', [BRW_BB], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(chipLabels()).toEqual(['BRW-BB - Rawang Bulk Bay']);

    fireEvent.click(screen.getByRole('button', { name: 'Dealer pool' }));

    await waitFor(() => expect(service.getDealerPoolWarehouses).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(chipLabels()).toEqual([
        'BRW - Rawang Main Warehouse',
        'MWH - Meru Warehouse',
        'DC1 - Distribution Centre 1',
      ]),
    );
    // Replaced, not appended: the preset IS the dealer pool, not an addition to it.
    expect(chipLabels()).not.toContain('BRW-BB - Rawang Bulk Bay');
  });
});

describe('E3 - the Dealer pool preset, when it comes back empty', () => {
  it('says so and leaves the selection alone', async () => {
    // An empty list is not a policy. Writing it would store `[]`, which means
    // "no stock at all" - the widest change on this card, made by a button the
    // admin pressed expecting three locations.
    const own = policy('detailed', [BRW_BB], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.getDealerPoolWarehouses.mockResolvedValue([]);

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.click(screen.getByRole('button', { name: 'Dealer pool' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('No dealer pool locations are configured'),
    );
    expect(chipLabels()).toEqual(['BRW-BB - Rawang Bulk Bay']);
  });
});

describe('E4 / E8 - Save', () => {
  it('sends the drafted mode and locations, then invalidates and toasts', async () => {
    const inherited = policy('detailed', [BRW, BRW_BB], 'default');
    respondWith(() => ({ effective: inherited, override: null }));
    const saved = policy('compact', [BRW, BRW_BB], 'contact');
    service.saveStockVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.change(modeSelect(), { target: { value: 'compact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'compact',
        warehouse_ids: [BRW.id, BRW_BB.id],
        hide_zero_locations: false,
      }),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Stock visibility saved'));
    // The write refreshes the tier it wrote, so the badge cannot go stale.
    await waitFor(() => expect(service.getStockVisibility.mock.calls.length).toBeGreaterThan(1));
  });

  it('reads "All locations" for a null list and saves warehouse_ids: null (E8)', async () => {
    const inherited = policy('detailed', null, 'default');
    respondWith(() => ({ effective: inherited, override: null }));
    const saved = policy('availability', null, 'contact');
    service.saveStockVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByTestId('locations-picker').getAttribute('data-placeholder')).toBe(
      'All locations',
    );
    expect(chipLabels()).toEqual([]);

    fireEvent.change(modeSelect(), { target: { value: 'availability' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'availability',
        warehouse_ids: null,
        hide_zero_locations: false,
      }),
    );
  });

  it('reads "No locations" for a stored empty list, and keeps it empty on Save (E8)', async () => {
    // `[]` and null are two different policies - "told about no stock at all" and
    // "told about every location". Both draw an empty picker, so a card that
    // cannot tell them apart shows the strictest policy as the loosest one, and
    // one Save turns it into that.
    const own = policy('compact', [], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.saveStockVisibility.mockResolvedValue({ effective: own, override: own });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByTestId('locations-picker').getAttribute('data-placeholder')).toBe(
      'No locations',
    );

    fireEvent.change(modeSelect(), { target: { value: 'availability' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'availability',
        warehouse_ids: [],
        hide_zero_locations: false,
      }),
    );
  });

  it('saves [] when the last chip is removed, and null when the field is cleared (E8)', async () => {
    const own = policy('compact', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.saveStockVisibility.mockResolvedValue({ effective: own, override: own });

    renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.click(screen.getByLabelText('Remove BRW - Rawang Main Warehouse'));
    await waitFor(() => expect(chipLabels()).toEqual([]));
    expect(screen.getByTestId('locations-picker').getAttribute('data-placeholder')).toBe(
      'No locations',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'compact',
        warehouse_ids: [],
        hide_zero_locations: false,
      }),
    );

    // The way back to "every location" - the picker itself can only ever hand
    // back a list, so removing the last chip cannot mean this.
    fireEvent.click(screen.getByRole('button', { name: 'All locations' }));
    await waitFor(() =>
      expect(screen.getByTestId('locations-picker').getAttribute('data-placeholder')).toBe(
        'All locations',
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenLastCalledWith(CONTACT_SCOPE, {
        mode: 'compact',
        warehouse_ids: null,
        hide_zero_locations: false,
      }),
    );
  });

  it('toasts the message the service extracted when the save is rejected', async () => {
    const own = policy('detailed', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.saveStockVisibility.mockRejectedValue(
      new Error('Unknown warehouse: 9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a09'),
    );

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    fireEvent.change(modeSelect(), { target: { value: 'compact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Unknown warehouse: 9f2c1d84-1b3a-4a0e-9b21-8c1f0d4e7a09',
      ),
    );
  });
});

describe('E5 - Remove override', () => {
  it('confirms in a dialog, deletes, and falls back to the inherited policy', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    const own = policy('compact', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    service.deleteStockVisibility.mockResolvedValue({
      effective: policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer'),
      override: null,
    });

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(screen.getByText('Contact override')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove override' }));

    // The dialog, not the browser prompt.
    await waitFor(() =>
      expect(
        screen.getByText(
          'This contact will fall back to the policy from its access type, or the default.',
        ),
      ).toBeInTheDocument(),
    );
    expect(service.deleteStockVisibility).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();

    // The refetch the invalidation fires must not put the deleted override back.
    respondWith(() => ({
      effective: policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer'),
      override: null,
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(service.deleteStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE),
    );
    await waitFor(() => expect(screen.getByText('Access type: Dealer')).toBeInTheDocument());
    await waitFor(() => expect(modeSelect().value).toBe('availability'));
    expect(screen.queryByRole('button', { name: 'Remove override' })).not.toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});

describe('Save enablement', () => {
  it('is disabled while a tier with its own row is untouched, and enabled once it is', async () => {
    const own = policy('compact', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    fireEvent.change(modeSelect(), { target: { value: 'availability' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
  });

  it('stays enabled on an inheriting tier even when the values still match', async () => {
    respondWith(() => ({
      effective: policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer'),
      override: null,
    }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    // Nothing is dirty, but there is no row yet - Save IS the act of creating one.
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });
});

describe('Draft re-seeding', () => {
  it('keeps a half-made edit when a background refetch brings no new policy VALUES', async () => {
    respondWith(() => ({
      effective: policy('detailed', [BRW], 'access_type', 'Dealer'),
      override: null,
    }));
    const { queryClient } = renderSection(CONTACT_SCOPE);
    await waitForCard();

    fireEvent.change(modeSelect(), { target: { value: 'availability' } });
    expect(modeSelect().value).toBe('availability');

    // The refetch really does land a DIFFERENT payload - the access type was renamed -
    // so react-query hands the card a new object and the effect runs again. The mode and
    // the id set are untouched, and those are the whole of what the draft is seeded from,
    // so re-seeding here would throw away an edit the admin is still making.
    respondWith(() => ({
      effective: policy('detailed', [BRW], 'access_type', 'Dealer (North)'),
      override: null,
    }));

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ['stock-visibility'] });
    });
    await waitFor(() => expect(screen.getByText('Access type: Dealer (North)')).toBeInTheDocument());

    expect(modeSelect().value).toBe('availability');
  });
});

describe('Scope parity', () => {
  it('writes the access-type row from the same card, with its own Remove', async () => {
    const own = policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer');
    respondWith(() => ({ effective: own, override: own }));
    service.saveStockVisibility.mockResolvedValue({ effective: own, override: own });

    renderSection(ACCESS_TYPE_SCOPE);
    await waitForCard();

    expect(screen.getByText('Access type: Dealer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove policy' })).toBeInTheDocument();

    fireEvent.change(modeSelect(), { target: { value: 'compact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(ACCESS_TYPE_SCOPE, {
        mode: 'compact',
        warehouse_ids: [BRW.id, MWH.id, DC1.id],
        hide_zero_locations: false,
      }),
    );
  });

  it('offers no Remove on the default tier - it is the floor of the chain', async () => {
    respondWith(() => {
      const row = policy('detailed', null, 'default');
      return { effective: row, override: row };
    });
    service.saveStockVisibility.mockResolvedValue({
      effective: policy('compact', null, 'default'),
      override: policy('compact', null, 'default'),
    });

    renderSection(DEFAULT_SCOPE);
    await waitForCard();

    expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument();

    fireEvent.change(modeSelect(), { target: { value: 'compact' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(DEFAULT_SCOPE, {
        mode: 'compact',
        warehouse_ids: null,
        hide_zero_locations: false,
      }),
    );
  });
});

describe('E9 - Hide zero-quantity locations', () => {
  function hideZeroSwitch(): HTMLElement {
    return screen.getByRole('switch', { name: 'Hide zero-quantity locations' });
  }

  it('renders the effective policy value, off and on', async () => {
    respondWith(() => {
      const own = policy('detailed', [BRW], 'contact');
      return { effective: own, override: own };
    });
    const off = renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(hideZeroSwitch()).toHaveAttribute('data-state', 'unchecked');
    off.unmount();

    respondWith(() => {
      const own = policy('compact', [BRW], 'contact', null, true);
      return { effective: own, override: own };
    });
    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(hideZeroSwitch()).toHaveAttribute('data-state', 'checked');
  });

  it('is inherited from the tier above, like the other two fields', async () => {
    // The card opens on the policy in FORCE, whichever tier wrote it, so a dealer
    // rule set once on the access type is what an inheriting contact shows.
    respondWith(() => ({
      effective: policy('compact', [BRW, MWH], 'access_type', 'Dealer', true),
      override: null,
    }));
    renderSection(CONTACT_SCOPE);
    await waitForCard();

    expect(screen.getByText('Access type: Dealer')).toBeInTheDocument();
    expect(hideZeroSwitch()).toHaveAttribute('data-state', 'checked');
  });

  it('toggling it is a change, and Save sends it with the rest of the row', async () => {
    const own = policy('compact', [BRW], 'contact');
    respondWith(() => ({ effective: own, override: own }));
    const saved = policy('compact', [BRW], 'contact', null, true);
    service.saveStockVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    // Nothing else touched, so Save is only reachable if the toggle is dirty.
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    fireEvent.click(hideZeroSwitch());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'compact',
        warehouse_ids: [BRW.id],
        hide_zero_locations: true,
      }),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Stock visibility saved'));
  });

  it('turns back off, and the round trip through the service shows the stored value', async () => {
    // A PUT replaces the whole row, so switching the toggle off has to reach the
    // API as `false` rather than as an omitted key the backend would default.
    const own = policy('compact', [BRW], 'contact', null, true);
    respondWith(() => ({ effective: own, override: own }));
    const saved = policy('compact', [BRW], 'contact');
    service.saveStockVisibility.mockResolvedValue({ effective: saved, override: saved });

    renderSection(CONTACT_SCOPE);
    await waitForCard();
    expect(hideZeroSwitch()).toHaveAttribute('data-state', 'checked');

    fireEvent.click(hideZeroSwitch());
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(CONTACT_SCOPE, {
        mode: 'compact',
        warehouse_ids: [BRW.id],
        hide_zero_locations: false,
      }),
    );
    // The write seeds the card from what came back, so the switch reads the
    // STORED value rather than the one that was clicked.
    await waitFor(() => expect(hideZeroSwitch()).toHaveAttribute('data-state', 'unchecked'));
  });

  it('is written on the access-type and default tiers from the same card', async () => {
    const own = policy('availability', [BRW, MWH, DC1], 'access_type', 'Dealer');
    respondWith(() => ({ effective: own, override: own }));
    service.saveStockVisibility.mockResolvedValue({ effective: own, override: own });

    renderSection(ACCESS_TYPE_SCOPE);
    await waitForCard();
    fireEvent.click(hideZeroSwitch());
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(service.saveStockVisibility).toHaveBeenCalledWith(ACCESS_TYPE_SCOPE, {
        mode: 'availability',
        warehouse_ids: [BRW.id, MWH.id, DC1.id],
        hide_zero_locations: true,
      }),
    );
  });
});
