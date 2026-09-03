/**
 * CertificateCoveredProducts - source encoded as colour, never as words.
 *   FE-7 (ONE legend above the list; the words "ai" / "manual" appear NOWHERE
 *     in the rendered rows - this is the point of this file. Source is carried
 *     by a colour dot plus chip border only)
 *   COV-2 (an AI-extracted link and a human-confirmed link are visually
 *     distinguishable without reading a badge)
 *   FE-7 unlink (removing a covered product is AlertDialog-confirmed, never one
 *     click) and add (searchable product select)
 *   FE-12 / cursor rule (no UUID is ever rendered)
 *   empty state
 *
 * SearchableSelect is stubbed to a native <select> with aria-label={placeholder}
 * so the product picker is deterministic under jsdom. The product-options
 * service and the coverage mutations are mocked.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

// DataGrid reads saved column preferences through react-query; the grid renders
// its rows fine in jsdom once this is stubbed.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    disabled,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const svc = vi.hoisted(() => ({ getCertificateProductOptions: vi.fn() }));
vi.mock('../services/certificateService', () => ({
  getCertificateProductOptions: (...a: unknown[]) => svc.getCertificateProductOptions(...a),
}));

const hooks = vi.hoisted(() => ({
  addAsync: vi.fn(),
  removeMutate: vi.fn(),
}));
vi.mock('../hooks/useCertificates', () => ({
  useAddCertificateProduct: () => ({ mutateAsync: hooks.addAsync, isPending: false }),
  useRemoveCertificateProduct: () => ({ mutate: hooks.removeMutate, isPending: false }),
}));

import CertificateCoveredProducts from './CertificateCoveredProducts';
import type { CertificateProduct } from '../types/certificate.types';

const AI_ROW: CertificateProduct = {
  id: 'cov-1',
  product_id: '9d1f0a2e-0000-4000-8000-000000000001',
  product_code: 'SR-1001',
  product_name: 'Close Coupled WC',
  company_name: 'Sorento',
  source: 'ai',
};

const MANUAL_ROW: CertificateProduct = {
  id: 'cov-2',
  product_id: '9d1f0a2e-0000-4000-8000-000000000002',
  product_code: 'SR-2002',
  product_name: 'Wall Hung Basin',
  company_name: 'Mocha',
  source: 'manual',
};

function renderPanel(products: CertificateProduct[]) {
  return render(<CertificateCoveredProducts certificateId="cert-1" products={products} />);
}

/** The grid body rows (one per covered product). */
function gridRows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('tbody tr')) as HTMLElement[];
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  svc.getCertificateProductOptions.mockResolvedValue([
    { value: 'prd-3', label: 'SR-3003 - Shower Mixer' },
  ]);
});

describe('CertificateCoveredProducts - empty state', () => {
  it('renders the grid empty message pointing at the picker', async () => {
    renderPanel([]);
    expect(
      await screen.findByText(/No product is covered yet\. Use the product picker above/i),
    ).toBeInTheDocument();
  });

  it('still renders the picker when nothing is covered', async () => {
    renderPanel([]);
    expect(await screen.findByLabelText('Add a product')).toBeInTheDocument();
  });
});

describe('CertificateCoveredProducts - paging', () => {
  it('pages a certificate that covers more products than one page holds', () => {
    // The live PPS 04424FC covers 68 products and WCM PC 000320 covers 90. A
    // grid that quietly renders only the first page hides most of the coverage.
    const many = Array.from({ length: 25 }, (_, i) => ({
      ...AI_ROW,
      id: `cov-${i}`,
      product_id: `9d1f0a2e-0000-4000-8000-0000000${String(i).padStart(5, '0')}`,
      product_code: `SR-${1000 + i}`,
    }));
    const { container } = renderPanel(many);
    // A pager is present and reports the true total, not the page size.
    expect(container.querySelector('[data-slot="card-footer"]')).toBeTruthy();
    expect(screen.getByText(/of\s*25/i)).toBeInTheDocument();
    expect(gridRows(container).length).toBeLessThan(25);
    expect(gridRows(container).length).toBeGreaterThan(0);
  });
});

