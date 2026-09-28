/**
 * Chatbot stock ask v2 S6, AC-SA606: the portal shows "Customer asks" only to a contact
 * linked to a sales agent (the list's 403 hides it).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const listCustomerAsks = vi.fn();
vi.mock('../lib/customer-asks-service', async () => {
  const actual = await vi.importActual<typeof import('../lib/customer-asks-service')>(
    '../lib/customer-asks-service',
  );
  return { ...actual, listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a) };
});

import { CustomerAsksLink } from './CustomerAsksLink';
import { NotASalesAgentError } from '../lib/customer-asks-service';

beforeEach(() => vi.clearAllMocks());

describe('CustomerAsksLink', () => {
  it('links a sales agent to the page, with the open count', async () => {
    listCustomerAsks.mockResolvedValue({ data: [], pagination: { total: 3, page: 1, limit: 1 } });
    render(<CustomerAsksLink slug="ah-lim" />);
    const link = await screen.findByRole('link', { name: /Customer asks/ });
    expect(link).toHaveAttribute('href', '/portal/c/ah-lim/customer_asks');
    expect(listCustomerAsks).toHaveBeenCalledWith(expect.objectContaining({ state: 'open', limit: 1 }));
    expect(link).toHaveTextContent('3');
  });

  it('shows nothing to a contact who is no sales agent', async () => {
    listCustomerAsks.mockRejectedValue(new NotASalesAgentError());
    const { container } = render(<CustomerAsksLink slug="ah-lim" />);
    await waitFor(() => expect(listCustomerAsks).toHaveBeenCalled());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});
