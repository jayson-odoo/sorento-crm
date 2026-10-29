/**
 * LEAD-GOVERNS-REGISTER LGR-C1: no visible "buyer" word on the lead page or in its edit dialog.
 * The tab id `buyer` and the listing keys stay, so they are not asserted.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectLead } from '../../../_shared/types/project.types';
import type { LeadWithAcceptance } from '../../../_shared/types/leadAcceptance.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const getLead = vi.fn();
const updateLead = vi.fn();
const getCustomerPortfolio = vi.fn();
const listCustomerOptions = vi.fn();
const acceptLead = vi.fn();
const declineLead = vi.fn();
const assignLead = vi.fn();
const getUserLookup = vi.fn();

let sessionUserId: string | undefined = 'u-ali';

/**
 * The router mock is reactive on purpose. The component reads the active tab from the
 * URL and writes it back with `replace`, so a mock that only records the call would let
 * a broken read pass: clicking a tab has to actually change what is on screen.
 */
let currentSearch = '';
const searchListeners = new Set<() => void>();
const subscribeSearch = (listener: () => void) => {
  searchListeners.add(listener);
  return () => {
    searchListeners.delete(listener);
  };
};
const readSearch = () => currentSearch;
const routerPush = vi.fn();
const routerReplace = vi.fn((url: string) => {
  const marker = url.indexOf('?');
  currentSearch = marker === -1 ? '' : url.slice(marker + 1);
  searchListeners.forEach((listener) => listener());
});

// The pager has its own tests; here it is only the first slot in the group.
vi.mock('@/components/common/ListPager', () => ({
  __esModule: true,
  default: () => <div data-testid="pager-slot" />,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  // Without this the grid never leaves its skeleton: the real hook fetches saved column
  // order and `isLoading` gates the body rows, and nothing answers that call under jsdom.
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  // The shared DataGrid falls back to the pathname when no listingKey is given, so every
  // tab that now renders a grid needs this present on the mock.
  usePathname: () => '/project-sales/leads/lead-1',
  useSearchParams: () =>
    new URLSearchParams(
      React.useSyncExternalStore(subscribeSearch, readSearch, readSearch),
    ),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: sessionUserId ? { user: { id: sessionUserId } } : null,
    status: 'authenticated',
  }),
}));

vi.mock(
  '@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph',
  () => ({ useProjectStatusGraph: () => ({ data: { statuses: [] }, isLoading: false }) }),
);

vi.mock('../../../_shared/services/projectService', () => ({
  getLead: (...args: unknown[]) => getLead(...args),
  updateLead: (...args: unknown[]) => updateLead(...args),
  getCustomerPortfolio: (...args: unknown[]) => getCustomerPortfolio(...args),
  listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
  listParties: vi.fn(async () => ({
    data: [],
    pagination: { total: 0, page: 1, limit: 200 },
  })),
  listProjectTypes: vi.fn(async () => []),
  listProjectTemplates: vi.fn(async () => []),
  listLeads: vi.fn(),
  createLead: vi.fn(),
  changeLeadStatus: vi.fn(),
  previewQualify: vi.fn(),
  qualifyLead: vi.fn(),
  disqualifyLead: vi.fn(),
  reopenLead: vi.fn(),
  deleteLead: vi.fn(),
  listDisqualifyReasons: vi.fn(async () => []),
  getLeadMetrics: vi.fn(),
  listProjects: vi.fn(),
}));

