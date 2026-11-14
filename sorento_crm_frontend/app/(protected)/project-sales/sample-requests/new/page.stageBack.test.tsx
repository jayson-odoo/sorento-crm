/** PROJECT-STAGE-ACTIONS: the header Cancel on a new sample request opened from a project. */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// SAMPLE-REQUEST-V2: the header is the client SampleRequestPageHeader; no `?from=` here, so the
// `project_id` alone must still lead back to the project.
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/project-sales/sample-requests/new',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock('../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('../components/SampleRequestForm', () => ({ __esModule: true, default: () => null }));

// The layout shell needs the app's settings provider; only the page's own wiring is under test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import NewSampleRequestPage from './page';

async function renderPage(searchParams: { project_id?: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      {await NewSampleRequestPage({ searchParams: Promise.resolve(searchParams) })}
    </QueryClientProvider>,
  );
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

  it('from a project, the trail leads back to the project, never to a list the user may not open', async () => {
    await renderPage({ project_id: 'p1' });
    const crumb = screen.getByRole('link', { name: 'Project' });
    expect(crumb.getAttribute('href')).toBe('/project-sales/p1?tab=sample-requests');
    expect(screen.getByRole('link', { name: 'Projects' }).getAttribute('href')).toBe('/project-sales/pipeline');
  });
});
