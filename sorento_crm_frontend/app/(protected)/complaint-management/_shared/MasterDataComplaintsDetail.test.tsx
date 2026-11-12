/** AFTER-SALES-P1 fix round 2 (R2-6): a resolution's Details card shows "Requires service job"; one Back only. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
}));
vi.mock('./LinkedComplaintsPanel', () => ({ LinkedComplaintsPanel: () => null }));

import { MasterDataComplaintsDetail } from './MasterDataComplaintsDetail';

const props = { id: 'r-1', isLoading: false, listHref: '/x', listLabel: 'resolutions' };

describe('MasterDataComplaintsDetail', () => {
  it('shows Requires service job for a resolution', () => {
    render(<MasterDataComplaintsDetail kind="resolution" record={{ name: 'Fix', is_active: true, requires_service_job: true }} {...props} />);
    expect(screen.getByText('Requires service job')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('shows No when off, and nothing for a root cause', () => {
    const { unmount } = render(<MasterDataComplaintsDetail kind="resolution" record={{ name: 'Fix', is_active: true, requires_service_job: false }} {...props} />);
    expect(screen.getByText('No')).toBeInTheDocument();
    unmount();
    render(<MasterDataComplaintsDetail kind="root_cause" record={{ name: 'RC', is_active: true }} {...props} />);
    expect(screen.queryByText('Requires service job')).toBeNull();
  });

  it('has no second Back button (the page header carries it)', () => {
    render(<MasterDataComplaintsDetail kind="resolution" record={{ name: 'Fix', is_active: true }} {...props} />);
    expect(screen.queryAllByRole('link', { name: /Back to resolutions/ })).toHaveLength(0);
  });
});
