/**
 * BULK-CONTACT-ACCESS U21: the Dealer group options are the companies the caller can see. A
 * non-superadmin cannot read /companies/select (403), so the options come from the same source as
 * the header company switcher (/companies/my-context) and are never empty while that has companies.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const svc = vi.hoisted(() => ({ getCompaniesSelect: vi.fn(), getMyCompanyContext: vi.fn() }));
vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => svc);

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: { fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]> }) => {
    const [opts, setOpts] = React.useState<{ value: string; label: string }[] | null>(null);
    React.useEffect(() => {
      void props.fetchOptions?.('').then(setOpts);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <ul data-testid="options">
        {(opts ?? []).map((o) => (
          <li key={o.value}>{o.label}</li>
        ))}
      </ul>
    );
  },
}));

import { DealerGroupSelect } from './DealerGroupSelect';

const company = (id: string, name: string, code: string) => ({ id, name, code, is_active: true });

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DealerGroupSelect options', () => {
  it('a non-superadmin (companies/select refused) gets the granted companies, not an empty list', async () => {
    svc.getCompaniesSelect.mockRejectedValue(new Error('Superadmin access is required to manage companies.'));
    svc.getMyCompanyContext.mockResolvedValue({
      companies: [company('c-srt', 'Sorento Sdn Bhd', 'SRT'), company('c-mch', 'Mocha Sdn Bhd', 'MCH')],
      active_company_id: 'c-srt',
      last_active_company_id: 'c-srt',
    });
    render(<DealerGroupSelect value={null} onChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2));
    expect(screen.getByText('Sorento Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Mocha Sdn Bhd')).toBeInTheDocument();
  });
});
