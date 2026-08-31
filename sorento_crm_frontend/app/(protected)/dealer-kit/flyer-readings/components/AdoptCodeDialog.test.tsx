/**
 * "This is..." - the one decision an adoption asks for (PLAN-flyer-code-adopt.md,
 * AC-A.10, AC-A.11).
 *
 * `SearchableSelect` is stubbed to the `(query, pageIndex) => Promise<Option[]>`
 * contract it calls `fetchOptions` with, the same convention
 * `SalesOrderFormModal.test.tsx` uses: a search box standing in for the real
 * combobox, and a button per row the stub's `fetchOptions` resolved with. What
 * this file pins is that the dialog wires the picker in SERVER mode (R5 - the
 * whole 10k+ master, never a capped list) and that the suggestion is a
 * default, never the server's opinion.
 *
 * Mocks the SERVICE layer (`flyerReadingService`), not the hook: the real
 * `useAdoptCode` mutation runs through actual react-query, matching
 * `UploadFlyerDialog.test.tsx`'s convention for this same feature.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

type StubOption = { value: string; label: string; description?: string };

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    onOptionChange,
    fetchOptions,
    selectedOption,
    placeholder,
    paginated,
    clearable,
  }: {
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (option: StubOption | null) => void;
    fetchOptions?: (query: string, pageIndex: number) => Promise<StubOption[]>;
    selectedOption?: StubOption;
    placeholder?: string;
    paginated?: boolean;
    clearable?: boolean;
  }) => {
    const [fetched, setFetched] = React.useState<StubOption[]>([]);
    const [query, setQuery] = React.useState('');
    React.useEffect(() => {
      if (!fetchOptions) return;
      let live = true;
      void fetchOptions(query, 0).then((rows) => {
        if (live) setFetched(rows);
      });
      return () => {
        live = false;
      };
    }, [fetchOptions, query]);

    return (
      <div
        data-testid="dk-adopt-picker"
        // What proves this is the fetchOptions (server) mode, not a static
        // options list: a picker with no `fetchOptions` at all could never
        // reach a code outside whatever page it was handed (AC-A.10's R5).
        data-fetch-mode={fetchOptions ? 'server' : 'static'}
        data-paginated={paginated ? 'true' : 'false'}
        data-clearable={clearable ? 'true' : 'false'}
      >
        <input
          aria-label={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span data-testid="dk-adopt-picker-selected">{selectedOption?.label ?? value}</span>
        {fetched.map((o) => (
          <button
            type="button"
            key={o.value}
            onClick={() => {
              onChange(o.value);
              onOptionChange?.(o);
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
    );
  },
}));

const { listPickerProducts } = vi.hoisted(() => ({ listPickerProducts: vi.fn() }));
vi.mock('../../services/productPickerService', () => ({
  PICKER_PAGE_SIZE: 50,
  listPickerProducts: (...args: unknown[]) => listPickerProducts(...args),
}));

const { adoptCode } = vi.hoisted(() => ({ adoptCode: vi.fn() }));
vi.mock('../../services/flyerReadingService', () => ({ adoptCode: (...args: unknown[]) => adoptCode(...args) }));

import type { CodeSuggestion } from '../../services/flyerReadingService';
import { AdoptCodeDialog } from './AdoptCodeDialog';

const SUGGESTION: CodeSuggestion = {
  productId: 'p-9',
  productCode: 'SRTBT1835-16',
  productName: 'Corner Bathtub 1835',
  similarity: 0.94,
};

function renderDialog(
  overrides: Partial<{
    code: string | null;
    pages: number[];
    suggestion: CodeSuggestion | null;
    onOpenChange: (open: boolean) => void;
  }> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onOpenChange = overrides.onOpenChange ?? vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <AdoptCodeDialog
        readingId="r-1"
        promotionId={null}
        open
        onOpenChange={onOpenChange}
        code={overrides.code ?? 'SRTBT1835'}
        pages={overrides.pages ?? [11]}
        suggestion={overrides.suggestion === undefined ? SUGGESTION : overrides.suggestion}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  listPickerProducts.mockResolvedValue([]);
});

describe('AdoptCodeDialog, the title and picker', () => {
  it('names the printed code in its title, and the page it was printed on', () => {
    renderDialog({ code: 'SRTBT1835', pages: [11] });

    expect(screen.getByText('SRTBT1835 is which product?')).toBeInTheDocument();
    expect(screen.getByText(/printed on p\. 11/i)).toBeInTheDocument();
  });

  it('is a server-searched, paginated picker - never a capped list (R5)', async () => {
    renderDialog();

    const picker = await screen.findByTestId('dk-adopt-picker');
    expect(picker).toHaveAttribute('data-fetch-mode', 'server');
    expect(picker).toHaveAttribute('data-paginated', 'true');
    expect(picker).toHaveAttribute('data-clearable', 'true');
    // On mount, with nothing typed.
    await waitFor(() => expect(listPickerProducts).toHaveBeenCalledWith('', 0));
  });

  it('forwards a typed query to the server search', async () => {
    renderDialog();
    await screen.findByTestId('dk-adopt-picker');

    fireEvent.change(screen.getByLabelText('Search by code or name'), {
      target: { value: 'SRTBT' },
    });

    await waitFor(() => expect(listPickerProducts).toHaveBeenCalledWith('SRTBT', 0));
  });
});

describe('AdoptCodeDialog, the suggestion is a default only', () => {
  it('preselects the suggestion, and Confirm reads the code it will adopt', () => {
    renderDialog({ suggestion: SUGGESTION });

    expect(screen.getByTestId('dk-adopt-picker-selected')).toHaveTextContent('SRTBT1835-16');
    expect(screen.getByTestId('dk-fr-adopt-confirm')).toBeEnabled();
    expect(screen.getByTestId('dk-fr-adopt-confirm')).toHaveTextContent(
      'Use SRTBT1835-16 for SRTBT1835',
    );
  });

  it('stays disabled with no suggestion until a product is picked', async () => {
    renderDialog({ suggestion: null });
    await screen.findByTestId('dk-adopt-picker');

    expect(screen.getByTestId('dk-fr-adopt-confirm')).toBeDisabled();

    listPickerProducts.mockResolvedValue([
      { id: 'p-2', code: 'SRTBT2000', name: 'Freestanding Bath' },
    ]);
    fireEvent.change(screen.getByLabelText('Search by code or name'), {
      target: { value: 'SRTBT2000' },
    });

    fireEvent.click(await screen.findByRole('button', { name: 'SRTBT2000' }));

    expect(screen.getByTestId('dk-fr-adopt-confirm')).toBeEnabled();
  });
});

describe('AdoptCodeDialog, success and failure', () => {
  it('keeps the dialog open and shows the extracted message on a refusal', async () => {
    adoptCode.mockRejectedValue(
      new Error('SRTBT1830 on p. 4 is already this product.'),
    );
    const { onOpenChange } = renderDialog({ suggestion: SUGGESTION });

    fireEvent.click(screen.getByTestId('dk-fr-adopt-confirm'));

    await waitFor(() =>
      expect(screen.getByTestId('dk-fr-adopt-error')).toHaveTextContent(
        'SRTBT1830 on p. 4 is already this product.',
      ),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('closes the dialog on success', async () => {
    adoptCode.mockResolvedValue({
      id: 'r-1',
      filename: 'flyer.pdf',
      byteSize: 1,
      pageCount: 1,
      codeCount: 1,
      uploadedAt: '',
      status: 'done',
      errorMessage: null,
      finishedAt: null,
      headings: [],
      codeOverridesChangedAt: '2026-08-31T00:00:00',
      report: {
        matched: [
          {
            code: 'SRTBT1835',
            productId: 'p-9',
            productCode: 'SRTBT1835-16',
            productName: 'Corner Bathtub 1835',
            pages: [11],
            adopted: true,
          },
        ],
        unmatched: [],
        notPromoted: [],
        dimensionCandidates: [],
        duplicates: {},
        promotionId: null,
      },
    });
    const { onOpenChange } = renderDialog({ suggestion: SUGGESTION });

    fireEvent.click(screen.getByTestId('dk-fr-adopt-confirm'));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(adoptCode).toHaveBeenCalledWith('r-1', 'SRTBT1835', 'p-9', null);
  });
});
