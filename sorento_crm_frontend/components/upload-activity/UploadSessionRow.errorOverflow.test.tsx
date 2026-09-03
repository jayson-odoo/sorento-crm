import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UploadSessionRow } from './UploadSessionRow';
import type { UploadActivitySession } from './types';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

/**
 * A production import job whose `job_error` is a full Python traceback
 * (~2,000 chars) - a raw traceback rendered as one unbroken line, which
 * overflowed the drawer and pushed the row's status icon off the right
 * edge. The row now shows only the last line (the exception itself),
 * truncated to one line, with the full traceback on hover.
 */
const EXCEPTION_LINE =
  'ValueError: Invalid attribute name: process_outstanding_import';

const TRACEBACK = [
  'Traceback (most recent call last):',
  '  File "/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/venv/lib/python3.12/site-packages/rq/worker.py", line 1414, in perform_job',
  '    rv = job.perform()',
  '  File "/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/app/tasks/import_tasks.py", line 512, in process_outstanding_import',
  '    ' + 'x'.repeat(1800), // pad well past 2,000 chars total
  EXCEPTION_LINE,
].join('\n');

function session(overrides: Partial<UploadActivitySession> = {}): UploadActivitySession {
  return {
    session_id: 'job-fail-1',
    session_type: 'import_job',
    title: 'SPO-202608-0099.xlsx',
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    status: 'failed',
    aggregate: { total: 0, uploading: 0, processing: 0, linked: 0, unlinked: 0, failed: 0 },
    needs_action: true,
    import_job_id: 'job-fail-1',
    files: [],
    job_error: TRACEBACK,
    ...overrides,
  } as UploadActivitySession;
}

describe('UploadSessionRow - failed import with a traceback error', () => {
  it('renders the last line of the error, clamped rather than cut mid-word (N4, fix round 5)', () => {
    render(<UploadSessionRow session={session()} />);
    const summaryEl = screen.getByText(EXCEPTION_LINE);
    expect(summaryEl.textContent).toBe(EXCEPTION_LINE);
    // `errorSummary` already strips the traceback down to this one line, so a plain
    // `truncate` (single line, ellipsis mid-word) is no longer needed to keep the row
    // from overflowing - `line-clamp-2 break-all` wraps it instead.
    expect(summaryEl.className).toContain('line-clamp-2');
    expect(summaryEl.className).toContain('break-all');
    expect(summaryEl.className).not.toContain('truncate');
  });

  it('never carries the raw traceback header in the visible text', () => {
    render(<UploadSessionRow session={session()} />);
    expect(screen.queryByText(/Traceback \(most recent call last\)/)).toBeNull();
  });

  it('still exposes the full traceback as a tooltip', () => {
    render(<UploadSessionRow session={session()} />);
    const summaryEl = screen.getByText(EXCEPTION_LINE);
    expect(summaryEl.getAttribute('title')).toBe(TRACEBACK);
  });

  it('keeps the status icon in the DOM, never pushed out by the error text', () => {
    render(<UploadSessionRow session={session()} />);
    const badge = screen.getByText('Failed');
    expect(badge).toBeTruthy();
    expect(badge.closest('.shrink-0')).toBeTruthy();
    // the SVG status icon rendered inside the badge
    expect(badge.parentElement?.querySelector('svg')).toBeTruthy();
  });
});
