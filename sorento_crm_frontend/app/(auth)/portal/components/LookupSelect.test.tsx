import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    // lookupSet resolves to LookupSetResult ({ options, defaultValue }), not a
    // bare array — the component reads `data.options`.
    lookupSet: vi.fn().mockResolvedValue({
      options: [
        { value: 'showroom', label: 'Showroom' },
        { value: 'mockup', label: 'Mockup' },
        { value: 'others', label: 'Others' },
      ],
      defaultValue: null,
    }),
  };
});

import { LookupSelect } from './LookupSelect';
import { lookupSet } from '../lib/portal-client';

beforeEach(() => vi.clearAllMocks());

describe('LookupSelect (portal sponsor subject)', () => {
  it('loads options for the procurement_sponsor_subject set and shows the selected label', async () => {
    render(
      <LookupSelect
        setKey="procurement_sponsor_subject"
        value="mockup"
        onChange={() => {}}
        placeholder="Select sponsor subject"
      />,
    );

    await waitFor(() =>
      expect(lookupSet).toHaveBeenCalledWith('procurement_sponsor_subject'),
    );
    // The trigger reflects the chosen value's label once options resolve.
    await waitFor(() => expect(screen.getByText('Mockup')).toBeInTheDocument());
  });

  it('renders the placeholder when no value is selected', async () => {
    render(
      <LookupSelect
        setKey="procurement_sponsor_subject"
        value=""
        onChange={() => {}}
        placeholder="Select sponsor subject"
      />,
    );
    await waitFor(() =>
      expect(lookupSet).toHaveBeenCalledWith('procurement_sponsor_subject'),
    );
    expect(screen.getByText('Select sponsor subject')).toBeInTheDocument();
  });
});
