/**
 * S3 - PricingConfigClient (AC-E5, AC-E8, AC-E9).
 *
 * The two things worth pinning are that a floor is READABLE as a sentence rather than as
 * a mode plus a number, and that the list keeps the server's specificity order. An admin
 * who cannot tell which rule wins cannot set the rules.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PriceFloorRule, ProjectSeries } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listSeries = vi.fn();
const listPriceFloors = vi.fn();

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listSeries: (...args: unknown[]) => listSeries(...args),
    listPriceFloors: (...args: unknown[]) => listPriceFloors(...args),
  };
});

vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));

vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query',
  () => ({ useProductCategorySelectQuery: () => ({ data: [] }) }),
);

import { PricingConfigClient } from './PricingConfigClient';

function series(overrides: Partial<ProjectSeries> = {}): ProjectSeries {
  return {
    id: 's1',
    name: 'Sorento Project Series',
    is_active: true,
    category_ids: ['c1'],
    category_names: ['Basins'],
    covered_category_count: 4,
    quotation_count: 0,
    ...overrides,
  };
}

function floor(overrides: Partial<PriceFloorRule> = {}): PriceFloorRule {
  return {
    id: 'f1',
    mode: 'percent',
    value: '70.00',
    is_active: true,
    level: 'system',
    ...overrides,
  };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PricingConfigClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listSeries.mockResolvedValue([]);
  listPriceFloors.mockResolvedValue([]);
});

describe('PricingConfigClient', () => {
  it('says what is lost while no series exists', async () => {
    renderClient();

    expect(await screen.findByText(/No series yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no line is ever flagged as off-series/i)).toBeInTheDocument();
  });

  it('says what is lost while no floor exists', async () => {
    renderClient();

    expect(await screen.findByText(/No floors set/i)).toBeInTheDocument();
    expect(
      screen.getByText(/accepted without an alert until at least one floor exists/i),
    ).toBeInTheDocument();
  });

  it('separates the categories nominated from the categories covered', async () => {
    listSeries.mockResolvedValue([
      series({ category_ids: ['c1', 'c2'], covered_category_count: 11 }),
    ]);

    renderClient();

    // 2 picks, 11 categories actually judged against. The second number is the one that
    // decides whether a line is flagged, so both have to be visible.
    expect(await screen.findByText('2 nominated, 11 covered')).toBeInTheDocument();
  });

  it('reads a percent floor and an absolute floor as sentences', async () => {
    listPriceFloors.mockResolvedValue([
      floor({ id: 'f1', level: 'product', product_code: 'SRT-WC-01', mode: 'percent', value: '85.00' }),
      floor({ id: 'f2', level: 'category', category_name: 'Basins', mode: 'absolute', value: '150.00' }),
    ]);

    renderClient();

    expect(await screen.findByText(/At least 85% of the list price/)).toBeInTheDocument();
    expect(
      screen.getByText(/At least RM 150, whatever the list price says/),
    ).toBeInTheDocument();
  });

  it('labels the company-wide rule as the fallback it is', async () => {
    listPriceFloors.mockResolvedValue([floor({ level: 'system' })]);

    renderClient();

    expect(await screen.findByText('Company default')).toBeInTheDocument();
    expect(
      screen.getByText('Everything without a more specific rule'),
    ).toBeInTheDocument();
  });

  it('warns that deleting a floor leaves already-priced lines alone', async () => {
    listPriceFloors.mockResolvedValue([
      floor({ level: 'category', category_name: 'Basins' }),
    ]);

    renderClient();

    fireEvent.click(await screen.findByRole('button', { name: /Delete floor/i }));

    expect(
      await screen.findByText(/Lines already priced keep the floor that applied to them/i),
    ).toBeInTheDocument();
  });

  it('tells the admin to deactivate a series a quotation still uses', async () => {
    listSeries.mockResolvedValue([series({ quotation_count: 3 })]);

    renderClient();

    expect(await screen.findByText('Used by 3 quotations')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: /Delete Sorento Project Series/i }),
    );

    expect(await screen.findByText(/deactivate it instead/i)).toBeInTheDocument();
  });
});
