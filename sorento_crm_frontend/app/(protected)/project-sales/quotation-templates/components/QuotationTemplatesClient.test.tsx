import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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
      { id: 't1', kind: 'terms', name: 'Standard 2026', body_html: '<p>x</p>', is_active: true },
      { id: 't2', kind: 'terms', name: 'Older wording', body_html: '<p>y</p>', is_active: false },
    ],
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useQuotationTemplateMutations: () => ({
    activate: { mutate: activate, isPending: false },
    create: { mutateAsync: vi.fn(), isPending: false },
    update: { mutateAsync: vi.fn(), isPending: false },
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
