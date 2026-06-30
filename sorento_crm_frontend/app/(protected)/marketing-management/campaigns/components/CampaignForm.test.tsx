import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('../hooks/useCampaigns', () => ({
  useCampaign: () => ({ data: null, isLoading: false }),
  useCampaignTypes: () => ({
    data: [{ id: 't1', type_name: 'Email Blast' }],
    isLoading: false,
  }),
  useCreateCampaign: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCampaign: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import CampaignForm from './CampaignForm';

describe('CampaignForm (Bug A1 create)', () => {
  it('renders the create form with all key fields', () => {
    render(<CampaignForm />);
    expect(screen.getAllByText('Create Campaign').length).toBeGreaterThan(0);
    expect(screen.getByText('Campaign Code *')).toBeInTheDocument();
    expect(screen.getByText('Campaign Name *')).toBeInTheDocument();
    expect(screen.getByText('Campaign Type *')).toBeInTheDocument();
    expect(screen.getByText('Status *')).toBeInTheDocument();
    expect(screen.getByText('Start Date *')).toBeInTheDocument();
    expect(screen.getByText('Budget (MYR)')).toBeInTheDocument();
    expect(screen.getByText('Target Audience')).toBeInTheDocument();
  });

  it('shows the Create Campaign submit button (not Update)', () => {
    render(<CampaignForm />);
    expect(
      screen.getByRole('button', { name: /Create Campaign/i }),
    ).toBeInTheDocument();
  });
});
