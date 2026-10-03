/**
 * CONTACT-COMPANYLESS AC5 + AC7: the chatbot usual products / brands / sites pickers
 * ask for every GRANTED company (`company_scope=grants`) and label each option
 * `<Company> · <label>`, always. Asserted at the `apiFetch` seam, so it holds whichever
 * shared service the loader goes through.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('./contactService', () => ({ getContact: vi.fn() }));

import {
  searchUsualBrandOptions,
  searchUsualProductOptions,
  searchUsualSiteOptions,
} from './contactChatbotService';

function ok(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function lastUrl(): URL {
  const [url] = apiFetch.mock.calls[apiFetch.mock.calls.length - 1] as [string];
  return new URL(url, 'http://localhost');
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('usual products', () => {
  it('sends company_scope=grants and prefixes the company on each option', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            id: 'p-1',
            product_code: 'SKU-1',
            product_name: 'Basin',
            company_id: 'co-2',
            company_name: 'Mocha',
          },
        ],
      }),
    );

    const options = await searchUsualProductOptions('sku');

    const url = lastUrl();
    expect(url.pathname).toBe('/api/v1/master-data/products/select');
    expect(url.searchParams.get('company_scope')).toBe('grants');
    expect(options).toEqual([{ value: 'SKU-1', label: 'Mocha · SKU-1 - Basin' }]);
  });
});

describe('usual brands', () => {
  it('sends company_scope=grants and prefixes the company; the stored value stays the brand name', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            id: 'b-1',
            brand_code: 'MB',
            brand_name: 'Mocha Brand',
            company_id: 'co-2',
            company_name: 'Mocha',
          },
        ],
        pagination: { total: 1, page: 1, limit: 20 },
      }),
    );

    const options = await searchUsualBrandOptions('mocha');

    const url = lastUrl();
    expect(url.pathname).toMatch(/^\/api\/v1\/master-data\/brands/);
    expect(url.searchParams.get('company_scope')).toBe('grants');
    expect(options).toEqual([{ value: 'Mocha Brand', label: 'Mocha · Mocha Brand' }]);
  });
});

describe('usual sites', () => {
  it('sends company_scope=grants and prefixes the company; the stored value stays the warehouse name', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            id: 'w-1',
            warehouse_code: 'MOCHA-WH',
            warehouse_name: 'Mocha Site',
            company_id: 'co-2',
            company_name: 'Mocha',
          },
        ],
        pagination: { total: 1, page: 1, limit: 20 },
      }),
    );

    const options = await searchUsualSiteOptions('mocha');

    const url = lastUrl();
    expect(url.pathname).toMatch(/^\/api\/v1\/inventory\/warehouses/);
    expect(url.searchParams.get('company_scope')).toBe('grants');
    expect(options).toEqual([{ value: 'Mocha Site', label: 'Mocha · Mocha Site' }]);
  });
});
