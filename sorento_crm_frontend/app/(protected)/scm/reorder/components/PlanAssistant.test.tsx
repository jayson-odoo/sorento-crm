import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PlanAssistant } from './PlanAssistant';

// M6 hooks are react-query-backed; drive them from the test via hoisted spies.
const { hRunChat, hMarketSearch, hCategoryOptions } = vi.hoisted(() => ({
  hRunChat: vi.fn(),
  hMarketSearch: vi.fn(),
  hCategoryOptions: vi.fn(),
}));

vi.mock('../hooks/useExplainer', () => ({
  useRunChat: (...a: unknown[]) => hRunChat(...a),
  useMarketSearch: (...a: unknown[]) => hMarketSearch(...a),
}));
vi.mock('../../hooks/useScmOptions', () => ({
  useCategoryOptions: (...a: unknown[]) => hCategoryOptions(...a),
}));

// jsdom polyfills for the Radix Popover inside SearchableSelect.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function renderWithClient(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  hRunChat.mockReset();
  hMarketSearch.mockReset();
  hCategoryOptions.mockReset();
  hRunChat.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hMarketSearch.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hCategoryOptions.mockReturnValue({ data: [{ value: 'cat-1', label: 'Ceramics' }], isLoading: false });
});

describe('PlanAssistant (M6)', () => {
  it('offers both surfaces and reveals the chat input only when Discuss is opened', () => {
    renderWithClient(<PlanAssistant runId="run-1" />);
    expect(screen.getByRole('button', { name: /discuss this plan/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /search the market/i })).toBeInTheDocument();
    // collapsed by default — no chat input yet
    expect(screen.queryByLabelText('Ask about this plan')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /discuss this plan/i }));
    expect(screen.getByLabelText('Ask about this plan')).toBeInTheDocument();
  });

  it('appends a grounded answer to the transcript and forwards prior history', async () => {
    const mutateAsync = vi
      .fn()
      .mockResolvedValueOnce({ answer: 'The most urgent buy is FT-B.' })
      .mockResolvedValueOnce({ answer: 'The next is FT-03.' });
    hRunChat.mockReturnValue({ mutateAsync, isPending: false });

    renderWithClient(<PlanAssistant runId="run-1" />);
    fireEvent.click(screen.getByRole('button', { name: /discuss this plan/i }));

    fireEvent.change(screen.getByLabelText('Ask about this plan'), {
      target: { value: 'Which buys are most urgent?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(await screen.findByText('The most urgent buy is FT-B.')).toBeInTheDocument();
    // first call forwards an empty history
    expect(mutateAsync).toHaveBeenLastCalledWith({
      question: 'Which buys are most urgent?',
      history: [],
    });

    // a follow-up forwards the prior turn so "the next one" resolves
    fireEvent.change(screen.getByLabelText('Ask about this plan'), {
      target: { value: 'And the next one?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));
    await screen.findByText('The next is FT-03.');
    expect(mutateAsync).toHaveBeenLastCalledWith({
      question: 'And the next one?',
      history: [{ question: 'Which buys are most urgent?', answer: 'The most urgent buy is FT-B.' }],
    });
  });

  it('runs a market search and renders the returned signal', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      signals: [
        {
          id: 's1',
          topic_label: 'colours',
          category_ref: 'cat-1',
          currency: null,
          value: null,
          trend: 'up',
          summary: 'Ice blue is trending in 2026.',
          source_url: 'http://example.com',
          captured_at: '2026-07-17T00:00:00',
        },
      ],
      run: { id: 'r1', status: 'completed', signal_count: 1, error: null },
    });
    hMarketSearch.mockReturnValue({ mutateAsync, isPending: false });

    renderWithClient(<PlanAssistant runId="run-1" />);
    fireEvent.click(screen.getByRole('button', { name: /search the market/i }));

    fireEvent.change(screen.getByLabelText('Market search query'), {
      target: { value: 'trending bathroom colours 2026' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    expect(await screen.findByText('Ice blue is trending in 2026.')).toBeInTheDocument();
    expect(screen.getByText('Market signal')).toBeInTheDocument();
    expect(mutateAsync).toHaveBeenCalledWith({
      query: 'trending bathroom colours 2026',
      categoryRef: null,
    });
  });

  it('surfaces the honest failure note when a search fails (e.g. no key)', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      signals: [],
      run: { id: 'r1', status: 'failed', signal_count: 0, error: 'Anthropic web-search not configured' },
    });
    hMarketSearch.mockReturnValue({ mutateAsync, isPending: false });

    renderWithClient(<PlanAssistant runId="run-1" />);
    fireEvent.click(screen.getByRole('button', { name: /search the market/i }));
    fireEvent.change(screen.getByLabelText('Market search query'), {
      target: { value: 'anything' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    await waitFor(() =>
      expect(screen.getByText(/Anthropic web-search not configured/i)).toBeInTheDocument(),
    );
  });
});
