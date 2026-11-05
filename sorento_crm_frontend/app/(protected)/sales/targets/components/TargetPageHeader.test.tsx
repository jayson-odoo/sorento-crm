/**
 * TARGET-EDIT-CTA, owner 5 Nov: "if I am at dealer target, then I go back should go back to
 * dealer target tab". Back to targets and the Targets crumb both open the list on the tab the
 * record belongs to (its subject kind), so a direct link returns to the right tab as well.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

let search = '';
const target = vi.hoisted(() => ({ data: undefined as { subject_kind: string } | undefined }));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => '/sales/targets/t1',
}));
vi.mock('@/hooks/use-menu', () => ({ useMenu: () => ({ getBreadcrumb: () => [] }) }));
vi.mock('../hooks/useSalesTargets', () => ({ useSalesTarget: () => ({ data: target.data }) }));

import TargetPageHeader from './TargetPageHeader';

function hrefs() {
  return {
    back: screen.getByRole('link', { name: /Back to targets/ }).getAttribute('href'),
    crumb: screen.getByRole('link', { name: 'Targets' }).getAttribute('href'),
  };
}

beforeEach(() => {
  cleanup();
  search = '';
  target.data = undefined;
});

describe('TargetPageHeader: back to the list tab the target belongs to', () => {
  it('a dealer target opened from the list returns to the Dealers tab with the list state', () => {
    search = 'page=1&limit=25&from=t1&tab=periods';
    target.data = { subject_kind: 'dealer' };
    render(<TargetPageHeader id="t1" />);
    expect(hrefs()).toEqual({
      back: '/sales/targets?tab=dealer&page=1&limit=25&from=t1',
      crumb: '/sales/targets?tab=dealer&page=1&limit=25&from=t1',
    });
  });

  it('an agent target returns to the Agents tab', () => {
    search = 'page=1&limit=25&from=t1&team=north';
    target.data = { subject_kind: 'agent' };
    render(<TargetPageHeader id="t1" />);
    expect(hrefs()).toEqual({
      back: '/sales/targets?tab=agent&page=1&limit=25&from=t1&team=north',
      crumb: '/sales/targets?tab=agent&page=1&limit=25&from=t1&team=north',
    });
  });

  it('a dealer target opened straight from a link still returns to the Dealers tab', () => {
    target.data = { subject_kind: 'dealer' };
    render(<TargetPageHeader id="t1" />);
    expect(hrefs()).toEqual({ back: '/sales/targets?tab=dealer', crumb: '/sales/targets?tab=dealer' });
  });

  it('keeps the trail Dashboards, Sales, Targets, Target', () => {
    target.data = { subject_kind: 'team' };
    render(<TargetPageHeader id="t1" />);
    expect(screen.getByRole('heading', { name: 'Target' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Dashboards' }).getAttribute('href')).toBe('/');
    expect(screen.getByText('Sales')).toBeTruthy();
    expect(hrefs().crumb).toBe('/sales/targets?tab=team');
  });
});
