/**
 * Guardrail for the two shared waits: each one has to be able to FAIL.
 *
 * The flakes these came from (CI runs 33978421827 and 34008077286, both of
 * which blocked a prod deploy) were not timing bugs in the components. They
 * were waits that could not fail: one waited for text the app had stopped
 * rendering, the other fired a change at a `<select>` before its options
 * existed. Both went green on an idle machine and red on a loaded runner.
 *
 * So the assertions below are mostly about the unhappy path - a helper used
 * where it guards nothing must say so.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { configure, getConfig } from '@testing-library/dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { selectOption, tickCheckbox, waitForSectionLoaded } from './index';

/** The real skeleton, swapped for content one macrotask later. */
function LoadsAfterATick() {
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 0);
    return () => clearTimeout(timer);
  }, []);
  if (loading) return <SectionSkeleton rows={2} />;
  return <p>Loaded content</p>;
}

/** A lookup-backed select: the option lands one macrotask after the field. */
function LateOptions() {
  const [options, setOptions] = React.useState<string[]>([]);
  const [value, setValue] = React.useState('');
  React.useEffect(() => {
    const timer = setTimeout(() => setOptions(['ZZTD01']), 0);
    return () => clearTimeout(timer);
  }, []);
  return (
    <select
      aria-label="Debtor"
      value={value}
      onChange={(e) => setValue(e.target.value)}
    >
      <option value="">Select a dealer...</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

describe('waitForSectionLoaded', () => {
  it('returns only once the real SectionSkeleton has gone', async () => {
    render(<LoadsAfterATick />);

    await waitForSectionLoaded();

    // Synchronous on purpose: this is the assertion the flaky specs made, and
    // it is the one that failed on CI against a still-skeleton DOM.
    expect(screen.getByText('Loaded content')).toBeInTheDocument();
  });

  it('throws when there was no skeleton, instead of passing quietly', async () => {
    render(<p>Loaded content</p>);

    await expect(waitForSectionLoaded()).rejects.toThrow(/already removed/i);
  });
});

describe('selectOption', () => {
  it('waits for a late-arriving option and takes the value', async () => {
    render(<LateOptions />);

    const select = await selectOption('Debtor', 'ZZTD01');

    expect(select.value).toBe('ZZTD01');
  });

  it('the trap it exists for: a bare change before the option lands sets nothing', async () => {
    render(<LateOptions />);
    const select = screen.getByLabelText('Debtor') as HTMLSelectElement;

    fireEvent.change(select, { target: { value: 'ZZTD01' } });

    // No throw, no warning: jsdom drops a value that matches no option, which
    // is why the specs that did this looked fine until the runner got busy.
    expect(select.value).toBe('');
  });

  it('reports a select that ignored the change rather than letting it through', async () => {
    render(
      <select aria-label="Debtor" value="" onChange={() => {}}>
        <option value="">Select a dealer...</option>
        <option value="ZZTD01">ZZT Dealer Sdn Bhd</option>
      </select>,
    );

    await expect(selectOption('Debtor', 'ZZTD01')).rejects.toThrow();
  });

  it('times out rather than firing a change for an option that never appears', async () => {
    const { asyncUtilTimeout } = getConfig();
    configure({ asyncUtilTimeout: 150 });
    try {
      render(<LateOptions />);

      await expect(selectOption('Debtor', 'ZZTD99')).rejects.toThrow();
    } finally {
      configure({ asyncUtilTimeout });
    }
  });
});

/**
 * A checkbox whose NODE is replaced once its data lands: the key flips, so
 * React unmounts the first button and mounts a second one in its place. That
 * is what a grid does between "skeleton" and "rows", and it is why a handle
 * held across an `await` is not safe to fire an event at.
 */
function ReplacedOnLoad() {
  const [loaded, setLoaded] = React.useState(false);
  const [checked, setChecked] = React.useState(false);
  React.useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), 0);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div>
      <button
        key={loaded ? 'rows' : 'skeleton'}
        type="button"
        role="checkbox"
        aria-checked={checked}
        aria-label="Select all rows on this page"
        onClick={() => setChecked(true)}
      />
      {checked ? <button type="button">Delete</button> : null}
    </div>
  );
}

describe('tickCheckbox', () => {
  it('the trap it exists for: clicking a handle React has replaced does nothing', async () => {
    render(<ReplacedOnLoad />);
    const stale = screen.getByLabelText('Select all rows on this page');
    await waitFor(() =>
      expect(screen.getByLabelText('Select all rows on this page')).not.toBe(
        stale,
      ),
    );

    fireEvent.click(stale);

    // No throw and no warning - the click simply went nowhere, which is how a
    // selection ends up empty and the failure lands on whatever was supposed
    // to appear afterwards.
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });

  it('clicks the current node, so the replacement above does not lose it', async () => {
    render(<ReplacedOnLoad />);
    const stale = screen.getByLabelText('Select all rows on this page');
    await waitFor(() =>
      expect(screen.getByLabelText('Select all rows on this page')).not.toBe(
        stale,
      ),
    );

    await tickCheckbox('Select all rows on this page');

    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('survives a replacement that lands inside its own wait', async () => {
    render(<ReplacedOnLoad />);

    // Deliberately NOT settled first: the swap lands while `tickCheckbox` is
    // awaiting, which is the ordering CI hits. A version that held the handle
    // its own `findByLabelText` returned clicks the discarded node here and
    // times out waiting for a tick that never happens.
    await tickCheckbox('Select all rows on this page');

    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('reports a click that did not tick the box', async () => {
    const { asyncUtilTimeout } = getConfig();
    configure({ asyncUtilTimeout: 150 });
    try {
      render(
        <button
          type="button"
          role="checkbox"
          aria-checked="false"
          aria-label="Select all rows on this page"
        />,
      );

      await expect(
        tickCheckbox('Select all rows on this page'),
      ).rejects.toThrow();
    } finally {
      configure({ asyncUtilTimeout });
    }
  });
});
