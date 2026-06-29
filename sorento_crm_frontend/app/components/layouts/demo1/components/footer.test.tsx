/**
 * Footer — UAC1.2: only Support + copyright; no demo/template links.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// Container pulls layout settings context; stub it to a plain wrapper.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children?: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { Footer } from './footer';

describe('demo1 Footer', () => {
  it('UAC1.2: renders Support and the copyright', () => {
    render(<Footer />);

    const support = screen.getByRole('link', { name: 'Support' });
    expect(support).toBeInTheDocument();
    expect(support).toHaveAttribute('href', '/ticket-management/tickets');

    expect(
      screen.getByText(`${new Date().getFullYear()} @ Foundryx`),
    ).toBeInTheDocument();
  });

  it('UAC1.2: does NOT render Docs / Purchase / FAQ / License links', () => {
    render(<Footer />);

    expect(screen.queryByText('Docs')).not.toBeInTheDocument();
    expect(screen.queryByText('Purchase')).not.toBeInTheDocument();
    expect(screen.queryByText('FAQ')).not.toBeInTheDocument();
    expect(screen.queryByText('License')).not.toBeInTheDocument();
  });

  it('UAC1.2: no empty-href links in the footer', () => {
    const { container } = render(<Footer />);
    expect(container.querySelector('a[href=""]')).toBeNull();
  });
});
