import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UploadSessionRow } from './UploadSessionRow';
import type { UploadActivitySession } from './types';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

/**
 * Long import filenames used to render WIDER than the 500px drawer and spill
 * outside it: the title is a flex item, and a flex item defaults to
 * min-width:auto, so `truncate` alone could never constrain it. The name now
 * wraps inside the row instead of being cut off at the drawer edge.
 */
const LONG_TITLE =
  'Order Listing - Macro Version New JULY 2026 24.07.2026 10AM, 2PM & 5PM.xlsm';

function session(overrides: Partial<UploadActivitySession> = {}): UploadActivitySession {
  return {
    session_id: 's1',
    session_type: 'import_job',
    title: LONG_TITLE,
    started_at: new Date().toISOString(),
    finished_at: null,
    status: 'processing',
    aggregate: { total: 4231, uploading: 0, processing: 1, linked: 0, unlinked: 0, failed: 0 },
    needs_action: false,
    import_job_id: 'job-1',
    files: [],
    ...overrides,
  } as UploadActivitySession;
}

function titleEl() {
  return screen.getByTitle(LONG_TITLE);
}

describe('UploadSessionRow - long filenames', () => {
  it('shows the whole filename rather than clipping it', () => {
    render(<UploadSessionRow session={session()} />);
    expect(titleEl()).toHaveTextContent(LONG_TITLE);
  });

  it('lets the title shrink and wrap inside the drawer', () => {
    render(<UploadSessionRow session={session()} />);
    const el = titleEl();
    // min-w-0 is the actual fix: without it the flex item refuses to shrink and
    // the text renders past the drawer's right edge.
    expect(el.className).toContain('min-w-0');
    expect(el.className).toContain('break-words');
    expect(el.className).not.toContain('truncate');
  });

  it('keeps the flex row itself constrained', () => {
    render(<UploadSessionRow session={session()} />);
    const row = titleEl().parentElement!;
    expect(row.className).toContain('min-w-0');
  });

  it('applies the same treatment to the import-job branch', () => {
    // session_type import_job with an import_job_id renders the non-collapsible
    // branch; both branches must constrain the title identically.
    render(<UploadSessionRow session={session({ status: 'linked' })} />);
    const el = titleEl();
    expect(el.className).toContain('min-w-0');
    expect(el.className).not.toContain('truncate');
  });

  it('still exposes the full name as a tooltip', () => {
    render(<UploadSessionRow session={session()} />);
    expect(titleEl()).toHaveAttribute('title', LONG_TITLE);
  });
});
