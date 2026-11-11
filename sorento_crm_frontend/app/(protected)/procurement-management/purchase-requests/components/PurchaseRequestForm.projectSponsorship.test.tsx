/**
 * PROJECT-STAGE-ACTIONS: a sponsorship form opened from a project is the salesperson's form
 * (the portal SubmissionForm) for staff too, never the free-text staff form, and it starts from
 * the project.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const scope = vi.hoisted(() => ({ limited: false }));
vi.mock('@/hooks/useRequestScope', () => ({ useRequestScope: () => ({ limited: scope.limited }) }));

const projectRef = vi.hoisted(() => ({
  current: {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Example',
    customer_id: 'cust-1',
    customer_name: 'Acme Developers',
    customer_attn: 'Bob',
    customer_phone: '012-3456789',
    address: '1 Example Road',
    estimated_sales_value: '250000.00',
    owner_name: 'Ann Sales',
    owner_contact_id: 'c-ann',
  } as Record<string, unknown>,
}));
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: projectRef.current, isLoading: false }),
  SPONSORSHIPS_KEY: 'project-sponsorships',
}));

const seen = vi.hoisted(() => ({ props: [] as Record<string, unknown>[], me: [] as unknown[] }));
vi.mock('@/app/(auth)/portal/components/SubmissionForm', async () => {
  const { useSubmissionClient } = await import('@/app/(auth)/portal/lib/submission-client');
  return {
    SubmissionForm: (props: Record<string, unknown>) => {
      const client = useSubmissionClient();
      seen.props.push(props);
      seen.me.push(client.fetchMe);
      return <div data-testid="salesperson-form" />;
    },
  };
});
vi.mock('@/components/common/MyRequestPortalForm', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    seen.props.push(props);
    return <div data-testid="salesperson-form" />;
  },
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/procurement-management/sponsorship-forms/new',
}));

import PurchaseRequestForm from './PurchaseRequestForm';

function renderForm(props: Record<string, unknown>) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm defaultRequestType="sponsorship_form" {...props} />
    </QueryClientProvider>,
  );
}

const SEED = {
  project_id: 'p1',
  project_title: 'Menara Example',
  customer_name: 'Acme Developers',
  customer_id: 'cust-1',
  pic: 'Bob 012-3456789',
  delivery_address: '1 Example Road',
  total_project_value: '250000.00',
};

beforeEach(() => {
  seen.props = [];
  seen.me = [];
  scope.limited = false;
});

describe('Sponsorship form from a project', () => {
  it('staff get the salesperson form, not the free-text staff form', () => {
    renderForm({ defaultProjectId: 'p1' });
    expect(screen.getByTestId('salesperson-form')).toBeTruthy();
    expect(screen.queryByText('Registered project (optional)')).toBeNull();
  });

  it('staff start from the project: project, title, customer, PIC, address and value', () => {
    renderForm({ defaultProjectId: 'p1' });
    expect(seen.props.at(-1)).toMatchObject({
      kind: 'sponsorship_form',
      initialValues: { fields: SEED, labels: { project_code: 'PRJ-000001' } },
    });
  });

  it('staff write it on behalf of the project salesperson', async () => {
    renderForm({ defaultProjectId: 'p1' });
    const fetchMe = seen.me.at(-1) as () => Promise<{ contact_id: string; name: string }>;
    await expect(fetchMe()).resolves.toMatchObject({ contact_id: 'c-ann', name: 'Ann Sales' });
  });

  it('a salesperson gets the same form with the same start', () => {
    scope.limited = true;
    renderForm({ defaultProjectId: 'p1' });
    expect(seen.props.at(-1)).toMatchObject({
      kind: 'sponsorship_form',
      initialValues: { fields: SEED },
    });
  });
});
