/**
 * MarketSignalTiles - the three roll-up tiles: active topics, signals captured,
 * last-captured time. Counts render with thousands separators; a null
 * last-captured degrades to an em dash (never a fabricated date).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MarketSignalTiles } from './MarketSignalTiles';

describe('MarketSignalTiles', () => {
  it('renders the three tile labels', () => {
    render(<MarketSignalTiles activeTopicCount={0} signalCount={0} lastCapturedAt={null} />);
    expect(screen.getByText('Active topics')).toBeInTheDocument();
    expect(screen.getByText('Signals captured')).toBeInTheDocument();
    expect(screen.getByText('Last captured')).toBeInTheDocument();
  });

  it('formats counts with thousands separators', () => {
    render(<MarketSignalTiles activeTopicCount={12} signalCount={1234} lastCapturedAt={null} />);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });

  it('renders an em dash for last-captured when nothing has been captured', () => {
    render(<MarketSignalTiles activeTopicCount={3} signalCount={0} lastCapturedAt={null} />);
    // signals captured is 0, last captured is the em dash
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('renders a formatted last-captured timestamp when present', () => {
    render(
      <MarketSignalTiles
        activeTopicCount={3}
        signalCount={9}
        lastCapturedAt="2026-07-10T08:00:00"
      />,
    );
    // formatDateTimeInMalaysia renders a non-empty, non-em-dash string
    expect(screen.queryByText('-')).not.toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
  });
});
