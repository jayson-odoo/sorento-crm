/**
 * AFTER-SALES-P2 owner hand test (14 Nov): the product dropdown must not print the product code twice.
 * Both product pickers (job "Add product" and Rules "Test a product") follow the shared code + name rule
 * (`lib/product-display.ts` codeWithName): the name shows only when it differs from the code, joined by " - ".
 * Checked on every option and on the selected value, with the real dialog and the real SearchableSelect.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => undefined);

const PRODUCTS = [
  { id: 'p-cb', product_code: 'CB110', product_name: 'CB110' },
  { id: 'p-wc', product_code: 'SRTWC6020-SH-UF', product_name: 'Wall hung water closet' },
];

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/warranty',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => true }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  useRules: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }),
  useKindOptions: () => ({ data: [] }),
  useCreateRule: mut, useUpdateRule: mut,
  useTestKindRules: () => ({ mutateAsync: vi.fn(async () => null), isPending: false }),
}));
vi.mock('./RuleFormDialog', () => ({ RuleFormDialog: () => null }));
vi.mock('../../service-jobs/hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useServiceJobProductMutations: () => ({ add: mut(), update: mut() }),
}));
vi.mock('../../service-jobs/services/serviceJobService', () => ({
  searchCatalogueProducts: vi.fn(async () => PRODUCTS),
  getDefectOptions: vi.fn(async () => []),
}));
vi.mock('../services/warrantyConfigService', () => ({
  testKindRules: vi.fn(async () => null),
  getKinds: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 100 } })),
}));

import { RulesTab } from './RulesTab';
import ServiceJobProductsCard from '../../service-jobs/components/ServiceJobProductsCard';

const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

/** Each option's text, read from the open product dropdown. */
const optionTexts = async () => {
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('combobox', { name: 'Product' }));
  await screen.findByText('Wall hung water closet', { exact: false });
  return screen.getAllByRole('option').map((o) => (o.textContent ?? '').replace(/\s+/g, ' ').trim());
};

const codeOnce = (text: string, code: string) => text.split(code).length - 1;

const expectCodeOnce = async () => {
  const texts = await optionTexts();
  expect(texts).toContain('CB110');
  expect(texts).toContain('SRTWC6020-SH-UF - Wall hung water closet');
  for (const t of texts) {
    expect(codeOnce(t, 'CB110')).toBeLessThanOrEqual(1);
    expect(codeOnce(t, 'SRTWC6020-SH-UF')).toBeLessThanOrEqual(1);
  }
  // Pick the product whose name equals its code: the selected value shows the code once.
  await userEvent.click(screen.getAllByRole('option').find((o) => (o.textContent ?? '').includes('CB110')) as HTMLElement);
  const trigger = within(screen.getByRole('dialog')).getByRole('combobox', { name: 'Product' });
  expect(codeOnce(trigger.textContent ?? '', 'CB110')).toBe(1);
};

describe('product dropdowns show the product code once', () => {
  it('Rules tab, Test a product', async () => {
    wrap(<RulesTab />);
    fireEvent.click(screen.getByRole('button', { name: /Test a product/ }));
    await expectCodeOnce();
  });

  it('service job, Add product', async () => {
    wrap(<ServiceJobProductsCard jobId="j-1" canEdit />);
    await userEvent.click(screen.getByRole('button', { name: 'Add product' }));
    await expectCodeOnce();
  });
});
