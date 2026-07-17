import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RunPlanningModal } from './RunPlanningModal';

const { hWarehouses } = vi.hoisted(() => ({ hWarehouses: vi.fn() }));
vi.mock('../../hooks/useScmOptions', () => ({
  useWarehouseOptions: (...a: unknown[]) => hWarehouses(...a),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
// jsdom lacks these Radix/pointer APIs
if (!(Element.prototype as unknown as { hasPointerCapture?: unknown }).hasPointerCapture) {
  (Element.prototype as unknown as { hasPointerCapture: () => boolean }).hasPointerCapture = () => false;
  (Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
}

beforeEach(() => {
  hWarehouses.mockReset();
  hWarehouses.mockReturnValue({
    data: [{ value: 'WH-1', label: 'Warehouse 1' }],
    isLoading: false,
    isError: false,
  });
});

describe('RunPlanningModal — market factor toggle (M7)', () => {
  it('renders the market toggle off by default with the qty-neutral explainer', () => {
    render(
      <RunPlanningModal open onOpenChange={() => {}} onSubmit={vi.fn()} isSubmitting={false} />,
    );
    const toggle = screen.getByRole('button', { name: /factor in market signals/i });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText(/order quantities are unchanged/i)).toBeInTheDocument();
  });

  it('flips aria-pressed when clicked', () => {
    render(
      <RunPlanningModal open onOpenChange={() => {}} onSubmit={vi.fn()} isSubmitting={false} />,
    );
    const toggle = screen.getByRole('button', { name: /factor in market signals/i });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('blocks submit with no warehouse, then includes include_market once one is picked', () => {
    const onSubmit = vi.fn();
    render(
      <RunPlanningModal open onOpenChange={() => {}} onSubmit={onSubmit} isSubmitting={false} />,
    );

    // no warehouse → validation error, no submit
    fireEvent.click(screen.getByRole('button', { name: /^run planning$/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/select at least one warehouse/i)).toBeInTheDocument();

    // pick a warehouse via the multi-select
    fireEvent.click(screen.getByRole('button', { name: /select warehouses to plan for/i }));
    fireEvent.click(screen.getByText('Warehouse 1'));

    // turn market on, then submit
    fireEvent.click(screen.getByRole('button', { name: /factor in market signals/i }));
    fireEvent.click(screen.getByRole('button', { name: /^run planning$/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ warehouse_codes: ['WH-1'], include_market: true }),
    );
  });
});
