/**
 * PROJECT-RELATED-RECORDS fix round 3 (browser pass 1 D1, D2; AC-C3a): the shared Registered project
 * picker, on every form. Each option is ONE line, code + title cut with "..." and the full text on
 * hover; the closed control cuts a long pick to one line inside its cell (the page never scrolls
 * sideways), and its clear button empties it. Fake values only.
 */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';

const { LONG } = vi.hoisted(() => ({
  LONG: 'PS26-0004 - Zzt Riverside Gardens Phase 2 Block A, B and C serviced apartments with retail podium and car park',
}));

vi.mock('@/app/(protected)/complaint-management/complaints/services/complaintService', () => ({
  searchProjectsForLink: vi.fn().mockResolvedValue([
    { value: 'p4', label: LONG, description: 'Zzt Developer - Approved' },
  ]),
}));

import { RegisteredProjectSelect } from './RegisteredProjectSelect';

const trigger = () => document.querySelector('[data-slot="searchable-select-trigger"]') as HTMLElement;

afterEach(() => cleanup());

describe('RegisteredProjectSelect', () => {
  it('D1 an option is one line: the label cut with "..." and the full text on hover', async () => {
    render(<RegisteredProjectSelect value="" onChange={() => {}} />);
    fireEvent.click(trigger());
    const option = await waitFor(() => {
      const found = document.querySelector('[role="option"]');
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    const text = Array.from(option.querySelectorAll('span')).find((s) => s.textContent === LONG);
    expect(text, 'the label in one span').toBeTruthy();
    expect(text!.className).toContain('truncate');
    expect(text!.getAttribute('title')).toBe(LONG);
    // No second line under it.
    expect(option.textContent).toBe(LONG);
  });

  it('D2 a long pick is cut to one line in the closed control, inside its cell', () => {
    render(
      <RegisteredProjectSelect value="p4" onChange={() => {}} selectedOption={{ value: 'p4', label: LONG }} />,
    );
    const label = Array.from(trigger().querySelectorAll('span')).find((s) => s.textContent === LONG)!;
    expect(label.className).toContain('truncate');
    expect(label.getAttribute('title')).toBe(LONG);
    // The control does not size its cell from the title's length.
    expect(trigger().parentElement!.className).toContain('[contain:inline-size]');
  });

  it('D2 clear empties it', () => {
    const onChange = vi.fn();
    render(
      <RegisteredProjectSelect value="p4" onChange={onChange} selectedOption={{ value: 'p4', label: LONG }} />,
    );
    fireEvent.pointerDown(document.querySelector('[aria-label="Clear selection"]')!);
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
