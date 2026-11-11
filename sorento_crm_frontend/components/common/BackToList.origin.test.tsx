/**
 * PROJECT-STAGE-ACTIONS (crew pass 11 Nov): a record opened from somewhere that named itself in
 * `?back=` (a project's Sponsorship Form tab) goes Back there, not to the list.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

let params = new URLSearchParams();
vi.mock('next/navigation', () => ({ useSearchParams: () => params }));
const scope = vi.hoisted(() => ({ limited: false }));
vi.mock('@/hooks/useRequestScope', () => ({ useRequestScope: () => ({ limited: scope.limited }) }));

import BackToList from './BackToList';

function renderBack() {
  render(
    <BackToList
      listPath="/procurement-management/sponsorship-forms"
      label="Back to sponsorship forms"
      originLabel="Back to project"
      hideForLimited="sponsorship_form"
    />,
  );
}

beforeEach(() => {
  scope.limited = false;
  params = new URLSearchParams();
});

describe('BackToList with an origin', () => {
  it('returns to the page that opened the record', () => {
    params = new URLSearchParams({ back: '/project-sales/p1?tab=sponsorships' });
    renderBack();
    const link = screen.getByRole('link', { name: /Back to project/ });
    expect(link.getAttribute('href')).toBe('/project-sales/p1?tab=sponsorships');
  });

  it('is shown to a salesperson limited to their own forms too', () => {
    scope.limited = true;
    params = new URLSearchParams({ back: '/project-sales/p1?tab=sponsorships' });
    renderBack();
    expect(screen.getByRole('link', { name: /Back to project/ })).toBeTruthy();
  });

  it('ignores an origin that is not a path in this app', () => {
    params = new URLSearchParams({ back: '//evil.example/x' });
    renderBack();
    const href = screen.getByRole('link', { name: /Back to sponsorship forms/ }).getAttribute('href') ?? '';
    // The list, never the foreign origin (which may ride along as list state, as on other pages).
    expect(href.startsWith('/procurement-management/sponsorship-forms')).toBe(true);
  });

  it('without an origin goes to the list', () => {
    renderBack();
    expect(screen.getByRole('link', { name: /Back to sponsorship forms/ })).toBeTruthy();
  });
});
