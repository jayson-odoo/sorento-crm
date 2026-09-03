import { describe, it, expect } from 'vitest';
import { errorSummary } from './errorSummary';

describe('errorSummary', () => {
  it('returns the last non-empty line of a multi-line traceback', () => {
    const traceback = [
      'Traceback (most recent call last):',
      '  File "/app/app/tasks/import_tasks.py", line 512, in process_outstanding_import',
      '    getattr(module, attr_name)',
      'ValueError: Invalid attribute name: process_outstanding_import',
    ].join('\n');

    expect(errorSummary(traceback)).toBe(
      'ValueError: Invalid attribute name: process_outstanding_import',
    );
  });

  it('ignores trailing blank lines', () => {
    const text = 'line one\nline two\n\n\n';
    expect(errorSummary(text)).toBe('line two');
  });

  it('passes a single-line message through unchanged', () => {
    const message =
      'Moved to FailedJobRegistry, due to AbandonedJobError, at 2026-08-19 03:28:40.362670+00:00';
    expect(errorSummary(message)).toBe(message);
  });

  it('caps a very long single line at ~200 chars', () => {
    const huge = 'x'.repeat(500);
    const out = errorSummary(huge);
    expect(out.length).toBeLessThanOrEqual(201); // 200 chars + ellipsis
    expect(out.startsWith('x'.repeat(200))).toBe(true);
  });

  it('returns empty input unchanged', () => {
    expect(errorSummary('')).toBe('');
  });
});
