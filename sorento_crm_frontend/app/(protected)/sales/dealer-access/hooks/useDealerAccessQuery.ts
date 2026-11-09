import { useQuery } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  getAccounts,
  getPeople,
  type DealerAccessPeopleParams,
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
