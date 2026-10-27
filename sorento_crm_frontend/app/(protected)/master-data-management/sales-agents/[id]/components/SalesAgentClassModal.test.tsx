import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  createSalesAgentClass: vi.fn(),
  updateSalesAgentClass: vi.fn(),
  getSalesAgentClasses: vi.fn(),
}));
vi.mock('../../services/salesAgentService', () => service);
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SalesAgentClassModal, { buildClassPayload } from './SalesAgentClassModal';

const ROW = {
  id: 'r1',
  sales_agent_id: 'a1',
  demand_class: 'project' as const,
  class_label: 'Project team',
  from_month: '2026-01',
  to_month: null,
};

function renderModal(row: typeof ROW | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesAgentClassModal agentId="a1" open onOpenChange={vi.fn()} row={row} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.createSalesAgentClass.mockResolvedValue(ROW);
  service.updateSalesAgentClass.mockResolvedValue(ROW);
});

describe('buildClassPayload', () => {
  it('sends null for empty months', () => {
    expect(buildClassPayload({ demandClass: 'other', fromMonth: '', toMonth: '' })).toEqual({
      demand_class: 'other',
      from_month: null,
      to_month: null,
    });
  });
  it('keeps months', () => {
    expect(buildClassPayload({ demandClass: 'retail', fromMonth: '2026-01', toMonth: '2026-06' })).toEqual({
      demand_class: 'retail',
      from_month: '2026-01',
      to_month: '2026-06',
    });
  });
});

describe('SalesAgentClassModal', () => {
  it('saves an edit as a PATCH with the cleared From month as null', async () => {
    renderModal(ROW);
    fireEvent.change(screen.getByLabelText('From month'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(service.updateSalesAgentClass).toHaveBeenCalledWith('r1', {
        demand_class: 'project',
        from_month: null,
        to_month: null,
      }),
    );
  });
});
