/** PROJECT-STAGE-ACTIONS: the header Cancel on a new sample request opened from a project. */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../components/SampleRequestForm', () => ({ __esModule: true, default: () => null }));

// The layout shell needs the app's settings provider; only the page's own wiring is under test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import NewSampleRequestPage from './page';

async function renderPage(searchParams: { project_id?: string }) {
  render(await NewSampleRequestPage({ searchParams: Promise.resolve(searchParams) }));
}

describe('New sample request header Cancel', () => {
  it('from a project goes back to its Samples Request tab', async () => {
    await renderPage({ project_id: 'p1' });
    expect(screen.getByRole('link', { name: 'Cancel' }).getAttribute('href')).toBe(
      '/project-sales/p1?tab=sample-requests',
    );
  });

  it('from the list goes back to the list', async () => {
    await renderPage({});
    expect(screen.getByRole('link', { name: 'Cancel' }).getAttribute('href')).toBe(
      '/project-sales/sample-requests',
    );
  });
});
