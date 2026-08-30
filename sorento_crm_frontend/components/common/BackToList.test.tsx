/**
 * S3-01 - Back carries the list's query string.
 *
 * The list wrote its page, sort, search and filters into the detail URL when the
 * row was clicked. Back hands that same string back, so the user returns to the
 * page they left instead of a fresh page 1, and the list's cache entry (the one
 * the pager was reading) is the one that answers.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import BackToList from './BackToList';

let search = '';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  cleanup();
  search = '';
});

describe('BackToList', () => {
  it('S3-01: appends the detail URL query string to the list path', () => {
    search = 'page=3&limit=25&sort=name&dir=asc&query=ada&roleId=r1';

    render(<BackToList listPath="/user-management/users" label="Back to users" />);

    expect(screen.getByRole('link', { name: /Back to users/ }).getAttribute('href')).toBe(
      '/user-management/users?page=3&limit=25&sort=name&dir=asc&query=ada&roleId=r1',
    );
  });

  it('S3-01: a detail opened without list state links to the bare list', () => {
    render(<BackToList listPath="/order-management/orders" label="Back to delivery orders" />);

    expect(
      screen.getByRole('link', { name: /Back to delivery orders/ }).getAttribute('href'),
    ).toBe('/order-management/orders');
  });

  it('S3-01: a caller that owns its whole href keeps it (spec verification worklist)', () => {
    search = 'page=2&limit=50';

    render(
      <BackToList
        listPath="/master-data-management/spec-verification?page=7&status=pending"
        label="Back to spec verification"
        appendListState={false}
      />,
    );

    expect(
      screen.getByRole('link', { name: /Back to spec verification/ }).getAttribute('href'),
    ).toBe('/master-data-management/spec-verification?page=7&status=pending');
  });
});
