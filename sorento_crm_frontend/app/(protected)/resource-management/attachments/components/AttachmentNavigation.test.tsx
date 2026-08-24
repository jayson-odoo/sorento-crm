/**
 * Tests for the AttachmentNavigation wrapper (record-navigation, IDs mode).
 *
 * The wrapper:
 * - reconstructs the list query from the detail URL via parseDetailSearch,
 * - feeds it to useAttachmentNeighbours (thin wrapper over useRecordNeighbours),
 * - renders RecordNavigation in IDs mode (prevId/nextId/index/total/isLoading),
 * - preserves the active list query in the URL when stepping to a neighbour.
 *
 * useAttachmentNeighbours is mocked so we assert the wrapping/threading, not the
 * network layer (that is covered by the backend pytest + the shared hook test).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import AttachmentNavigation from './AttachmentNavigation';
import { useAttachmentNeighbours } from '../hooks/useAttachments';

const push = vi.fn();
// Detail URL carries the active list query (sort + search + the folder/linkage/
// type/uploader/trash filters) the user came from.
const searchParams = new URLSearchParams(
  'page=2&limit=50&sort=name&dir=asc&query=invoice' +
    '&directory_id=dir-1&is_deleted=true&link_status=linked' +
    '&attachment_type_id=type-9&uploaded_by=user-7',
);

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

vi.mock('../hooks/useAttachments', () => ({
  useAttachmentNeighbours: vi.fn(),
}));

const mockedNeighbours = vi.mocked(useAttachmentNeighbours);

beforeEach(() => {
  push.mockClear();
  mockedNeighbours.mockReset();
});

describe('AttachmentNavigation', () => {
  it('passes the parsed list query (sort/dir/search + filters) to useAttachmentNeighbours', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 2,
      total: 7,
      isLoading: false,
    });

    render(<AttachmentNavigation attachmentId="cur" />);

    expect(mockedNeighbours).toHaveBeenCalledTimes(1);
    const [attachmentId, listParams] = mockedNeighbours.mock.calls[0];
    expect(attachmentId).toBe('cur');
    // page 2 -> pageIndex 1; sort/dir -> sorting; query -> searchQuery; the
    // attachment filters land verbatim so the folder/linkage/type scope holds.
    expect(listParams).toMatchObject({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'name', desc: false }],
      searchQuery: 'invoice',
      directory_id: 'dir-1',
      is_deleted: true,
      link_status: 'linked',
      attachment_type_id: 'type-9',
      uploaded_by: 'user-7',
    });
  });

  it('renders RecordNavigation in IDs mode with the resolved counter', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 7,
      isLoading: false,
    });

    render(<AttachmentNavigation attachmentId="cur" />);

    // index is 1-based from the backend; rendered verbatim as "3 / 7".
    expect(screen.getByText('3 / 7')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous attachment')).not.toBeDisabled();
    expect(screen.getByLabelText('Next attachment')).not.toBeDisabled();
  });

  it('disables a chevron when its neighbour id is null', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 7,
      isLoading: false,
    });

    render(<AttachmentNavigation attachmentId="cur" />);

    expect(screen.getByLabelText('Previous attachment')).toBeDisabled();
    expect(screen.getByLabelText('Next attachment')).not.toBeDisabled();
  });

  it('shows the loading counter while neighbours resolve', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 7,
      isLoading: true,
    });

    render(<AttachmentNavigation attachmentId="cur" />);

    expect(screen.getByText('… / 7')).toBeInTheDocument();
  });

  it('preserves the active list query in the URL when stepping to a neighbour', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 7,
      isLoading: false,
    });

    render(<AttachmentNavigation attachmentId="cur" />);
    fireEvent.click(screen.getByLabelText('Next attachment'));

    expect(push).toHaveBeenCalledTimes(1);
    const target = push.mock.calls[0][0] as string;
    expect(
      target.startsWith('/resource-management/attachments/n1?'),
    ).toBe(true);
    // The list query (sort + filters) is carried forward so the set stays stable.
    expect(target).toContain('sort=name');
    expect(target).toContain('query=invoice');
    expect(target).toContain('directory_id=dir-1');
    expect(target).toContain('link_status=linked');
  });
});
