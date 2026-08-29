/**
 * S3-03 - the key parity every wired entity has to hold.
 *
 * The pager reads the page out of the cache by rebuilding the LIST's React Query
 * key from the detail URL. If a list's key and the key its own URL produces are
 * not identical, nothing breaks loudly: the pager just misses, refetches, and can
 * page a wider set than the user was looking at. So each entity states, here, the
 * list state it can be in, the URL its row click emits for that state, and the two
 * keys are hashed and compared the way React Query compares them.
 *
 * Add a row per entity as the sweep wires it.
 */
import { describe, it, expect } from 'vitest';
import { hashKey, type QueryKey } from '@tanstack/react-query';

import { buildDetailSearch, parseDetailSearch } from '@/lib/listNavQuery';
import {
  usersListFilters,
  usersListQueryKey,
} from '@/app/(protected)/user-management/users/lib/listQuery';
import {
  ordersListQueryKey,
  ordersListParamsFromUrl,
} from '@/app/(protected)/order-management/orders/hooks/useOrders';
import {
  productsListQueryKey,
  productsListParamsFromUrl,
} from '@/app/(protected)/master-data-management/products/lib/listQuery';
import {
  complaintsListQueryKey,
  complaintsListParamsFromUrl,
} from '@/app/(protected)/complaint-management/complaints/hooks/useComplaints';
import {
  customersListQueryKey,
  customersListParamsFromUrl,
} from '@/app/(protected)/order-management/customers/hooks/useCustomers';

/** One list state: the key the list builds, and the URL its row click emits. */
interface ParityCase {
  name: string;
  listKey: QueryKey;
  url: string;
  /** The key the pager builds from that URL. */
  pagerKey: (search: URLSearchParams) => QueryKey;
}

const ADVANCED = {
  op: 'and' as const,
  children: [{ field: 'debtor_name', operator: 'contains', value: 'acme' }],
};

function usersCase(
  name: string,
  state: {
    pageIndex: number;
    pageSize: number;
    sorting: { id: string; desc: boolean }[];
    searchQuery: string;
    role: string | null;
    status: string | null;
    trashed: string;
  },
): ParityCase {
  const filters = usersListFilters(state);
  const listParams = {
    pageIndex: state.pageIndex,
    pageSize: state.pageSize,
    sorting: state.sorting,
    searchQuery: state.searchQuery,
    filters,
  };
  return {
    name,
    listKey: usersListQueryKey(listParams),
    url: buildDetailSearch(listParams, filters),
    pagerKey: (search) => usersListQueryKey(parseDetailSearch(search)),
  };
}

const CASES: ParityCase[] = [
  usersCase('users, defaults', {
    pageIndex: 0,
    pageSize: 10,
    sorting: [{ id: 'createdAt', desc: true }],
    searchQuery: '',
    role: null,
    status: 'all',
    trashed: 'exclude',
  }),
  usersCase('users, searched and filtered on page 3', {
    pageIndex: 2,
    pageSize: 25,
    sorting: [{ id: 'name', desc: false }],
    searchQuery: 'ada',
    role: 'role-1',
    status: 'active',
    trashed: 'only',
  }),

  (() => {
    // Orders, quick filters only.
    const listParams = {
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: 'DO-99',
      order_status_id: 'status-7',
      has_order_lines: 'yes' as const,
      advancedFilter: undefined,
    };
    return {
      name: 'orders, quick filters',
      listKey: ordersListQueryKey(listParams),
      url: buildDetailSearch(listParams, {
        order_status_id: listParams.order_status_id,
        has_order_lines: listParams.has_order_lines,
        advFilter: undefined,
      }),
      pagerKey: (search: URLSearchParams) =>
        ordersListQueryKey(ordersListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),

  (() => {
    // Orders, advanced filter: the case that silently pages the wrong set when
    // the filter is not carried in the URL.
    const listParams = {
      pageIndex: 0,
      pageSize: 50,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      order_status_id: undefined,
      has_order_lines: 'all' as const,
      advancedFilter: ADVANCED,
    };
    return {
      name: 'orders, advanced filter',
      listKey: ordersListQueryKey(listParams),
      url: buildDetailSearch(listParams, {
        advFilter: encodeURIComponent(JSON.stringify(ADVANCED)),
      }),
      pagerKey: (search: URLSearchParams) =>
        ordersListQueryKey(ordersListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),

  (() => {
    // Products, every filter the list can hold at once.
    const listParams = {
      pageIndex: 4,
      pageSize: 50,
      sorting: [{ id: 'product_name', desc: false }],
      searchQuery: 'lamp',
      category_id: 'cat-1',
      brand_id: 'brand-1',
      status: 'active',
      variant_filter: 'base' as const,
      discontinued_batch_id: undefined,
      discontinued_brand_ids: undefined,
      advancedFilter: undefined,
    };
    return {
      name: 'products, category + brand + status + variant',
      listKey: productsListQueryKey(listParams),
      url: buildDetailSearch(listParams, {
        category_id: listParams.category_id,
        brand_id: listParams.brand_id,
        status: listParams.status,
        variant_filter: listParams.variant_filter,
      }),
      pagerKey: (search: URLSearchParams) =>
        productsListQueryKey(productsListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),

  (() => {
    // Products reached from a "products discontinued" notification: the brand
    // param IS the recipient's slice of the batch.
    const listParams = {
      pageIndex: 0,
      pageSize: 50,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      category_id: undefined,
      brand_id: 'brand-a,brand-b',
      status: 'all',
      variant_filter: 'all' as const,
      discontinued_batch_id: 'batch-9',
      discontinued_brand_ids: 'brand-a,brand-b',
      advancedFilter: undefined,
    };
    return {
      name: 'products, discontinued deep link',
      listKey: productsListQueryKey(listParams),
      url: buildDetailSearch(listParams, {
        brand_id: listParams.brand_id,
        discontinued_batch_id: listParams.discontinued_batch_id,
      }),
      pagerKey: (search: URLSearchParams) =>
        productsListQueryKey(productsListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),
  (() => {
    // Complaints: the multi-select filters travel as comma-joined ids.
    const listParams = {
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'complaint_date', desc: true }],
      searchQuery: 'leak',
      assigned_to: 'user-3',
      status: 'submitted',
      root_cause_ids: ['rc-1', 'rc-2'],
      resolution_ids: undefined,
    };
    return {
      name: 'complaints, assignee + status + root causes',
      listKey: complaintsListQueryKey(listParams),
      url: buildDetailSearch(listParams, {
        assigned_to: listParams.assigned_to,
        status: listParams.status,
        root_cause_ids: listParams.root_cause_ids.join(','),
      }),
      pagerKey: (search: URLSearchParams) =>
        complaintsListQueryKey(complaintsListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),
  (() => {
    const listParams = {
      pageIndex: 2,
      pageSize: 50,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: 'acme',
      status: 'active',
    };
    return {
      name: 'customers, status filter',
      listKey: customersListQueryKey(listParams),
      url: buildDetailSearch(listParams, { status: listParams.status }),
      pagerKey: (search: URLSearchParams) =>
        customersListQueryKey(customersListParamsFromUrl(parseDetailSearch(search))),
    };
  })(),
];

describe('list key parity: the pager rebuilds the key the list used', () => {
  for (const testCase of CASES) {
    it(`S3-03: ${testCase.name}`, () => {
      const rebuilt = testCase.pagerKey(new URLSearchParams(testCase.url));
      expect(hashKey(rebuilt)).toBe(hashKey(testCase.listKey));
    });
  }
});
