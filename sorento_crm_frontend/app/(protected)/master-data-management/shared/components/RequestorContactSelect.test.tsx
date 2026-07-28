import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { RequestorContactSelect } from './RequestorContactSelect';

const getRequestorSelectOptionsMock = vi.fn();
vi.mock('../services/requestorSelectService', () => ({
  getRequestorSelectOptions: (...args: unknown[]) => getRequestorSelectOptionsMock(...args),
}));

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-select-trigger"]')!);
const optionLabels = () =>
  [...document.querySelectorAll('[role="option"]')].map((o) => o.textContent?.trim());

beforeEach(() => {
  getRequestorSelectOptionsMock.mockReset();
});

describe('RequestorContactSelect', () => {
  it('renders the saved contact NAME even when it is not in the fetched page (saved-but-ineligible)', async () => {
    // The endpoint no longer returns the saved contact (lost eligibility since
    // the row was submitted) - only unrelated eligible contacts come back.
    getRequestorSelectOptionsMock.mockResolvedValue({
      items: [{ id: 'contact-other', name: 'Someone Else' }],
      has_more: false,
    });

    render(
      <RequestorContactSelect
        value="contact-darren"
        onChange={vi.fn()}
        submitterContactId="contact-submitter"
        savedContactId="contact-darren"
        savedContactName="Darren Lee"
      />,
    );

    // Trigger label resolves to the saved contact's name, never a UUID.
    expect(screen.getByText('Darren Lee')).toBeInTheDocument();
    expect(screen.queryByText('contact-darren')).toBeNull();
  });

  it('falls back to a generic label when the saved contact has no name yet', () => {
    render(
      <RequestorContactSelect
        value="contact-darren"
        onChange={vi.fn()}
        savedContactId="contact-darren"
        savedContactName={null}
      />,
    );
    expect(screen.getByText('Selected contact')).toBeInTheDocument();
  });

  it('includes both the submitter id and the saved id in include_ids on fetch', async () => {
    getRequestorSelectOptionsMock.mockResolvedValue({ items: [], has_more: false });
    render(
      <RequestorContactSelect
        value=""
        onChange={vi.fn()}
        submitterContactId="contact-submitter"
        savedContactId="contact-darren"
        savedContactName="Darren Lee"
      />,
    );
    openMenu();

    await waitFor(() => expect(getRequestorSelectOptionsMock).toHaveBeenCalled());
    const [params] = getRequestorSelectOptionsMock.mock.calls[0];
    expect(params.includeIds).toEqual(['contact-submitter', 'contact-darren']);
  });

  it('shows a loading state while fetching options', async () => {
    let resolveFetch: (v: { items: unknown[]; has_more: boolean }) => void = () => {};
    getRequestorSelectOptionsMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    render(<RequestorContactSelect value="" onChange={vi.fn()} />);
    openMenu();

    expect(await screen.findByText(/searching/i)).toBeInTheDocument();
    resolveFetch({ items: [{ id: 'c1', name: 'Eric Ng' }], has_more: false });
    await waitFor(() => expect(screen.getByText('Eric Ng')).toBeInTheDocument());
  });

  it('shows the empty message on error / no eligible requestors', async () => {
    getRequestorSelectOptionsMock.mockRejectedValue(new Error('boom'));
    render(<RequestorContactSelect value="" onChange={vi.fn()} />);
    openMenu();

    await waitFor(() =>
      expect(screen.getByText('No eligible requestors found.')).toBeInTheDocument(),
    );
  });

  it('renders eligible contacts from the endpoint (data state) and never renders raw UUIDs', async () => {
    getRequestorSelectOptionsMock.mockResolvedValue({
      items: [
        { id: '11111111-1111-1111-1111-111111111111', name: 'Eric Ng' },
        { id: '22222222-2222-2222-2222-222222222222', name: 'Priya Sundar' },
      ],
      has_more: false,
    });
    render(<RequestorContactSelect value="" onChange={vi.fn()} />);
    openMenu();

    await waitFor(() => expect(optionLabels()).toEqual(['Eric Ng', 'Priya Sundar']));
    expect(screen.queryByText(/^[0-9a-f]{8}-/)).toBeNull();
  });

  it('calls onChange with the picked contact id', async () => {
    getRequestorSelectOptionsMock.mockResolvedValue({
      items: [{ id: 'contact-eric', name: 'Eric Ng' }],
      has_more: false,
    });
    const onChange = vi.fn();
    render(<RequestorContactSelect value="" onChange={onChange} />);
    openMenu();

    await waitFor(() => screen.getByText('Eric Ng'));
    fireEvent.click(screen.getByText('Eric Ng'));
    expect(onChange).toHaveBeenCalledWith('contact-eric');
  });
});
