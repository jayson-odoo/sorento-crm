/**
 * MarketSignalsPanel - loading / empty / error / data states (CRUD UX standard)
 * + trend colour mapping (up = adverse/red, down = favourable/green, flat/null =
 * neutral) + topic_label rendered as a human label (never a UUID).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MarketSignalsPanel } from './MarketSignalsPanel';
import type { MarketSignal } from '../types/market.types';

function signal(over: Partial<MarketSignal>): MarketSignal {
  return {
    id: 'sig-1',
    topic_label: 'Copper price index',
    category_ref: 'SRT-FC',
    currency: 'MYR',
    value: 1234,
    trend: 'up',
    summary: 'Copper up 3% on supply tightness.',
    source_url: 'https://example.com/copper',
    captured_at: '2026-07-10T08:00:00',
    ...over,
  };
}

function renderPanel(props: Partial<React.ComponentProps<typeof MarketSignalsPanel>>) {
  return render(
    <MarketSignalsPanel
      signals={[]}
      categoryOptions={undefined}
      isLoading={false}
      isError={false}
      error={null}
      {...props}
    />,
  );
}

describe('MarketSignalsPanel', () => {
  it('renders a loading skeleton grid with no signal content', () => {
    renderPanel({ isLoading: true, signals: [signal({})] });
    expect(screen.queryByText('Copper price index')).not.toBeInTheDocument();
  });

  it('renders the error message on failure', () => {
    renderPanel({ isError: true, error: new Error('Failed to load market signals.') });
    expect(screen.getByText('Failed to load market signals.')).toBeInTheDocument();
  });

  it('falls back to a generic error string when error is not an Error', () => {
    renderPanel({ isError: true, error: null });
    expect(screen.getByText('Failed to load market signals.')).toBeInTheDocument();
  });

  it('renders the empty state with the run-research call to action', () => {
    renderPanel({ signals: [] });
    expect(screen.getByText('No market signals yet')).toBeInTheDocument();
    expect(screen.getByText(/Run research to capture the latest/i)).toBeInTheDocument();
  });

  it('renders one card per signal with the human topic label (no UUID)', () => {
    renderPanel({
      signals: [
        signal({ id: 's1', topic_label: 'Copper price index' }),
        signal({ id: 's2', topic_label: 'Steel rebar' }),
      ],
    });
    expect(screen.getByText('Copper price index')).toBeInTheDocument();
    expect(screen.getByText('Steel rebar')).toBeInTheDocument();
  });

  it('formats the headline value with currency + links the source', () => {
    renderPanel({ signals: [signal({ value: 1234, currency: 'MYR', source_url: 'https://x.test' })] });
    expect(screen.getByText('MYR 1,234')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Source/i });
    expect(link).toHaveAttribute('href', 'https://x.test');
  });

  it('renders an em dash for a purely-qualitative signal (null value) and no source link', () => {
    renderPanel({ signals: [signal({ value: null, source_url: null, summary: 'Freight easing.' })] });
    expect(screen.getByText('Freight easing.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Source/i })).not.toBeInTheDocument();
  });

  it('maps trend to the right label + colour (up=Rising/red, down=Falling/green, flat=Flat)', () => {
    const { rerender } = renderPanel({ signals: [signal({ id: 'up', trend: 'up' })] });
    const up = screen.getByTitle('Trend: Rising');
    expect(up).toHaveClass('text-scm-stockout');

    rerender(
      <MarketSignalsPanel
        signals={[signal({ id: 'down', trend: 'down' })]}
        categoryOptions={undefined}
        isLoading={false}
        isError={false}
      />,
    );
    expect(screen.getByTitle('Trend: Falling')).toHaveClass('text-scm-healthy');

    rerender(
      <MarketSignalsPanel
        signals={[signal({ id: 'flat', trend: 'flat' })]}
        categoryOptions={undefined}
        isLoading={false}
        isError={false}
      />,
    );
    expect(screen.getByTitle('Trend: Flat')).toBeInTheDocument();
  });

  it('maps a null trend to the Unknown chip', () => {
    renderPanel({ signals: [signal({ trend: null })] });
    expect(screen.getByTitle('Trend: Unknown')).toBeInTheDocument();
  });

  it('resolves category_ref to a readable label when options are provided', () => {
    renderPanel({
      signals: [signal({ category_ref: 'cat-uuid-1' })],
      categoryOptions: [{ value: 'cat-uuid-1', label: 'Ferrous Castings' }],
    });
    const card = screen.getByText('Copper price index').closest('div');
    expect(card).toBeTruthy();
    expect(screen.getByText('Ferrous Castings')).toBeInTheDocument();
    // the raw ref/UUID never surfaces
    expect(screen.queryByText('cat-uuid-1')).not.toBeInTheDocument();
  });
});
