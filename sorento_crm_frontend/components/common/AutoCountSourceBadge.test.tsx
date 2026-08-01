/**
 * AutoCountSourceBadge — uniform provenance signal reused across every mirror
 * list + detail. Defaults to the AutoCount (read-only) label; "manual" rows on
 * reused tables get the Manual label instead.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { AutoCountSourceBadge } from './AutoCountSourceBadge';

describe('AutoCountSourceBadge', () => {
  it('shows AutoCount by default (new mirror tables are always synced)', () => {
    render(<AutoCountSourceBadge />);
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
    cleanup();
  });

  it('shows AutoCount for source=autocount', () => {
    render(<AutoCountSourceBadge source="autocount" />);
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
    cleanup();
  });

  it('shows Manual for source=manual', () => {
    render(<AutoCountSourceBadge source="manual" />);
    expect(screen.getByText('Manual')).toBeInTheDocument();
    cleanup();
  });
});
