/**
 * S3 - QuotationsPanel (AC-E1, AC-E6, AC-E10).
 *
 * What is worth pinning is that a scope is readable WITHOUT opening it: its outcome, its
 * version position, its total and both alerts. The alerts are the whole point of the
 * guardrail, so a panel that only showed them once expanded would hide the thing
 * management asked for.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectQuotation,
  QuotationVersion,
} from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listQuotations = vi.fn();
const listQuotationVersions = vi.fn();
const listQuotationLines = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  // Without this the grid never leaves its skeleton: the real hook fetches saved column
  // order and `isLoading` gates the body rows, and nothing answers that call under jsdom.
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listQuotations: (...args: unknown[]) => listQuotations(...args),
    listQuotationVersions: (...args: unknown[]) => listQuotationVersions(...args),
    listQuotationLines: (...args: unknown[]) => listQuotationLines(...args),
    listSeries: vi.fn(async () => []),
    listQuotationLossReasons: vi.fn(async () => []),
  };
});

import { QuotationsPanel } from './QuotationsPanel';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

function quotation(overrides: Partial<ProjectQuotation> = {}): ProjectQuotation {
  return {
    id: 'q1',
    project_id: 'p1',
    scope_label: 'House Units',
    outcome: 'open',
    version_count: 1,
    current_version_id: 'v1',
    current_version_no: 1,
    current_total: '12000.00',
    below_floor_count: 0,
    non_standard_count: 0,
    line_count: 0,
    ...overrides,
  };
}

function version(overrides: Partial<QuotationVersion> = {}): QuotationVersion {
  return {
    id: 'v1',
    quotation_id: 'q1',
    version_no: 1,
    is_current: true,
    total_amount: '12000.00',
    ...overrides,
  };
}

function renderPanel(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationsPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listQuotations.mockResolvedValue([]);
  listQuotationVersions.mockResolvedValue([version()]);
  listQuotationLines.mockResolvedValue([]);
});

describe('QuotationsPanel', () => {
  it('offers the first scope when nothing is priced', async () => {
    renderPanel();

    expect(await screen.findByText(/Nothing priced yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Add the first scope/i }),
    ).toBeInTheDocument();
  });

  it('reads a scope without opening it: version position, total and outcome', async () => {
    listQuotations.mockResolvedValue([
      quotation({ version_count: 3, current_version_no: 3, current_total: '48250.50' }),
    ]);

    renderPanel();

    // The name appears twice once a scope is open: in its row, and as the heading of the
    // version editor that opens beneath the list.
    expect((await screen.findAllByText('House Units')).length).toBeGreaterThan(0);
    expect(screen.getByText('v3 of 3')).toBeInTheDocument();
    expect(screen.getByText('RM 48,250.50')).toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
  });

  it('surfaces both alerts per scope and totals them across scopes', async () => {
    listQuotations.mockResolvedValue([
      quotation({
        id: 'q1',
        scope_label: 'House Units',
        below_floor_count: 2,
        non_standard_count: 1,
      }),
      quotation({
        id: 'q2',
        scope_label: 'Common Area',
        current_version_id: 'v2',
        below_floor_count: 1,
        non_standard_count: 3,
      }),
    ]);

    renderPanel();

    // Per scope...
    expect(await screen.findByText('2 below floor')).toBeInTheDocument();
    expect(screen.getByText('1 below floor')).toBeInTheDocument();
    expect(screen.getByText('1 non-standard')).toBeInTheDocument();
    expect(screen.getByText('3 non-standard')).toBeInTheDocument();
    // ...and the roll-up, so a project with ten scopes still shows one number.
    expect(screen.getByText('3 below the price floor')).toBeInTheDocument();
    expect(screen.getByText('4 non-standard')).toBeInTheDocument();
  });

  it('names the loss reason on a lost scope', async () => {
    listQuotations.mockResolvedValue([
      quotation({
        outcome: 'lost',
        loss_reason: 'price',
        loss_reason_label: 'Price too high',
      }),
    ]);

    renderPanel();

    expect(await screen.findByText('Lost')).toBeInTheDocument();
    // Its own column, so the reason no longer needs the "Lost:" prefix to be readable.
    expect(screen.getByText('Price too high')).toBeInTheDocument();
  });

  it('warns that deleting a scope takes every version with it', async () => {
    listQuotations.mockResolvedValue([quotation({ version_count: 4 })]);

    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /Delete House Units/i }));

    expect(
      await screen.findByText(/all 4 of its versions/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });

  it('hides every write affordance on a project the user cannot edit', async () => {
    listQuotations.mockResolvedValue([quotation()]);

    renderPanel({ can_edit: false });

    expect((await screen.findAllByText('House Units')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Add a scope/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Record outcome/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete House Units/i })).toBeNull();
  });

  it('opens the first scope on arrival rather than waiting for a click', async () => {
    listQuotations.mockResolvedValue([quotation()]);

    renderPanel();

    await screen.findAllByText('House Units');
    // The version editor mounting is what proves it: it only queries when a scope is open.
    await waitFor(() => expect(listQuotationVersions).toHaveBeenCalledWith('q1'));
  });
});
