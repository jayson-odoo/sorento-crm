/**
 * PORTAL-P3-ROLE-MENU round 8, S3: the banner below `sm` is one line: the target name stays
 * visible, the "Records ..." sentence is hidden below sm, Exit is a button named "Exit impersonation".
 * The page offset is the same 40px at every width, with no window.innerWidth read.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useImpersonation', () => ({
  useImpersonation: () => ({
    session: {
      sessionId: 's1',
      startedAt: '2026-10-28T00:00:00Z',
      targetUser: { id: 'u1', name: 'Test Salesperson A', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
    },
    stop: vi.fn(),
    stopping: false,
  }),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>{children}</a>
  ),
}));
vi.mock('@/services/contactImpersonationService', () => ({ stopContactImpersonation: vi.fn() }));

import { ImpersonationBanner } from './ImpersonationBanner';

let innerWidthReads = 0;

beforeEach(() => {
  window.localStorage.clear();
  innerWidthReads = 0;
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    get: () => {
      innerWidthReads += 1;
      return 375;
    },
  });
});

function classesOf(el: Element | null): string[] {
  return (el?.getAttribute('class') ?? '').split(/\s+/).filter(Boolean);
}

describe('ImpersonationBanner on a phone (S3)', () => {
  it('the target name is visible text, the Records sentence is hidden below sm', () => {
    render(<ImpersonationBanner />);
    const name = screen.getByText('Test Salesperson A');
    expect(name.closest('.hidden')).toBeNull();
    const sentence = screen.getByText(/Records you create or modify are still attributed to you\./);
    const cls = classesOf(sentence);
    expect(cls).toContain('hidden');
    expect(cls).toContain('sm:inline');
  });

  it('desktop text is unchanged', () => {
    render(<ImpersonationBanner />);
    expect(screen.getByText(/You are currently impersonating/)).toBeInTheDocument();
    expect(screen.getByText(/Records you create or modify are still attributed to you\./)).toBeInTheDocument();
  });

  it('Exit is a button named "Exit impersonation"', () => {
    render(<ImpersonationBanner />);
    expect(screen.getByRole('button', { name: 'Exit impersonation' })).toBeInTheDocument();
  });

  it('one line: the row does not wrap or stack', () => {
    render(<ImpersonationBanner />);
    const row = screen.getByTestId('impersonation-banner').firstElementChild;
    const cls = classesOf(row);
    expect(cls).not.toContain('flex-wrap');
    expect(cls).not.toContain('flex-col');
  });

  it('page offset is 40px and no window.innerWidth is read', () => {
    render(<ImpersonationBanner />);
    expect(document.body.style.paddingTop).toBe('40px');
    expect(document.documentElement.style.getPropertyValue('--impersonation-banner-height')).toBe('40px');
    expect(innerWidthReads).toBe(0);
  });
});

describe('ImpersonationBanner name stays readable at 375 (round 9)', () => {
  it('the lead-in words are hidden below sm', () => {
    render(<ImpersonationBanner />);
    const cls = classesOf(screen.getByText(/You are currently impersonating/));
    expect(cls).toContain('hidden');
    expect(cls).toContain('sm:inline');
  });

  it('the name can shrink and truncate', () => {
    render(<ImpersonationBanner />);
    const banner = screen.getByTestId('impersonation-banner');
    let el: Element | null = screen.getByText('Test Salesperson A');
    let ok = false;
    while (el && el !== banner) {
      const cls = classesOf(el);
      if (cls.includes('min-w-0') && cls.includes('truncate')) ok = true;
      el = el.parentElement;
    }
    expect(ok).toBe(true);
  });

  it('the Exit control does not shrink', () => {
    render(<ImpersonationBanner />);
    const exit = screen.getByRole('button', { name: 'Exit impersonation' });
    expect(classesOf(exit).includes('shrink-0') || classesOf(exit.parentElement).includes('shrink-0')).toBe(true);
  });
});
