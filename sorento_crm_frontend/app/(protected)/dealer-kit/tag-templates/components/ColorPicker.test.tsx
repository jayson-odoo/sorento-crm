/**
 * The colour control is a picker, not a palette (D54, AC-M.23).
 *
 * Written before the change. Twelve swatches and a hex box meant a designer who
 * wanted the thirteenth colour had to know its hex code, which is not how
 * anybody picks a colour. The popover's primary control is now the browser's
 * own spectrum input, and the three ways in have to agree: the spectrum, the
 * swatches and the box all name one colour.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ColorPicker } from './ColorPicker';

function spectrum(): HTMLInputElement {
  return screen.getByLabelText('Pick a colour') as HTMLInputElement;
}

function hexBox(): HTMLInputElement {
  return screen.getByLabelText('Hex colour') as HTMLInputElement;
}

function openPopover(value = '#000000') {
  const onChange = vi.fn();
  render(<ColorPicker value={value} onChange={onChange} label="Colour" />);
  fireEvent.click(screen.getByTitle(value));
  return onChange;
}

describe('ColorPicker', () => {
  it('the popover leads with a spectrum control, not a list of swatches', () => {
    openPopover();

    expect(spectrum().type).toBe('color');
  });

  it('picking a colour hands the hex straight to the layer', () => {
    const onChange = openPopover();

    fireEvent.change(spectrum(), { target: { value: '#12ab34' } });

    expect(onChange).toHaveBeenCalledWith('#12ab34');
  });

  it('picking a colour rewrites the hex box, so the two never disagree', () => {
    openPopover();

    fireEvent.change(spectrum(), { target: { value: '#12ab34' } });

    expect(hexBox().value).toBe('#12ab34');
  });

  it('typing a hex moves the picker to it', () => {
    openPopover();

    fireEvent.change(hexBox(), {
      target: { value: '#ff0000' },
    });

    expect(spectrum().value).toBe('#ff0000');
  });

  it('a half-typed hex is ignored until it is a colour', () => {
    const onChange = openPopover();

    fireEvent.change(hexBox(), { target: { value: '#ff' } });

    expect(onChange).not.toHaveBeenCalled();
    // The spectrum keeps the last real colour rather than blanking.
    expect(spectrum().value).toBe('#000000');
  });

  it('a three-digit hex reaches the picker as the six-digit colour it means', () => {
    openPopover();

    fireEvent.change(hexBox(), { target: { value: '#f00' } });

    expect(spectrum().value).toBe('#ff0000');
  });

  it('the twelve brand swatches are still there, under the spectrum', () => {
    const onChange = openPopover();

    fireEvent.click(screen.getByTitle('Sorento Red'));

    expect(onChange).toHaveBeenCalledWith('#b44d2e');
  });

  it('transparent is still reachable and the spectrum falls back to black', () => {
    const onChange = openPopover('transparent');

    expect(spectrum().value).toBe('#000000');

    fireEvent.click(screen.getByTitle('Transparent'));
    expect(onChange).toHaveBeenCalledWith('transparent');
  });
});
