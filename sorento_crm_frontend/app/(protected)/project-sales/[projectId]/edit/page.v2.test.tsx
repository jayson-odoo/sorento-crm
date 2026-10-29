/**
 * PROJECT-REGISTER-V2 J1b: the edit page opens for projects.projects.edit OR
 * projects.registrations.submit (the server then lets a submit-only user edit only their own
 * draft or rejected registration). A user with neither is denied.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me' } }, status: 'authenticated' }),
}));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => false }));
vi.mock('@/app/components/common/AccessDenied', () => ({
  default: () => <div>ACCESS-DENIED</div>,
}));
vi.mock('@/components/common/screen-loader', () => ({ ScreenLoader: () => <div>LOADING</div> }));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock('@/components/common/BackToList', () => ({ default: () => <span>back</span> }));
vi.mock('./components/EditProjectClient', () => ({
  EditProjectClient: () => <div>EDIT-FORM</div>,
}));

import EditProjectPage from './page';

async function renderPage() {
  const ui = await EditProjectPage({ params: Promise.resolve({ projectId: 'p1' }) });
  return render(ui);
}

beforeEach(() => {
  granted = new Set();
});

describe('J1b the edit page gate', () => {
  it('opens for projects.projects.edit', async () => {
    granted = new Set(['projects.projects.edit']);
    await renderPage();
    expect(screen.getByText('EDIT-FORM')).toBeInTheDocument();
  });

  it('opens for a submit-only salesperson', async () => {
    granted = new Set(['projects.registrations.submit']);
    await renderPage();
    expect(screen.getByText('EDIT-FORM')).toBeInTheDocument();
    expect(screen.queryByText('ACCESS-DENIED')).toBeNull();
  });

  it('is denied for a user with neither', async () => {
    granted = new Set(['projects.projects.view']);
    await renderPage();
    expect(screen.getByText('ACCESS-DENIED')).toBeInTheDocument();
    expect(screen.queryByText('EDIT-FORM')).toBeNull();
  });
});
