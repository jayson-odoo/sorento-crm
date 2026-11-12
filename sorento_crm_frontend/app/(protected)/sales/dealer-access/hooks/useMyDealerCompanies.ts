import { useQuery } from '@tanstack/react-query';
import { getMyCompanyContext } from '@/app/(protected)/system-management/companies/services/companyService';

/** The companies I may act in, as select options keyed by company code (what the API takes). */
export function useMyDealerCompanies() {
  const { data, isLoading } = useQuery({
    queryKey: ['company-my-context'],
    queryFn: getMyCompanyContext,
    staleTime: 30 * 1000,
  });
  const options = (data?.companies ?? []).map((c) => ({ value: c.code, label: c.name }));
  return { options, isLoading };
}
