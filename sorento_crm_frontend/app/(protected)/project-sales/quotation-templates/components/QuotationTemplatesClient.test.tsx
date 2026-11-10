import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const activate = vi.fn();
const createAsync = vi.fn(async () => ({}));
const updateAsync = vi.fn(async () => ({}));
let canEdit = true;

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/quotation-templates',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => canEdit,
}));

vi.mock('@/components/ui/rich-text-editor', () => ({
  RichTextEditor: () => <div data-testid="editor" />,
}));

vi.mock('../../_shared/hooks/useQuotationTemplates', () => ({
  useQuotationTemplates: () => ({
    data: [
      {
        id: 't1',
        kind: 'terms',
        name: 'Standard 2026',
        body_html: '<p>x</p>',
        is_active: true,
        payment_terms: '30 days net',
        validity: '60 days',
      },
      { id: 't2', kind: 'terms', name: 'Older wording', body_html: '<p>y</p>', is_active: false },
    ],
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useQuotationTemplateMutations: () => ({
    activate: { mutate: activate, isPending: false },
    create: { mutateAsync: (...args: unknown[]) => (createAsync as (...a: unknown[]) => unknown)(...args), isPending: false },
    update: { mutateAsync: (...args: unknown[]) => (updateAsync as (...a: unknown[]) => unknown)(...args), isPending: false },
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">none</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('../../_shared/hooks/usePaymentTerms', () => ({
  usePaymentTermOptions: () => ({
    data: [{ id: 'pt-cbd', code: 'C.B.D.', description: 'CASH BEFORE DELIVERY', label: 'CASH BEFORE DELIVERY' }],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

import { QuotationTemplatesClient } from './QuotationTemplatesClient';

beforeEach(() => {
  vi.clearAllMocks();
  canEdit = true;
});

describe('QuotationTemplatesClient', () => {
  it('activates only the inactive template', () => {
    render(<QuotationTemplatesClient />);
    const buttons = screen.getAllByRole('button', { name: 'Activate' });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(activate).toHaveBeenCalledWith('t2');
  });

  it('opens the add modal from the single toolbar button', () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByRole('button', { name: /Add template/i }));
    expect(screen.getByTestId('editor')).toBeTruthy();
  });

  it('hides write actions without projects.types.edit', () => {
    canEdit = false;
    render(<QuotationTemplatesClient />);
    expect(screen.queryByRole('button', { name: 'Activate' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add template/i })).toBeNull();
  });
});

/** QUOTE-COVER-PAGE (UAC D2) + QUOTE-TERMS-SELECT: Payment Terms (a synced AutoCount term) and
 *  Validity (number + unit) beside the terms text; a legacy text is kept until someone picks. */
describe('QuotationTemplatesClient payment terms and validity', () => {
  it('the add dialog has an empty Payment Terms select and an empty Validity', () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByRole('button', { name: /Add template/i }));
    expect(screen.getByLabelText('Payment Terms')).toHaveValue('');
    expect(screen.getByLabelText('Validity')).toHaveValue(null);
  });

  it('the edit dialog shows the legacy texts and save sends only what was picked', async () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByText('Standard 2026'));

    await screen.findByLabelText('Payment Terms');
    expect(screen.getByText('Current: 30 days net')).toBeTruthy();
    expect(screen.getByText('Current: 60 days')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Payment Terms'), { target: { value: 'pt-cbd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
    const call = (updateAsync.mock.calls as unknown as [{ id: string; body: Record<string, unknown> }][])[0][0];
    expect(call.id).toBe('t1');
    expect(call.body).toMatchObject({
      payment_term_id: 'pt-cbd',
      payment_terms: 'CASH BEFORE DELIVERY',
    });
    // The untouched legacy validity is not sent, so it keeps printing.
    expect(call.body).not.toHaveProperty('validity');
    expect(call.body).not.toHaveProperty('validity_value');
  });

  it('an invalid validity on screen blocks Save (crew pass 538d14b7)', async () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByText('Standard 2026'));
    fireEvent.change(await screen.findByLabelText('Validity'), { target: { value: '0' } });
    expect(screen.getByText('Enter a whole number from 1 to 999.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '3' } });
    expect(screen.getByText('Pick a unit.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    expect(updateAsync).not.toHaveBeenCalled();
  });

  it('save sends a validity as a number and a unit', async () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByText('Standard 2026'));
    fireEvent.change(await screen.findByLabelText('Validity'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Validity unit'), { target: { value: 'week' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
    expect(updateAsync).toHaveBeenCalledWith({
      id: 't1',
      body: expect.objectContaining({ validity_value: 2, validity_unit: 'week', validity: '2 WEEKS' }),
    });
  });
});
