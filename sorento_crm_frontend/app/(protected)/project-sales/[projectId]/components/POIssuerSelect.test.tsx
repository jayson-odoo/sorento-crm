/**
 * PO-UPLOAD-MATCHING crew pass 2, item 1: "Issued by" searches parties on the SERVER.
 *
 * A party list can run to thousands of rows; a select fed by one preloaded page cannot reach
 * the 1,977th party. Typing a name or code asks the parties list service (`query`), and the
 * options are what the server returned. The current issuer shows by its name even when it
 * is not among the fetched options (`issuerName`, from the version's
 * `purchase_order.issuing_party_name`; prop name per the coordinator's contract note).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type PartyParams = { query?: string; page?: number; limit?: number };

function party(n: number) {
  return { id: `pty${n}`, name: `ZZT Party ${n}`, party_type: 'main_contractor' };
}

const listParties = vi.fn(async (params: PartyParams = {}) => {
  const query = (params.query ?? '').trim();
  const all = query
    ? [party(1977)].filter((p) => p.name.includes(query))
    : Array.from({ length: params.limit ?? 50 }, (_, i) => party(i + 1));
  return { data: all, total: query ? all.length : 2000, page: params.page ?? 1, limit: params.limit ?? 50 };
});

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/projectService')>();
  return { ...actual, listParties: (params: PartyParams) => listParties(params) };
});

import { POIssuerSelect } from './POIssuerSelect';

function renderSelect(props: Partial<React.ComponentProps<typeof POIssuerSelect>> = {}) {
  const onChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <label htmlFor="issuer">Issued by</label>
      <POIssuerSelect id="issuer" value={null} onChange={onChange} {...(props as object)} />
    </QueryClientProvider>,
  );
  return { onChange };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIssuerSelect server search', () => {
  it('finds a party no preloaded page holds by asking the server, and chooses it', async () => {
    const user = userEvent.setup();
    const { onChange } = renderSelect();

    await user.click(await screen.findByRole('combobox', { name: /Issued by/i }));
    await user.type(await screen.findByPlaceholderText(/Search/i), '1977');

    const option = await screen.findByRole('option', { name: /ZZT Party 1977/ }, { timeout: 3000 });
    expect(listParties).toHaveBeenCalledWith(expect.objectContaining({ query: '1977' }));
    fireEvent.click(option);

    expect(onChange).toHaveBeenCalledWith('pty1977');
  });

  it('offers what the server returned for the query, not a client-side filter of one page', async () => {
    const user = userEvent.setup();
    renderSelect();

    await user.click(await screen.findByRole('combobox', { name: /Issued by/i }));
    await user.type(await screen.findByPlaceholderText(/Search/i), 'Party 1977');

    await screen.findByRole('option', { name: /ZZT Party 1977/ }, { timeout: 3000 });
    await waitFor(() =>
      expect(listParties).toHaveBeenCalledWith(expect.objectContaining({ query: 'Party 1977' })),
    );
    expect(screen.queryByRole('option', { name: /^ZZT Party 1$/ })).toBeNull();
  });

  it('shows the current issuer by name even when it is not among the fetched options', async () => {
    renderSelect({
      value: 'pty-far-away',
      issuerName: 'ZZT Far Away Contractor',
    } as Partial<React.ComponentProps<typeof POIssuerSelect>>);

    const select = await screen.findByRole('combobox', { name: /Issued by/i });
    await waitFor(() => expect(select).toHaveTextContent('ZZT Far Away Contractor'));
  });
});
