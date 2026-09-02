/**
 * M6-05 - the dialog close X keeps the global focus ring.
 *
 * `outline-0` and `focus:outline-hidden` both defeated `*:focus-visible`
 * (styles.css:13) unconditionally, so tabbing to the X showed nothing at all -
 * a keyboard user closing a dialog had no visual confirmation the X was even
 * focused. Dropping just those two classes lets the global rule apply.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Dialog, DialogContent, DialogTitle } from './dialog';

describe('DialogClose focus ring (M6-05)', () => {
  it('the close X carries neither outline-0 nor focus:outline-hidden', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Edit record</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const close = screen.getByRole('button', { name: 'Close' });
    expect(close.className).not.toContain('outline-0');
    expect(close.className).not.toContain('focus:outline-hidden');
  });
});
