/**
 * PORTAL-P4-REQUESTS S5 (deep links): New Product Application under /my-requests sends the visitor to the STAFF page.
 * Either `redirect()` or `router.replace()` counts; what is asserted is where it lands.
 *   /my-requests?type=new_product_application      -> staff list
 *   /my-requests/new_product_application/new       -> staff /new
 *   /my-requests/new_product_application/<id>      -> staff detail
 */
import React, { Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';

const landed: string[] = [];
const query = { type: '' };
class Redirected extends Error {}
vi.mock('next/navigation', () => ({
  redirect: (to: string) => {
    landed.push(to);
    throw new Redirected(to);
  },
  permanentRedirect: (to: string) => {
    landed.push(to);
    throw new Redirected(to);
  },
  notFound: () => {
    throw new Error('notFound');
  },
  useRouter: () => ({
    replace: (to: string) => landed.push(to),
    push: (to: string) => landed.push(to),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(query.type ? `type=${query.type}` : ''),
  usePathname: () => '/my-requests',
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: { portalKinds: ['new_product_application'], portalSlug: 'S1' },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="embedded-landing" /> }));
vi.mock('@/app/(auth)/portal/components/NewProductApplicationForm', () => ({ default: () => <div data-testid="embedded-form" /> }));

import MyRequestsPage from './page';
import NpaNew from './new_product_application/new/page';
import NpaDetail from './new_product_application/[id]/page';

async function mount(node: React.ReactElement) {
  try {
    await act(async () => {
      render(<Suspense fallback={null}>{node}</Suspense>);
    });
  } catch (e) {
    if (!(e instanceof Redirected)) throw e;
  }
}

beforeEach(() => {
  landed.length = 0;
  query.type = '';
});

describe('New Product Application deep links', () => {
  it('/my-requests?type=new_product_application lands on the staff list', async () => {
    query.type = 'new_product_application';
    await mount(<MyRequestsPage {...({ searchParams: Promise.resolve({ type: 'new_product_application' }) } as object)} />);
    await waitFor(() => expect(landed).toContain('/procurement-management/new-product-applications'));
  });
  it('/my-requests/new_product_application/new lands on the staff /new', async () => {
    await mount(<NpaNew />);
    await waitFor(() => expect(landed).toContain('/procurement-management/new-product-applications/new'));
  });
  it('/my-requests/new_product_application/<id> lands on the staff detail', async () => {
    await mount(<NpaDetail params={Promise.resolve({ id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain('/procurement-management/new-product-applications/abc-123'));
  });
  it('never renders the embedded portal form', async () => {
    const { queryByTestId } = render(
      <Suspense fallback={null}>
        <NpaNew />
        <NpaDetail params={Promise.resolve({ id: 'abc-123' })} />
      </Suspense>,
    );
    await act(async () => {});
    expect(queryByTestId('embedded-form')).toBeNull();
  });
});
