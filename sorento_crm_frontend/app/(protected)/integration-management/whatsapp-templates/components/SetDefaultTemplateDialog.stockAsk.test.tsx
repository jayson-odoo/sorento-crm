import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SetDefaultTemplateDialog from './SetDefaultTemplateDialog';
import { PARAM_VARIABLES, USE_CASES } from '@/services/whatsappTemplateService';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/whatsappTemplateService')
  >('@/services/whatsappTemplateService');
  return { ...actual, listApprovedTemplates: vi.fn().mockResolvedValue([]), setTemplateDefault: vi.fn() };
});

// Chatbot stock ask v2 S4, AC-SA409 [FE]: the salesman notification use case is listed,
// with its label, and the five facts it sends are mappable variables.
describe('SetDefaultTemplateDialog - stock_ask_salesman', () => {
  it('lists the use case with its label', () => {
    const entry = USE_CASES.find((u) => u.key === 'stock_ask_salesman');
    expect(entry?.label).toBe('Stock Ask - Salesman Notification');
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SetDefaultTemplateDialog useCase="stock_ask_salesman" current={null} open onOpenChange={() => {}} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Stock Ask - Salesman Notification/)).toBeInTheDocument();
  });

  it('offers the ask facts as mappable variables', () => {
    const keys = PARAM_VARIABLES.map((v) => v.key);
    for (const key of ['outcome', 'customer_name', 'product', 'quantity', 'asked_at']) {
      expect(keys).toContain(key);
    }
  });
});
