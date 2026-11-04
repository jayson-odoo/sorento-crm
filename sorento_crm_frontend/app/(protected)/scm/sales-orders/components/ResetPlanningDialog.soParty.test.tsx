/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35): the orders Reset planning lists name their
 * customer and project too (the shared `CUSTOMER / project` line).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

import { ResetPlanningDialog } from './ResetPlanningDialog';

describe('ResetPlanningDialog lists each order with customer / project', () => {
  it('prints SO number then CUSTOMER / project per order', () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ResetPlanningDialog
          open
          onOpenChange={vi.fn()}
          onDone={vi.fn()}
          orders={[
            { id: 'a', so_number: 'SO1', customer_name: 'ACME', project_label: 'TAMAN JAYA' },
            { id: 'b', so_number: 'SO2', customer_name: 'BETA', project_label: null },
          ]}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText('SO1')).toBeInTheDocument();
    expect(screen.getByText('ACME / TAMAN JAYA')).toBeInTheDocument();
    expect(screen.getByText('SO2')).toBeInTheDocument();
    expect(screen.getByText('BETA / -')).toBeInTheDocument();
  });
});
