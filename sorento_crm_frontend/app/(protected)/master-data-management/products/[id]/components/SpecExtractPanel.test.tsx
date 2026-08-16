/**
 * SpecExtractPanel - the prompt box that replaced the flyer card (Journey B, AC-B.1,
 * AC-B.7, AC-B.15's neighbour states).
 *
 * The SERVICE is mocked, not the hook: `useSpecExtraction` is the real hook under
 * test-by-proxy here, so every state transition (idle -> reading -> proposals / zero /
 * degraded / error -> applying -> applied) comes from the real state machine reacting
 * to a mocked `extractSpecProposals` / `applySpecProposals`, the same pattern
 * `useProductSpecTable.test.tsx` uses for its own service.
 *
 * `DataGrid` (inside the real, un-mocked `SpecProposalReview`) calls
 * `useListingColumnPreferences`, which never answers under jsdom - mocked here too,
 * before the import that pulls `SpecProposalReview` in transitively.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock(
  '@/app/(protected)/master-data-management/product-specifications/services/productSpecService',
  () => ({
    extractSpecProposals: vi.fn(),
    applySpecProposals: vi.fn(),
  }),
);

import { toast } from 'sonner';
import {
  applySpecProposals,
  extractSpecProposals,
} from '@/app/(protected)/master-data-management/product-specifications/services/productSpecService';
import SpecExtractPanel from './SpecExtractPanel';

const mockExtract = extractSpecProposals as unknown as ReturnType<typeof vi.fn>;
const mockApply = applySpecProposals as unknown as ReturnType<typeof vi.fn>;

const PROPOSALS = [
  {
    spec_key: 'seat_material',
    label: 'Seat cover material',
    data_type: 'text',
    value: 'pp',
    unit: null,
    evidence: '*PP Seat Cover',
    kind: 'new' as const,
    stored_value: null,
    stored_unit: null,
    stored_source: null,
  },
  {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'text',
    value: 'matt_black',
    unit: null,
    evidence: 'Matt Black finish',
    kind: 'conflict' as const,
    stored_value: 'chrome',
    stored_unit: null,
    stored_source: 'human',
  },
];

function renderPanel(canEdit = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpecExtractPanel productId="p-1" productCode="SRT-WC-1001" canEdit={canEdit} />
    </QueryClientProvider>,
  );
}

/** A promise the test controls the settlement of, to assert a pending state. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('hidden without master_data.products.edit', () => {
  it('renders nothing when canEdit is false', () => {
    // The panel is gated on the `canEdit` prop the parent computes from
    // `usePermissions` (master_data.products.edit); this component owns no
    // permission check of its own, so the prop IS the gate under test.
    const { container } = renderPanel(false);
    expect(container.querySelector('[data-spec-extract-panel]')).toBeNull();
  });
});

describe('idle', () => {
  it('disables the button on empty text', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: 'Read specs from this' })).toBeDisabled();
  });

  it('enables the button once text is typed', () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Washdown with rimless' },
    });
    expect(screen.getByRole('button', { name: 'Read specs from this' })).toBeEnabled();
  });
});

describe('reading', () => {
  it('locks the textarea and busies the button while the extract call is pending', async () => {
    const pending = deferred<never>();
    mockExtract.mockReturnValue(pending.promise);
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Washdown with rimless' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Reading…' })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Text to read specifications from')).toBeDisabled();
  });
});

describe('proposals', () => {
  it('renders the review with Apply reflecting the seeded non-conflict selection', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 2,
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Washdown with rimless, matt black finish' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));

    // One new, one conflict - conflict starts unticked, so Apply 1.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Apply 1' })).toBeInTheDocument(),
    );
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByText('Conflicts with your value Chrome')).toBeInTheDocument();
  });
});

describe('zero proposals ("nothing new")', () => {
  it('shows the empty state with the unchanged count', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: [],
      unchanged: 5,
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Nothing new here' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));

    await waitFor(() =>
      expect(screen.getByText('Nothing new in this text')).toBeInTheDocument(),
    );
    expect(
      screen.getByText('5 values it states are already stored.'),
    ).toBeInTheDocument();
  });
});

describe('degraded (no model reachable)', () => {
  it('shows the "read by the rules only" line', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'deterministic',
      model: null,
      proposals: PROPOSALS,
      unchanged: 0,
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Washdown with rimless' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));

    await waitFor(() =>
      expect(
        screen.getByText('Read by the rules only - no model was reachable.'),
      ).toBeInTheDocument(),
    );
  });
});

describe('error', () => {
  it('shows an Alert with the message and keeps the pasted text', async () => {
    mockExtract.mockRejectedValue(new Error('Could not read this text. Try again in a moment.'));
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'fail this please' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));

    await waitFor(() =>
      expect(
        screen.getByText('Could not read this text. Try again in a moment.'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Text to read specifications from')).toHaveValue(
      'fail this please',
    );
  });
});

describe('applying then applied', () => {
  it('busies on apply, then toasts, clears the text and resets the panel', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    const pendingApply = deferred<{ product_code: string; rows_written: number; spec_keys: string[] }>();
    mockApply.mockReturnValue(pendingApply.promise);
    renderPanel();

    fireEvent.change(screen.getByLabelText('Text to read specifications from'), {
      target: { value: 'Washdown with rimless, matt black finish' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Read specs from this' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Apply 1' })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Apply 1' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Applying…' })).toBeInTheDocument(),
    );

    pendingApply.resolve({
      product_code: 'SRT-WC-1001',
      rows_written: 1,
      spec_keys: ['seat_material'],
    });

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    // Reset: the applied state clears the review and the pasted text goes with it -
    // it was never persisted, so nothing survives an accepted apply either.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Apply/ })).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Text to read specifications from')).toHaveValue('');
  });
});
