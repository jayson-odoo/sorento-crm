/**
 * SPEC-VALUE-ICONS R2 / R5: the table draws whatever the caller hands it after a row's value,
 * and hides it while that row is in edit. The table stays free of Dealer Kit types: the
 * adornment is a render prop.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

import { SpecTable } from './SpecTable';
import { buildSpecTableRows } from './specTableModel';
import {
  MOCK_EXCEPTIONS,
  MOCK_PROVENANCE,
  MOCK_REGISTRY,
  MOCK_VALUES,
} from './__mocks__/specTable.fixtures';
import type { SpecTableRow } from './types';

function renderTable(valueAdornment?: (row: SpecTableRow) => React.ReactNode) {
  const rows = buildSpecTableRows({
    values: MOCK_VALUES,
    provenance: MOCK_PROVENANCE,
    registry: MOCK_REGISTRY,
    exceptions: MOCK_EXCEPTIONS,
  });
  const callbacks = {
    onSetValue: vi.fn().mockResolvedValue(undefined),
    onTombstone: vi.fn().mockResolvedValue(undefined),
    onRevert: vi.fn().mockResolvedValue(undefined),
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpecTable
        rows={rows}
        registry={MOCK_REGISTRY}
        callbacks={callbacks}
        valueAdornment={valueAdornment}
      />
    </QueryClientProvider>,
  );
}

describe('SpecTable valueAdornment', () => {
  it('draws the adornment on the rows it returns one for, and nothing elsewhere', async () => {
    renderTable((row) =>
      row.specKey === 'material' ? (
        <span data-testid="adorn-material">icons</span>
      ) : null,
    );
    expect(await screen.findByTestId('adorn-material')).toBeTruthy();
    expect(screen.queryAllByText('icons')).toHaveLength(1);
  });

  it('sits in the same cell as the value, after it', async () => {
    renderTable((row) =>
      row.specKey === 'material' ? (
        <span data-testid="adorn-material">icons</span>
      ) : null,
    );
    const adorn = await screen.findByTestId('adorn-material');
    const value = document.querySelector(
      '[data-spec-value="material"]',
    ) as HTMLElement;
    expect(value).toBeTruthy();
    expect(adorn.closest('td')).toBe(value.closest('td'));
    expect(
      value.compareDocumentPosition(adorn) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('is hidden while the row is in edit', async () => {
    renderTable((row) =>
      row.specKey === 'material' ? (
        <span data-testid="adorn-material">icons</span>
      ) : null,
    );
    await screen.findByTestId('adorn-material');
    fireEvent.click(
      document.querySelector('[data-spec-value="material"]') as HTMLElement,
    );
    expect(screen.queryByTestId('adorn-material')).toBeNull();
  });

  it('leaves the value cell as it was when no adornment is given', async () => {
    renderTable();
    await screen.findAllByText(/Stainless Steel/i);
    const value = document.querySelector(
      '[data-spec-value="material"]',
    ) as HTMLElement;
    expect(value.className).toContain('w-full');
  });
});
