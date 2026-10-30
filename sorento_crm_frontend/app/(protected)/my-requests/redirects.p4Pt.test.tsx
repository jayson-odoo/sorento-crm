/**
 * PORTAL-P4-REQUESTS S7 (deep links): Price Tag Request under /my-requests sends the visitor to the STAFF pages
 * (Dealer Kit > Room Designer > Price Tag Requests). Either `redirect()` or `router.replace()` counts.
 *   /my-requests?type=price_tag_request     -> /dealer-kit/price-tag-requests
 *   /my-requests/price_tag_request           -> the same list (the old list route)
 *   /my-requests/price_tag_request/new       -> /dealer-kit/price-tag-requests/new
 *   /my-requests/price_tag_request/<id>      -> /dealer-kit/price-tag-requests/<id>
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
    salesperson: { portalKinds: ['price_tag_request'], portalSlug: 'S1' },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="embedded-landing" /> }));
vi.mock('@/app/(auth)/portal/components/PriceTagRequestForm', () => ({
  PriceTagRequestForm: () => <div data-testid="embedded-form" />,
  default: () => <div data-testid="embedded-form" />,
}));
vi.mock('@/app/(auth)/portal/components/PriceTagRequestList', () => ({ PriceTagRequestList: () => <div data-testid="embedded-form" /> }));

import MyRequestsPage from './page';
import PtList from './price_tag_request/page';
import PtNew from './price_tag_request/new/page';
import PtDetail from './price_tag_request/[id]/page';

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

describe('Price Tag Request deep links', () => {
  it('/my-requests?type=price_tag_request lands on the staff table', async () => {
    query.type = 'price_tag_request';
    await mount(<MyRequestsPage {...({ searchParams: Promise.resolve({ type: 'price_tag_request' }) } as object)} />);
    await waitFor(() => expect(landed).toContain('/dealer-kit/price-tag-requests'));
  });
  it('/my-requests/price_tag_request lands on the staff table', async () => {
    await mount(<PtList />);
    await waitFor(() => expect(landed).toContain('/dealer-kit/price-tag-requests'));
  });
  it('/my-requests/price_tag_request/new lands on the staff request page in create mode', async () => {
    await mount(<PtNew />);
    await waitFor(() => expect(landed).toContain('/dealer-kit/price-tag-requests/new'));
  });
  it('/my-requests/price_tag_request/<id> lands on the staff request page', async () => {
    await mount(<PtDetail params={Promise.resolve({ id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain('/dealer-kit/price-tag-requests/abc-123'));
  });
  it('never renders the embedded portal form', async () => {
    const { queryByTestId } = render(
      <Suspense fallback={null}>
        <PtList />
        <PtNew />
        <PtDetail params={Promise.resolve({ id: 'abc-123' })} />
      </Suspense>,
    );
    await act(async () => {});
    expect(queryByTestId('embedded-form')).toBeNull();
  });
});
