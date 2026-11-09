import { keepPreviousData, useQuery } from '@tanstack/react-query';
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
    queryKey: [...DEALER_ACCESS_KEY, params],
    queryFn: () => getPeople(params),
    placeholderData: keepPreviousData,
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
