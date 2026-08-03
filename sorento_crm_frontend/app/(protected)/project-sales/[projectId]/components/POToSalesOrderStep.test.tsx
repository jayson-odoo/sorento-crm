/**
 * The step after a PO arrives.
 *
 * The client uploaded their purchase order and asked "so how do I convert to SO?".
 * These assert that the question is answered where they asked it, and that the answer
 * is never a dead control: when the next step is blocked, it says by what.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

// jsdom polyfills Radix's Popover (the info icon) needs.
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

import {
  POToSalesOrderStep,
  poToSalesOrderStep,
} from './POToSalesOrderStep';
import type { ProjectPurchaseOrder } from '../../_shared/types/project.types';

const PO = {
  id: 'po-1',
  project_id: 'p-1',
  po_number: 'HQ/26/01/121',
  po_source: 'contractor_direct',
  line_count: 51,
  line_total: '1810640.62',
  model_mismatch_count: 0,
  price_mismatch_count: 0,
} as unknown as ProjectPurchaseOrder;

function renderStep(poConfirmed: boolean, scheduleConfirmed: boolean) {
  return render(
    <POToSalesOrderStep
      projectId="p-1"
      purchaseOrder={PO}
      readiness={{ poConfirmed, scheduleConfirmed }}
    />,
  );
}

describe('the next step after a PO', () => {
  it('asks for the PO to be checked before anything else', () => {
    renderStep(false, false);

    expect(screen.getByTestId('po-next-step')).toHaveAttribute('data-state', 'confirm-po');
    expect(
      screen.getByText(/Confirm this PO before it becomes a sales order/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/project-sales/p-1?tab=pos&po=po-1',
    );
  });

  it('names the delivery schedule as what is missing, rather than disabling silently', () => {
    renderStep(true, false);

    const step = screen.getByTestId('po-next-step');
    expect(step).toHaveAttribute('data-state', 'need-schedule');
    expect(
      screen.getByText(/Add the delivery schedule to build the sales orders/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/project-sales/p-1?tab=schedules&po=po-1',
    );
  });

  it('keeps the reason off the page until it is asked for', async () => {
    renderStep(true, false);

    // The REASON is the useful half (quantities alone cannot be scheduled), but it is a
    // lesson learned once, so it is not printed beside every PO.
    expect(screen.queryByText(/when each phase needs it/i)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Why this is the next step/i }));

    await waitFor(() =>
      expect(screen.getByText(/when each phase needs it/i)).toBeInTheDocument(),
    );
  });

  it('offers to build once the PO and its schedule are both agreed', () => {
    renderStep(true, true);

    expect(screen.getByTestId('po-next-step')).toHaveAttribute('data-state', 'ready');
    expect(screen.getByRole('link', { name: /Build the sales orders/i })).toHaveAttribute(
      'href',
      // Carries the PO through, so the next screen does not ask them to pick the one
      // they are standing on.
      '/project-sales/p-1?tab=sales-orders&build=po-1',
    );
  });

  it('never leaves the person without a next action', () => {
    for (const [po, schedule] of [
      [false, false],
      [true, false],
      [true, true],
      [false, true],
    ] as const) {
      const step = poToSalesOrderStep({ poConfirmed: po, scheduleConfirmed: schedule });
      expect(step.actionLabel.length).toBeGreaterThan(0);
      expect(step.body.length).toBeGreaterThan(0);
    }
  });

  it('treats a schedule confirmed before the PO as still needing the PO', () => {
    // Order matters: a schedule can be uploaded first, but nothing is ordered until
    // somebody has agreed what the PO actually says.
    renderStep(false, true);

    expect(screen.getByTestId('po-next-step')).toHaveAttribute('data-state', 'confirm-po');
  });
});
