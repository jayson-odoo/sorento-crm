import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { NoToolAsksCard } from './NoToolAsksCard';
import type { NoToolAsk } from '../services/aiUsageService';

const useNoToolAsks = vi.fn();
vi.mock('../hooks/useAIUsage', () => ({
  useNoToolAsks: () => useNoToolAsks(),
}));

afterEach(() => {
  cleanup();
  useNoToolAsks.mockReset();
});

const ROWS: NoToolAsk[] = [
  {
    turn_id: 't1',
    ask: 'approve purchase order PO-1001',
    area: 'purchasing',
    who: 'Aina',
    channel: 'panel',
    asked_at: '2026-11-05T03:00:00Z',
  },
  {
    turn_id: 't2',
    ask: 'change my delivery address',
    area: null,
    who: null,
    channel: 'whatsapp',
    asked_at: '2026-11-04T03:00:00Z',
  },
];

describe('NoToolAsksCard', () => {
  it('lists each ask with its area, user, channel and date', () => {
    useNoToolAsks.mockReturnValue({
      data: ROWS,
      isLoading: false,
      isError: false,
    });
    render(<NoToolAsksCard />);
    expect(screen.getByText('approve purchase order PO-1001')).toBeTruthy();
    expect(screen.getByText('purchasing')).toBeTruthy();
    expect(screen.getByText('Aina')).toBeTruthy();
    expect(screen.getByText('Side panel')).toBeTruthy();
    expect(screen.getByText('WhatsApp')).toBeTruthy();
    expect(screen.getByText('change my delivery address')).toBeTruthy();
    // No turn id is shown as text.
    expect(screen.queryByText('t1')).toBeNull();
  });

  it('puts Date right after Ask, so it stays on screen at 375px', () => {
    useNoToolAsks.mockReturnValue({
      data: ROWS,
      isLoading: false,
      isError: false,
    });
    render(<NoToolAsksCard />);
    const headers = screen
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers.slice(0, 2)).toEqual(['Ask', 'Date']);
  });

  it('shows an empty state with no button', () => {
    useNoToolAsks.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    render(<NoToolAsksCard />);
    expect(screen.getByText('No asks without a tool')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows the error message', () => {
    useNoToolAsks.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
    });
    render(<NoToolAsksCard />);
    expect(screen.getByText('boom')).toBeTruthy();
  });
});
