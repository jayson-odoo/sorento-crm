import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ListPageToolbar } from './ListPageToolbar';

/**
 * Regression: the Roles search box lost focus after every keystroke.
 *
 * Root cause: each keystroke updates a react-query key that includes the
 * search term, so the query briefly re-enters its pending state
 * (isLoading=true). ListPageToolbar used to set `disabled={isLoading}` on the
 * search <input>; a disabled element is blurred by the browser, so focus was
 * lost after every character.
 *
 * The harness below mirrors the real call sites: it forwards an `isLoading`
 * that is TRUE whenever the latest typed value has not yet "resolved"
 * (i.e. true on every keystroke), exactly the condition that triggered the bug.
 */
function Harness() {
  const [value, setValue] = React.useState('');
  const [resolved, setResolved] = React.useState('');
  // With per-keystroke query keys this flips true on every change — the bug condition.
  const isLoading = value !== resolved;

  return (
    <ListPageToolbar
      searchPlaceholder="Search roles"
      searchValue={value}
      onSearchChange={(v) => {
        setValue(v);
        // Defer "resolution" so isLoading stays true through the keystroke.
        setTimeout(() => setResolved(v), 0);
      }}
      createButton={<button type="button">Add Role</button>}
      isLoading={isLoading}
    />
  );
}

describe('ListPageToolbar search focus', () => {
  it('keeps focus and accumulates value across consecutive keystrokes', () => {
    render(<Harness />);

    const input = screen.getByPlaceholderText('Search roles') as HTMLInputElement;
    const sameNode = input;

    input.focus();
    expect(document.activeElement).toBe(input);

    // Simulate continuous typing: each keystroke sets the next accumulated value
    // (a controlled input does not append on its own under fireEvent).
    for (const next of ['a', 'ad', 'adm', 'admi', 'admin']) {
      fireEvent.change(sameNode, { target: { value: next } });
    }

    // The same DOM node must persist (no remount) ...
    expect(screen.getByPlaceholderText('Search roles')).toBe(sameNode);
    // ... it must not be disabled mid-load ...
    expect(sameNode.disabled).toBe(false);
    // ... it must still hold focus ...
    expect(document.activeElement).toBe(sameNode);
    // ... and the full string accumulated, not just the last char.
    expect(sameNode.value).toBe('admin');
  });

  it('never disables the search input even while loading', () => {
    render(
      <ListPageToolbar
        searchPlaceholder="Search roles"
        searchValue="abc"
        onSearchChange={() => {}}
        createButton={<button type="button">Add Role</button>}
        isLoading
      />,
    );
    const input = screen.getByPlaceholderText('Search roles') as HTMLInputElement;
    expect(input.disabled).toBe(false);
  });
});
