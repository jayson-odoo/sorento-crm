/**
 * PROJECT-REGISTER-V2 J1: /project-sales/new opens for projects.projects.edit OR
 * projects.registrations.submit; a user with neither is denied.
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
vi.mock('../_shared/components/ProjectForm', () => ({
  ProjectForm: () => <div>REGISTER-FORM</div>,
}));

import RegisterProjectPage from './page';

beforeEach(() => {
  granted = new Set();
});

describe('J1 the register page gate', () => {
  it('opens for projects.projects.edit', () => {
    granted = new Set(['projects.projects.edit']);
    render(<RegisterProjectPage />);
    expect(screen.getByText('REGISTER-FORM')).toBeInTheDocument();
  });

  it('opens for a submit-only salesperson', () => {
    granted = new Set(['projects.registrations.submit']);
    render(<RegisterProjectPage />);
    expect(screen.getByText('REGISTER-FORM')).toBeInTheDocument();
    expect(screen.queryByText('ACCESS-DENIED')).toBeNull();
  });

  it('is denied for a user with neither', () => {
    granted = new Set(['projects.projects.view']);
    render(<RegisterProjectPage />);
    expect(screen.getByText('ACCESS-DENIED')).toBeInTheDocument();
    expect(screen.queryByText('REGISTER-FORM')).toBeNull();
  });
});
