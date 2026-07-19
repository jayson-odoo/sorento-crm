import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// Stub the heavy shell + the embed host so the page tests stay unit-level
// (no SettingsProvider / react-query needed) and just assert wiring.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/toolbar', () => ({
  Toolbar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolbarActions: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolbarHeading: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolbarTitle: ({ children }: { children: React.ReactNode }) => <h1>{children}</h1>,
}));
vi.mock('@/components/ideas/IdeationEmbed', () => ({
  IdeationEmbed: ({ ideaId, title }: { ideaId?: string; title: string }) => (
    <div data-testid="ideation-embed" data-idea-id={ideaId ?? ''} data-title={title} />
  ),
}));

import IdeasBoardPage from './page';
import IdeaDetailPage from './[id]/page';

describe('Ideas board page', () => {
  it('renders the board embed with no idea id', () => {
    render(IdeasBoardPage());
    const embed = screen.getByTestId('ideation-embed');
    expect(embed).toBeInTheDocument();
    expect(embed.getAttribute('data-idea-id')).toBe('');
    expect(embed.getAttribute('data-title')).toBe('Ideas board');
    expect(screen.getByRole('heading', { name: 'Ideas' })).toBeInTheDocument();
  });
});

describe('Idea detail page', () => {
  it('passes the opaque route id to the detail embed without rendering it as text', async () => {
    const ui = await IdeaDetailPage({ params: Promise.resolve({ id: 'idea-abc' }) });
    render(ui);
    const embed = screen.getByTestId('ideation-embed');
    expect(embed.getAttribute('data-idea-id')).toBe('idea-abc');
    expect(embed.getAttribute('data-title')).toBe('Idea detail');
    // The UUID/id is plumbing, never visible UI text (AC-41 / D-8).
    expect(screen.queryByText('idea-abc')).toBeNull();
  });
});
