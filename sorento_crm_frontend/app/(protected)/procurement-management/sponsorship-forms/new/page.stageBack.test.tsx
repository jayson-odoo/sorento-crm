/**
 * PROJECT-STAGE-ACTIONS: the new sponsorship form opened from a project's Sponsorship stage
 * button keeps that project, and Cancel and save go back to the project's Sponsorship Form tab.
 * Opened from the admin list it behaves as before.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const formProps = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('../../purchase-requests/components/PurchaseRequestForm', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    formProps.current = props;
    return null;
  },
}));

// The layout shell needs the app's settings provider; only the page's own wiring is under test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import NewSponsorshipFormPage from './page';

async function renderPage(searchParams: { project_id?: string }) {
  render(await NewSponsorshipFormPage({ searchParams: Promise.resolve(searchParams) }));
}

describe('New sponsorship form', () => {
  it('from a project: Cancel and save return to its Sponsorship Form tab', async () => {
    await renderPage({ project_id: 'p1' });
    expect(screen.getByRole('link', { name: 'Cancel' }).getAttribute('href')).toBe(
      '/project-sales/p1?tab=sponsorships',
    );
    expect(formProps.current).toMatchObject({
      defaultRequestType: 'sponsorship_form',
      defaultProjectId: 'p1',
      successRedirectUrl: '/project-sales/p1?tab=sponsorships',
    });
  });

  it('from the list: Cancel and save return to the list', async () => {
    await renderPage({});
    expect(screen.getByRole('link', { name: 'Cancel' }).getAttribute('href')).toBe(
      '/procurement-management/sponsorship-forms',
    );
    expect(formProps.current.successRedirectUrl).toBe('/procurement-management/sponsorship-forms');
  });

  it('from a project, the trail leads back to the project, never to a list the user may not open', async () => {
    await renderPage({ project_id: 'p1' });
    const crumb = screen.getByRole('link', { name: 'Project' });
    expect(crumb.getAttribute('href')).toBe('/project-sales/p1?tab=sponsorships');
    expect(screen.getByRole('link', { name: 'Projects' }).getAttribute('href')).toBe('/project-sales/pipeline');
  });
});
