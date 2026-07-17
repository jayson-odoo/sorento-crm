import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const useDeadStockDays = vi.fn();
const mutateAsync = vi.fn();
const useSaveDeadStockDays = vi.fn();
vi.mock('../hooks/useScmDashboard', () => ({
  useDeadStockDays: () => useDeadStockDays(),
  useSaveDeadStockDays: () => useSaveDeadStockDays(),
}));

import { DeadStockSettings } from './DeadStockSettings';

beforeEach(() => {
  useDeadStockDays.mockReturnValue({ data: 180, isLoading: false });
  mutateAsync.mockReset().mockResolvedValue(90);
  useSaveDeadStockDays.mockReturnValue({ mutateAsync, isPending: false });
});

async function openPopover() {
  fireEvent.click(screen.getByRole('button', { name: /Settings/i }));
  await waitFor(() => screen.getByLabelText('Dead-stock threshold in days'));
}

describe('DeadStockSettings', () => {
  it('shows the current value and helper note', async () => {
    render(<DeadStockSettings />);
    await openPopover();
    expect(screen.getByText(/no movement beyond this are flagged Dead/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Dead-stock threshold in days')).toHaveValue(180);
  });

  it('disables Save until the value changes', async () => {
    render(<DeadStockSettings />);
    await openPopover();
    const save = screen.getByRole('button', { name: /^Save$/i });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Dead-stock threshold in days'), { target: { value: '90' } });
    expect(save).toBeEnabled();
  });

  it('rejects out-of-range values', async () => {
    render(<DeadStockSettings />);
    await openPopover();
    fireEvent.change(screen.getByLabelText('Dead-stock threshold in days'), { target: { value: '0' } });
    expect(screen.getByText(/between 1 and 3650/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Save$/i })).toBeDisabled();
  });

  it('saves a valid new value', async () => {
    render(<DeadStockSettings />);
    await openPopover();
    fireEvent.change(screen.getByLabelText('Dead-stock threshold in days'), { target: { value: '90' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith(90));
  });
});
