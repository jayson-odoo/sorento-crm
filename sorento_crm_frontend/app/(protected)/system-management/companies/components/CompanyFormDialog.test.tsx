/**
 * CompanyFormDialog - the "AutoCount sales orders connected" switch.
 *
 * `so_feed_live` gates the chatbot's stock answer: off withholds Outstanding
 * for that company's rows (PLAN company-so-feed-flag, AC-8). These tests pin
 * the control and its payload so it cannot go missing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const hooks = vi.hoisted(() => ({
  createAsync: vi.fn().mockResolvedValue({}),
  updateAsync: vi.fn().mockResolvedValue({}),
  useCompany: vi.fn(),
}));

vi.mock('../hooks/useCompanies', () => ({
  useCreateCompany: () => ({ mutateAsync: hooks.createAsync, isPending: false }),
  useUpdateCompany: () => ({ mutateAsync: hooks.updateAsync, isPending: false }),
  useCompany: (...a: unknown[]) => hooks.useCompany(...a),
}));

import CompanyFormDialog from './CompanyFormDialog';

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  hooks.useCompany.mockReturnValue({ data: undefined, isLoading: false });
});

function renderCreate() {
  return render(<CompanyFormDialog open onOpenChange={vi.fn()} />);
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText(/Company Name/i), { target: { value: 'Mocha' } });
  fireEvent.change(screen.getByLabelText(/Company Code/i), { target: { value: 'MCH' } });
}

describe('CompanyFormDialog - AutoCount sales orders connected switch', () => {
  it('offers the switch, on by default on create', () => {
    renderCreate();
    const sw = screen.getByRole('switch', { name: /AutoCount sales orders connected/i });
    expect(sw).toBeInTheDocument();
    expect(sw).toBeChecked();
  });

  it('sends so_feed_live true on create when left untouched', async () => {
    renderCreate();
    fillRequired();
    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    expect(hooks.createAsync.mock.calls[0][0]).toMatchObject({ so_feed_live: true });
  });

  it('sends so_feed_live false once switched off', async () => {
    renderCreate();
    fillRequired();
    fireEvent.click(screen.getByRole('switch', { name: /AutoCount sales orders connected/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    expect(hooks.createAsync.mock.calls[0][0]).toMatchObject({ so_feed_live: false });
  });

  it('reflects an off row when editing, and sends it back unchanged', async () => {
    hooks.useCompany.mockReturnValue({
      data: {
        id: 'co-mocha',
        name: 'Mocha',
        code: 'MCH',
        is_active: true,
        so_feed_live: false,
        autocount_ref: null,
        logo_url: null,
      },
      isLoading: false,
    });
    render(<CompanyFormDialog open onOpenChange={vi.fn()} companyId="co-mocha" />);

    const sw = screen.getByRole('switch', { name: /AutoCount sales orders connected/i });
    expect(sw).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: /^Update$/ }));

    await waitFor(() => expect(hooks.updateAsync).toHaveBeenCalledTimes(1));
    expect(hooks.updateAsync.mock.calls[0][0]).toMatchObject({
      data: expect.objectContaining({ so_feed_live: false }),
    });
  });

  it('places the switch above Active', () => {
    renderCreate();
    const labels = screen.getAllByText(/AutoCount sales orders connected|^Active$/);
    expect(labels[0].textContent).toMatch(/AutoCount sales orders connected/);
    expect(labels[1].textContent).toBe('Active');
  });
});