vi.mock('../../../_shared/services/leadAcceptanceService', () => ({
  listAwaitingAcceptance: vi.fn(),
  assignLead: (...args: unknown[]) => assignLead(...args),
  acceptLead: (...args: unknown[]) => acceptLead(...args),
  declineLead: (...args: unknown[]) => declineLead(...args),
  nudgeLeadAssignee: vi.fn(),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: (...args: unknown[]) => getUserLookup(...args),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => {
  type Opt = { value: string; label: string };
  function AsyncSelect({
    id,
    onChange,
    fetchOptions,
  }: {
    id?: string;
    onChange: (next: string) => void;
    fetchOptions: (query: string, page: number) => Promise<Opt[]>;
  }) {
    const [query, setQuery] = React.useState('');
    const [results, setResults] = React.useState<Opt[]>([]);
    return (
      <span>
        <input
          id={id}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            void fetchOptions(event.target.value, 0).then(setResults);
          }}
        />
        {results.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => {
              onChange(option.value);
              setResults([]);
              setQuery(option.label);
            }}
          >
            {option.label}
          </button>
        ))}
      </span>
    );
  }
  return {
    SearchableSelect: (props: Record<string, unknown>) => {
      if (props.fetchOptions) return <AsyncSelect {...(props as never)} />;
      const { value, onChange, options, placeholder } = props as {
        value: string;
        onChange: (next: string) => void;
        options?: Opt[];
        placeholder?: string;
      };
      return (
        <select
          aria-label={placeholder ?? 'select'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{placeholder ?? ''}</option>
          {(options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    },
  };
});

import { LeadDetailClient } from './LeadDetailClient';

function lead(overrides: Partial<LeadWithAcceptance> = {}): ProjectLead {
  const row: LeadWithAcceptance = {
    id: 'l1',
    lead_code: 'LEAD-000001',
    title: 'Tower behind the showroom',
    customer_id: null,
    customer_name: null,
    developer_name: 'Setia Land',
    location: 'Setia Alam',
    outcome: 'open',
    // The header pill shows the RUNG now, not the derived outcome, so the fixture carries one.
    status_id: 's-new',
    status_key: 'new',
    status_label: 'New',
    project_count: 0,
    possible_duplicates: [],
    can_edit: true,
    informant_source: 'bci',
    informant_ref: 'BCI-778812',
    informant_party_id: '11111111-1111-1111-1111-111111111111',
    informant_party_label: 'Veritas Architects Sdn Bhd',
    informant_contact_name: 'Lim, QS',
    acceptance_state: 'assigned',
    owner_user_id: 'u-ali',
    owner_name: 'Ali',
    assigned_at: new Date(Date.now() - 50 * 3_600_000).toISOString().replace('Z', ''),
    ...overrides,
  };
  return row as ProjectLead;
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadDetailClient leadId="l1" />
    </QueryClientProvider>,
  );
}

/**
 * Tabs are the shared `Tabs` strip since S4, exactly as on the project detail
 * page: `role="tablist"` / `role="tab"`, and the open one is `aria-selected`
 * rather than the `aria-current="page"` the hand-rolled `<nav>` set.
 */
/** Secondary actions live behind the gear now. Radix opens on pointerdown, not click. */
function openGearMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Lead actions' }), {
    button: 0,
    ctrlKey: false,
  });
}

async function openTab(name: string) {
  // Radix activates a tab on mousedown, which jsdom does not synthesize
  // from a click.
  fireEvent.mouseDown(await screen.findByRole('tab', { name }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  currentSearch = '';
  sessionUserId = 'u-ali';
  getLead.mockResolvedValue(lead());
  updateLead.mockResolvedValue(lead());
  acceptLead.mockResolvedValue(lead({ acceptance_state: 'accepted' }));
  declineLead.mockResolvedValue(
    lead({ acceptance_state: 'declined', owner_user_id: null, owner_name: null }),
  );
  assignLead.mockResolvedValue(lead());
  getCustomerPortfolio.mockResolvedValue({ leads: [], projects: [] });
  getUserLookup.mockResolvedValue([
    { id: 'u-siti', name: 'Siti' },
  ]);
});


describe('LGR-C1 no visible buyer word on the lead page', () => {
  it('a customerless lead: Customer tab says No customer yet and offers Set the customer', async () => {
    renderDetail();
    await openTab('Customer');
    expect(await screen.findByText('No customer yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Set the customer' }));
    expect(await screen.findByText('Who told us, and the customer')).toBeInTheDocument();
    expect(screen.queryByText(/buyer/i)).toBeNull();
  });

  it('a lead with a customer: related lists read "<name> - other leads" / "<name> - projects" with customer empty text', async () => {
    getLead.mockResolvedValue(lead({ customer_id: 'c1', customer_name: 'KEDAI CONTOH SDN. BHD.' }));
    renderDetail();
    await openTab('Customer');
    expect(await screen.findByText('KEDAI CONTOH SDN. BHD. - other leads')).toBeInTheDocument();
    expect(screen.getByText('KEDAI CONTOH SDN. BHD. - projects')).toBeInTheDocument();
    expect(screen.getByText('No other leads on this customer')).toBeInTheDocument();
    expect(screen.queryByText(/buyer/i)).toBeNull();
  });

  it('the Who told us tab and its edit dialog show no buyer word', async () => {
    renderDetail();
    await openTab('Who told us');
    expect(screen.queryByText(/buyer/i)).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Who told us, and the customer')).toBeInTheDocument();
    expect(within(dialog).queryByText(/buyer/i)).toBeNull();
    expect(screen.queryByText(/buyer/i)).toBeNull();
  });
});
