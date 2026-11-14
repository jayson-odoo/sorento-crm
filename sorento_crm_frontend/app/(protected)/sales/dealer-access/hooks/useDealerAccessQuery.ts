import { useCallback } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  getAccounts,
  getCustomers,
  getPeople,
  type DealerAccessAccount,
  type DealerAccessPeopleParams,
  type DealerAccessRow,
} from '@/services/dealerAccessService';

export const DEALER_ACCESS_KEY = ['dealer-access-people'] as const;
const ACCOUNTS_KEY = 'dealer-access-accounts';

/** The people who hold access to my accounts, one row per (person, company). */
export function useDealerAccessPeopleQuery(params: DealerAccessPeopleParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...DEALER_ACCESS_KEY, params],
    queryFn: () => getPeople(params),
  });
}

/** My own accounts of one company; nothing is asked until a company is known. */
export function useDealerAccessAccountsQuery(company: string) {
  return useQuery({
    queryKey: [ACCOUNTS_KEY, company],
    queryFn: () => getAccounts(company),
    enabled: !!company,
  });
}

/** My own accounts of each picked company (Add people across one or two companies, N4.1). */
export function useDealerAccessAccountsForCompanies(companies: string[]) {
  const results = useQueries({
    queries: companies.map((company) => ({
      queryKey: [ACCOUNTS_KEY, company],
      queryFn: () => getAccounts(company),
    })),
  });
  const byCompany: Record<string, DealerAccessAccount[]> = {};
  companies.forEach((company, i) => {
    byCompany[company] = results[i]?.data ?? [];
  });
  return byCompany;
}

/** The Customer filter's server search (N3.3), for `SearchableMultiSelect.fetchOptions`. */
export function useDealerAccessCustomerSearch(mine: boolean, companies: string[]) {
  const queryClient = useQueryClient();
  const key = companies.join(',');
  return useCallback(
    (query: string) =>
      queryClient.fetchQuery({
        queryKey: ['dealer-access-customers', mine, key, query],
        queryFn: () => getCustomers({ query, mine, companies: key ? key.split(',') : [] }),
        staleTime: 30 * 1000,
      }),
    [queryClient, mine, key],
  );
}

/**
 * The list row of one person in one company, found by the phone typed for them (N4.3: "Edit / Show
 * <Name>" opens that person). Null when the list does not show them.
 */
export function useFindDealerAccessPerson() {
  const queryClient = useQueryClient();
  return useCallback(
    async (contactId: string, company: string, phone: string): Promise<DealerAccessRow | null> => {
      const params: DealerAccessPeopleParams = {
        pageIndex: 0,
        pageSize: 50,
        searchQuery: phone.replace(/\D/g, '').slice(-9),
        companies: [company],
        mine: false,
      };
      const page = await queryClient.fetchQuery({
        queryKey: [...DEALER_ACCESS_KEY, params],
        queryFn: () => getPeople(params),
      });
      return page.data.find((r) => r.contact_id === contactId && r.company === company) ?? null;
    },
    [queryClient],
  );
}
