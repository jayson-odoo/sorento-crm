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

vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query',
  () => ({
    useBrandSelectQuery: (...a: unknown[]) => useBrandSelectQuery(...a),
  }),
);

// Deliberately unsorted, and with the same brand repeated once per company - the
// two things the live /brands/select response does.
const CATALOG = [
  { id: 'b1', brand_code: 'mocha', brand_name: 'Mocha', is_active: true },
  { id: 'b2', brand_code: 'CABANA', brand_name: 'Cabana', is_active: true },
  { id: 'b3', brand_code: 'SORENTO', brand_name: 'Sorento', is_active: true },
  { id: 'b4', brand_code: 'sorento', brand_name: 'Sorento', is_active: true },
  { id: 'b5', brand_code: 'ALPINE', brand_name: 'Alpine', is_active: true },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
  return {
    ...result,
    rerender: (next: React.ReactElement) =>
      result.rerender(
        <QueryClientProvider client={client}>{next}</QueryClientProvider>,
      ),
  };
}

/** Opens the editor dialog, then the multiselect menu inside it. */
function openPicker() {
  fireEvent.click(screen.getByLabelText(/edit brands/i));
  fireEvent.click(
    document.querySelector('[data-slot="searchable-multi-select-trigger"]')!,
  );
}

const optionLabels = () =>
  Array.from(document.querySelectorAll('[cmdk-item]')).map(
    (el) => el.textContent?.trim() ?? '',
  );

beforeEach(() => {
  useMemberBrands.mockReset();
  useBrandSelectQuery.mockReset();
  setMutate.mockReset();
  useBrandSelectQuery.mockReturnValue({ data: CATALOG, isLoading: false });
  Element.prototype.scrollIntoView = vi.fn();
  (
    Element.prototype as unknown as { hasPointerCapture: unknown }
  ).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('MemberBrandEditor', () => {
  it('shows "All brands" when the member has no brand tags', () => {
    useMemberBrands.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText(/all brands/i)).toBeInTheDocument();
  });

  it('renders the tagged brands as badges, resolved to their names', () => {
    useMemberBrands.mockReturnValue({
      data: ['mocha', 'cabana'],
      isLoading: false,
    });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText('Mocha')).toBeInTheDocument();
    expect(screen.getByText('Cabana')).toBeInTheDocument();
  });

  it('falls back to the upper-cased code for a tag no brand matches', () => {
    useMemberBrands.mockReturnValue({ data: ['weathermaker'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(screen.getByText('WEATHERMAKER')).toBeInTheDocument();
  });

  it('offers every brand once, sorted A to Z', () => {
    useMemberBrands.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    openPicker();
    // Sorento appears once despite the per-company duplicate rows.
    expect(optionLabels()).toEqual(['Alpine', 'Cabana', 'Mocha', 'Sorento']);
  });

  it('narrows the list from the search box', () => {
    useMemberBrands.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    openPicker();
    fireEvent.change(screen.getByPlaceholderText('Search...'), {
      target: { value: 'sor' },
    });
    expect(optionLabels()).toEqual(['Sorento']);
  });

  it('persists the selected brands as lower-case codes on save', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    openPicker();
    // The catalogue carries "CABANA"; the payload is always lower-case.
    fireEvent.click(screen.getByRole('option', { name: 'Cabana' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save brands$/i }));
    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toEqual(['mocha', 'cabana']);
  });

  it('clears every tag back to "serves all" when the last one is deselected', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    openPicker();
    fireEvent.click(screen.getByRole('option', { name: 'Mocha' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save brands$/i }));
    expect(setMutate.mock.calls[0][0]).toEqual([]);
  });

  it('opens without looping when the query has not answered yet', () => {
    // Both queries undefined: the old inline `= []` defaults handed the
    // draft-reset effect a fresh array every render, so opening the dialog
    // re-entered setDraft until React threw "Maximum update depth exceeded".
    useMemberBrands.mockReturnValue({ data: undefined, isLoading: false });
    useBrandSelectQuery.mockReturnValue({ data: undefined, isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    expect(() =>
      fireEvent.click(screen.getByLabelText(/edit brands/i)),
    ).not.toThrow();
    expect(screen.getByText('Brands served')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Save brands$/i }));
    expect(setMutate.mock.calls[0][0]).toEqual([]);
  });

  it('keeps the draft when a background refetch lands while the dialog is open', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    const { rerender } = renderWithClient(
      <MemberBrandEditor teamId="t1" userId="u1" />,
    );
    openPicker();
    fireEvent.click(screen.getByRole('option', { name: 'Cabana' }));
    // A refetch resolves to a new array while the user is mid-edit.
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    rerender(<MemberBrandEditor teamId="t1" userId="u1" />);
    fireEvent.click(screen.getByRole('button', { name: /^Save brands$/i }));
    expect(setMutate.mock.calls[0][0]).toEqual(['mocha', 'cabana']);
  });

  it('still lets a stale tag be cleared when the catalogue is empty', () => {
    useMemberBrands.mockReturnValue({ data: ['mocha'], isLoading: false });
    useBrandSelectQuery.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberBrandEditor teamId="t1" userId="u1" />);
    openPicker();
    expect(screen.getByText(/no brands configured/i)).toBeInTheDocument();
    // The orphaned tag is still an option, so it can be taken off.
    fireEvent.click(screen.getByRole('option', { name: 'MOCHA' }));
    const save = screen.getByRole('button', { name: /^Save brands$/i });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    expect(setMutate.mock.calls[0][0]).toEqual([]);
  });
});
