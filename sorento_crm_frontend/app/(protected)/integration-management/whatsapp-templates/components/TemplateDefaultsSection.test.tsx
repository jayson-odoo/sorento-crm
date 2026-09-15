/**
 * AC-S6-4 (PLAN-price-tag-ai-extract-resolver.md D10): the WhatsApp Templates
 * settings page renders a "Price Tag Request - Update" row in the update
 * group, showing "Set template" when no default is configured for
 * `price_tag_update` yet.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/services/whatsappTemplateService', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('@/services/whatsappTemplateService')>();
  return {
    ...original,
    listTemplateDefaults: vi.fn(async () => []),
    clearTemplateDefault: vi.fn(),
  };
});

vi.mock('./SetDefaultTemplateDialog', () => ({
  __esModule: true,
  default: () => null,
}));

import TemplateDefaultsSection from './TemplateDefaultsSection';

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TemplateDefaultsSection />
    </QueryClientProvider>,
  );
}

describe('TemplateDefaultsSection - price_tag_update row (AC-S6-4)', () => {
  it('renders a "Price Tag Request - Update" row with "Set template" when unset', async () => {
    renderSection();

    const row = await screen.findByTestId('default-row-price_tag_update');
    expect(within(row).getByText('Price Tag Request - Update')).toBeInTheDocument();
    expect(within(row).getByText('Not set')).toBeInTheDocument();
    expect(
      within(row).getByRole('button', { name: /Set template/ }),
    ).toBeInTheDocument();
  });
});
