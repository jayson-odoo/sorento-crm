/**
 * P7 - the publish dialog, and the one way past a hard stop.
 *
 * What is pinned here is the shape of the override: it cannot be used without a reason, the
 * reason reaches the caller in the body the backend reads, and a refusal from the backend
 * (no sales-manager grant) is shown in the dialog rather than swallowed. The ordinary publish
 * still sends no body at all, which is what keeps an unblocked order's behaviour unchanged.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SalesOrderPublishDialog } from './SalesOrderPublishDialog';
import type {
  ProjectSalesOrderFinding,
  SalesOrderPublishResult,
} from '../../_shared/types/projectSalesOrder.types';

const HARD: ProjectSalesOrderFinding = {
  id: 'find-1',
  severity: 'hard',
  code: 'schedule_short',
  detail: 'The schedule places 90 where the PO orders 100.',
  line_no: 1,
};

const HARD_2: ProjectSalesOrderFinding = {
  id: 'find-2',
  severity: 'hard',
  code: 'total_mismatch',
  detail: 'The lines add up to 39,285.00 where the PO prints 40,000.00.',
  line_no: null,
};

const PUBLISHED: SalesOrderPublishResult = {
  status: 'published',
  provisional_ref: 'PSO-000123',
  import_file_url: '/api/v1/project-sales/sales-orders/pso-1/import-file',
  can_export: true,
};

function renderDialog({
  blocking = [] as ProjectSalesOrderFinding[],
  onPublish = vi.fn().mockResolvedValue(PUBLISHED),
} = {}) {
  render(
    <SalesOrderPublishDialog
      reference="PSO-000123"
      blocking={blocking}
      unacknowledgedWarnings={[]}
      onDone={vi.fn()}
      onPublish={onPublish}
      onDownloadImportFile={vi.fn()}
      submitting={false}
    />,
  );
  return onPublish;
}

describe('SalesOrderPublishDialog', () => {
  it('publishes an unblocked order with no body at all', async () => {
    const onPublish = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(onPublish).toHaveBeenCalledTimes(1));
    expect(onPublish).toHaveBeenCalledWith(undefined);
    expect(await screen.findByText('Published')).toBeInTheDocument();
  });

  it('lists what blocks the publish and offers the override, off by default', () => {
    renderDialog({ blocking: [HARD, HARD_2] });

    expect(screen.getByText('Publishing is refused')).toBeInTheDocument();
    expect(screen.getByText(/Line 1: The schedule places 90/)).toBeInTheDocument();
    expect(screen.getByText('Publish despite 2 blocking findings')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    // Nothing to type into until the decision is made.
    expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish anyway' })).toBeDisabled();
  });

  it('keeps Publish anyway disabled until a reason is typed', () => {
    renderDialog({ blocking: [HARD] });

    fireEvent.click(screen.getByRole('checkbox'));
    const button = screen.getByRole('button', { name: 'Publish anyway' });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'ok' } });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Manager signed it off in the room.' },
    });
    expect(button).toBeEnabled();
  });

  it('sends the override and the trimmed reason, and says how many were waved through', async () => {
    const onPublish = vi
      .fn()
      .mockResolvedValue({ ...PUBLISHED, acknowledged_findings: 2 });
    renderDialog({ blocking: [HARD, HARD_2], onPublish });

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: '  Manager signed it off in the room.  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Publish anyway' }));

    await waitFor(() =>
      expect(onPublish).toHaveBeenCalledWith({
        acknowledge_blocking: true,
        reason: 'Manager signed it off in the room.',
      }),
    );
    expect(
      await screen.findByText(
        '2 blocking findings published anyway, with the reason recorded on each.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the backend refusal in place when the user holds no override', async () => {
    const onPublish = vi
      .fn()
      .mockRejectedValue(
        new Error(
          'This is a hard stop. Only a sales manager can acknowledge it, and the reason stays on the sales order.',
        ),
      );
    renderDialog({ blocking: [HARD], onPublish });

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Manager signed it off in the room.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Publish anyway' }));

    expect(await screen.findByText(/Only a sales manager can acknowledge it/)).toBeInTheDocument();
    // Still on the refusal, with the findings and the control in reach.
    expect(screen.getByText('Publishing is refused')).toBeInTheDocument();
    expect(screen.queryByText('Published')).not.toBeInTheDocument();
  });
});