describe('CertificateCoveredProducts - standard grid shape', () => {
  it('renders the documented columns', () => {
    renderPanel([AI_ROW, MANUAL_ROW]);
    ['Product Code', 'Product Name', 'Company', 'Added By'].forEach((header) => {
      expect(screen.getAllByText(header).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders one row per covered product, with code, name and company', () => {
    const { container } = renderPanel([AI_ROW, MANUAL_ROW]);
    const rows = gridRows(container);
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('SR-1001');
    expect(rows[0].textContent).toContain('Close Coupled WC');
    expect(rows[0].textContent).toContain('Sorento');
    expect(rows[1].textContent).toContain('SR-2002');
    expect(rows[1].textContent).toContain('Mocha');
  });

  it('shows every coverage row, including one from another company - no blank rows', () => {
    // Regression: certificate_products spans companies (AI extraction matches
    // codes across companies), and the row used to render blank outside the
    // viewer's own company scope.
    const otherCompanyRow: CertificateProduct = {
      id: 'cov-3',
      product_id: '9d1f0a2e-0000-4000-8000-000000000003',
      product_code: 'MC-3003',
      product_name: 'Kitchen Sink Mixer',
      company_name: 'Mocha',
      source: 'ai',
    };
    const { container } = renderPanel([AI_ROW, otherCompanyRow]);
    const rows = gridRows(container);
    expect(rows).toHaveLength(2);
    expect(rows[1].textContent).toContain('MC-3003');
    expect(rows[1].textContent).toContain('Kitchen Sink Mixer');
    expect(rows[1].textContent).toContain('Mocha');
  });

  it('truncates long text with a title attribute rather than overflowing', () => {
    const { container } = renderPanel([AI_ROW]);
    const cells = Array.from(gridRows(container)[0].querySelectorAll('div.truncate'));
    expect(cells.length).toBeGreaterThanOrEqual(3);
    expect(cells.every((c) => c.getAttribute('title'))).toBe(true);
  });
});

describe('CertificateCoveredProducts - source reads as a shared status pill', () => {
  it('labels the source in words a person can read, never the raw code', () => {
    const { container } = renderPanel([AI_ROW, MANUAL_ROW]);
    const rows = gridRows(container);
    expect(rows[0].textContent).toContain('From document');
    expect(rows[1].textContent).toContain('Confirmed');
    // The raw enum never reaches the row.
    expect(rows[0].textContent).not.toMatch(/\bai\b/i);
    expect(rows[1].textContent).not.toMatch(/\bmanual\b/i);
  });

  it('uses the SHARED pill classes, not a per-feature colour scheme', () => {
    const { container } = renderPanel([AI_ROW, MANUAL_ROW]);
    const rows = gridRows(container);
    const pill = (row: HTMLElement) =>
      Array.from(row.querySelectorAll('span')).find((el) =>
        el.className.includes('rounded-full'),
      ) as HTMLElement;
    expect(pill(rows[0]).className).toContain('rounded-full');
    expect(pill(rows[1]).className).toContain('rounded-full');
    // The two sources stay visually distinguishable.
    expect(pill(rows[0]).className).not.toEqual(pill(rows[1]).className);
  });

  it('never renders a UUID', () => {
    const { container } = renderPanel([AI_ROW, MANUAL_ROW]);
    expect(container.textContent ?? '').not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});

describe('CertificateCoveredProducts - add coverage', () => {
  it('offers only products that are not covered yet', async () => {
    svc.getCertificateProductOptions.mockResolvedValue([
      { value: AI_ROW.product_id, label: 'SR-1001 - Close Coupled WC' },
      { value: 'prd-3', label: 'SR-3003 - Shower Mixer' },
    ]);
    renderPanel([AI_ROW]);
    const select = await screen.findByLabelText('Add a product');
    await waitFor(() =>
      expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toContain(
        'SR-3003 - Shower Mixer',
      ),
    );
    expect(
      Array.from(select.querySelectorAll('option')).map((o) => o.textContent),
    ).not.toContain('SR-1001 - Close Coupled WC');
  });

  it('Add is disabled until a product is picked, then posts the link', async () => {
    hooks.addAsync.mockResolvedValue({});
    renderPanel([]);
    const addButton = screen.getByRole('button', { name: /^Add$/ });
    expect(addButton).toBeDisabled();
    const select = await screen.findByLabelText('Add a product');
    await waitFor(() => expect(select.querySelectorAll('option')).toHaveLength(2));
    fireEvent.change(select, { target: { value: 'prd-3' } });
    fireEvent.click(screen.getByRole('button', { name: /^Add$/ }));
    await waitFor(() =>
      expect(hooks.addAsync).toHaveBeenCalledWith({ id: 'cert-1', productId: 'prd-3' }),
    );
  });

  it('survives a failing options load by offering an empty picker', async () => {
    svc.getCertificateProductOptions.mockRejectedValue(new Error('boom'));
    renderPanel([]);
    const select = await screen.findByLabelText('Add a product');
    // Only the placeholder option.
    await waitFor(() => expect(select.querySelectorAll('option')).toHaveLength(1));
    expect(screen.getByRole('button', { name: /^Add$/ })).toBeDisabled();
  });
});

describe('CertificateCoveredProducts - unlink is confirm-gated (FE-7)', () => {
  it('does not remove on the first click; it opens a confirmation naming the product', async () => {
    renderPanel([AI_ROW, MANUAL_ROW]);
    fireEvent.click(screen.getByLabelText('Remove SR-1001 from coverage'));
    expect(hooks.removeMutate).not.toHaveBeenCalled();
    expect(await screen.findByText('Confirm remove')).toBeInTheDocument();
    expect(
      screen.getByText(
        /SR-1001 will stop being covered by this certificate, and the certificate will no longer be served on that product page\./i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/i)).toBeInTheDocument();
  });

  it('confirming removes that coverage row (by coverage id, not product id)', async () => {
    renderPanel([AI_ROW, MANUAL_ROW]);
    fireEvent.click(screen.getByLabelText('Remove SR-2002 from coverage'));
    fireEvent.click(await screen.findByRole('button', { name: /^Remove$/ }));
    await waitFor(() => expect(hooks.removeMutate).toHaveBeenCalledTimes(1));
    expect(hooks.removeMutate.mock.calls[0][0]).toEqual({ id: 'cert-1', coverageId: 'cov-2' });
  });

  it('cancelling leaves the coverage alone', async () => {
    renderPanel([AI_ROW]);
    fireEvent.click(screen.getByLabelText('Remove SR-1001 from coverage'));
    fireEvent.click(await screen.findByRole('button', { name: /^Cancel$/ }));
    await waitFor(() => expect(screen.queryByText('Confirm remove')).toBeNull());
    expect(hooks.removeMutate).not.toHaveBeenCalled();
  });
});
