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

/** QUOTE-COVER-PAGE (UAC D2): Payment Terms and Validity beside the terms text. */
describe('QuotationTemplatesClient payment terms and validity', () => {
  it('the add dialog has Payment Terms and Validity inputs, empty', () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByRole('button', { name: /Add template/i }));
    expect(screen.getByLabelText('Payment Terms')).toHaveValue('');
    expect(screen.getByLabelText('Validity')).toHaveValue('');
  });

  it('the edit dialog opens with the saved values and save sends the changed ones', async () => {
    render(<QuotationTemplatesClient />);
    fireEvent.click(screen.getByText('Standard 2026'));

    const payment = await screen.findByLabelText('Payment Terms');
    expect(payment).toHaveValue('30 days net');
    expect(screen.getByLabelText('Validity')).toHaveValue('60 days');
    fireEvent.change(payment, { target: { value: '14 days net' } });
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '30 days' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(updateAsync).toHaveBeenCalledTimes(1));
    expect(updateAsync).toHaveBeenCalledWith({
      id: 't1',
      body: expect.objectContaining({ payment_terms: '14 days net', validity: '30 days' }),
    });
  });
});
