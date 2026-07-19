import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IdeationEmbed } from './IdeationEmbed';

vi.mock('@/hooks/useIdeationEmbedSession', () => ({
  useIdeationEmbedSession: vi.fn(),
}));

import { useIdeationEmbedSession } from '@/hooks/useIdeationEmbedSession';

const mockHook = useIdeationEmbedSession as unknown as ReturnType<typeof vi.fn>;

describe('IdeationEmbed', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the loading state while the session is pending', () => {
    mockHook.mockReturnValue({
      isPending: true,
      isError: false,
      data: undefined,
      isFetching: true,
      refetch: vi.fn(),
    });
    render(<IdeationEmbed title="Ideas board" />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('shows an error state with a working Retry that refetches', () => {
    const refetch = vi.fn();
    mockHook.mockReturnValue({
      isPending: false,
      isError: true,
      data: undefined,
      isFetching: false,
      refetch,
    });
    render(<IdeationEmbed title="Ideas board" />);
    expect(screen.getByText(/couldn.t open the ideas workspace/i)).toBeInTheDocument();
    // Never renders a blank iframe on error (AC-44).
    expect(document.querySelector('iframe')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('renders the iframe with the token in the src on success', () => {
    mockHook.mockReturnValue({
      isPending: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
      data: {
        iframe_url: 'https://ideation.example.invalid/embed/ideas',
        token: 'stub-embed-token',
        expires_at: '2026-07-19T00:00:00.000Z',
      },
    });
    render(<IdeationEmbed title="Ideas board" />);
    const iframe = document.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe(
      'https://ideation.example.invalid/embed/ideas?token=stub-embed-token',
    );
    expect(iframe?.getAttribute('title')).toBe('Ideas board');
  });

  it('does not render the raw url or token as visible text (AC-41)', () => {
    mockHook.mockReturnValue({
      isPending: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
      data: {
        iframe_url: 'https://ideation.example.invalid/embed/ideas/idea-123',
        token: 'secret-token',
        expires_at: '2026-07-19T00:00:00.000Z',
      },
    });
    render(<IdeationEmbed ideaId="idea-123" title="Idea detail" />);
    expect(screen.queryByText('idea-123')).toBeNull();
    expect(screen.queryByText(/secret-token/)).toBeNull();
  });
});
