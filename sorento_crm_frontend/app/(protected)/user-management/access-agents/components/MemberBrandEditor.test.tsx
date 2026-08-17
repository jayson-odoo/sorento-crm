import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import MemberBrandEditor from './MemberBrandEditor';

const useMemberBrands = vi.fn();
const useBrandSelectQuery = vi.fn();
const setMutate = vi.fn();

vi.mock('../hooks/useMemberBrands', () => ({
  useMemberBrands: (...a: unknown[]) => useMemberBrands(...a),
  useSetMemberBrands: () => ({ mutate: setMutate, isPending: false }),
}));

vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: (...a: unknown[]) => useBrandSelectQuery(...a),
}));

const CATALOG = [
  { id: 'b1', brand_code: 'mocha', brand_name: 'Mocha', is_active: true },
  { id: 'b2', brand_code: 'CABANA', brand_name: 'Cabana', is_active: true },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  useMemberBrands.mockReset();
  useBrandSelectQuery.mockReset();
  setMutate.mockReset();
  useBrandSelectQuery.mockReturnValue({ data: CATALOG, isLoading: false });
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('MemberBrandEditor', () => {
  it('shows "All brands" when the member has no brand tags', () => {
    useMemberBrands.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText(/all brands/i)).toBeInTheDocument();
  });

  it('renders the tagged brands as badges, resolved to their names', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha', 'cabana'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText('Mocha')).toBeInTheDocument();
    expect(screen.getByText('Cabana')).toBeInTheDocument();
  });

  it('falls back to the upper-cased code for a tag no brand matches', () => {
    useMemberBrands.mockReturnValue({ data: ['sorento'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText('SORENTO')).toBeInTheDocument();
  });

  it('persists the selected brands as lower-case codes on save', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    fireEvent.click(screen.getByLabelText(/edit brands/i));
    fireEvent.click(screen.getByLabelText('Cabana'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(setMutate).toHaveBeenCalledTimes(1);
    // The catalogue carries "CABANA"; the payload is always lower-case.
    expect(setMutate.mock.calls[0][0]).toEqual(['mocha', 'cabana']);
  });

  it('clears every tag back to "serves all" when all boxes are unticked', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    fireEvent.click(screen.getByLabelText(/edit brands/i));
    fireEvent.click(screen.getByLabelText('Mocha'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(setMutate.mock.calls[0][0]).toEqual([]);
  });

  it('says where to add brands when none are configured', () => {
    useMemberBrands.mockReturnValue({ data: [], isLoading: false });
    useBrandSelectQuery.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    fireEvent.click(screen.getByLabelText(/edit brands/i));
    expect(screen.getByText(/no brands configured/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled();
  });
});
