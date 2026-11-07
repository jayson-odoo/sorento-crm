/**
 * The colour control is a Figma-style spectrum picker, not the native OS
 * `<input type=color>` (D6, S3, AC-M.23). Written before the change landed
 * for real interaction: the square and hue bar (pointer-drag) are covered in
 * the browser (agent-browser evidence, AC-X-1) since jsdom has no real
 * pointer geometry - this file covers what jsdom CAN assert: the popover's
 * shape, the hex box round trip, the swatch rows, and the eyedropper
 * button's conditional render.
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import path from 'path';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ColorPicker } from './ColorPicker';
import { hsvToHex } from '@/lib/dealer-kit/colour';

function hexBox(): HTMLInputElement {
  // Two inputs share the same accessible role/name pattern - the outer
  // field (always visible) and the one inside the popover (AC-S3-1). The
  // outer one is unambiguous by its own label.
  return screen.getByLabelText('Hex colour') as HTMLInputElement;
}

function popoverHexBox(): HTMLInputElement {
  return screen.getByLabelText('Hex') as HTMLInputElement;
}

function openPopover(value = '#000000', usedColours: string[] = []) {
  const onChange = vi.fn();
  render(<ColorPicker value={value} onChange={onChange} label="Colour" usedColours={usedColours} />);
  fireEvent.click(screen.getByTitle(value));
  return onChange;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ColorPicker', () => {
  it('the native OS colour input is gone (AC-S3-7)', () => {
    openPopover();

    expect(document.querySelector('input[type="color"]')).toBeNull();
  });

  it('the popover has a saturation/brightness square and a hue slider (AC-S3-1)', () => {
    openPopover();

    expect(screen.getByRole('slider', { name: 'Saturation and brightness' })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: 'Hue' })).toBeInTheDocument();
  });

  it('typing a hex in the popover box moves the outer field to match', () => {
    openPopover();

    fireEvent.change(popoverHexBox(), { target: { value: '#12ab34' } });

    expect(hexBox().value).toBe('#12ab34');
  });

  it('typing a hex in the outer field commits on Enter', () => {
    const onChange = openPopover();

    fireEvent.change(hexBox(), { target: { value: '#ff0000' } });
    fireEvent.keyDown(hexBox(), { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('#ff0000');
  });

  it('a half-typed hex is ignored on blur rather than reaching onChange', () => {
    const onChange = openPopover();

    fireEvent.change(hexBox(), { target: { value: '#ff' } });
    fireEvent.blur(hexBox());

    expect(onChange).not.toHaveBeenCalled();
  });

  it('reverts the box to the last real value on blur when what was typed is invalid (S4)', () => {
    const onChange = openPopover('#123456');

    fireEvent.change(hexBox(), { target: { value: '#ff' } });
    fireEvent.blur(hexBox());

    expect(onChange).not.toHaveBeenCalled();
    expect(hexBox().value).toBe('#123456');
  });

  it('leaves a valid typed value in the box on blur, unreverted', () => {
    openPopover('#123456');

    fireEvent.change(hexBox(), { target: { value: '#ff0000' } });
    fireEvent.blur(hexBox());

    expect(hexBox().value).toBe('#ff0000');
  });

  it('a three-digit hex is accepted and reaches onChange as-typed', () => {
    const onChange = openPopover();

    fireEvent.change(hexBox(), { target: { value: '#f00' } });
    fireEvent.blur(hexBox());

    expect(onChange).toHaveBeenCalledWith('#f00');
  });

  it('the twelve brand swatches are still there', () => {
    const onChange = openPopover();

    fireEvent.click(screen.getByTitle('Sorento Red'));

    expect(onChange).toHaveBeenCalledWith('#b44d2e');
  });

  it('transparent is still reachable as a brand swatch', () => {
    const onChange = openPopover();

    fireEvent.click(screen.getByTitle('Transparent'));

    expect(onChange).toHaveBeenCalledWith('transparent');
  });

  it('shows a "This tag" row when colours are already used on the tag', () => {
    openPopover('#000000', ['#FF0000', '#00FF00']);

    expect(screen.getByText('This tag')).toBeInTheDocument();
  });

  it('clicking a "This tag" swatch applies it', () => {
    const onChange = openPopover('#000000', ['#FF0000']);

    fireEvent.click(screen.getByTitle('#FF0000'));

    expect(onChange).toHaveBeenCalledWith('#FF0000');
  });

  it('hides the "This tag" row when the tag has no other colours yet', () => {
    openPopover('#000000', []);

    expect(screen.queryByText('This tag')).not.toBeInTheDocument();
  });

  it('renders the eyedropper button when window.EyeDropper exists', () => {
    vi.stubGlobal('EyeDropper', class {
      open() {
        return Promise.resolve({ sRGBHex: '#123456' });
      }
    });

    openPopover();

    expect(screen.getByTitle('Pick colour from screen')).toBeInTheDocument();
  });

  it('hides the eyedropper button when the browser has no EyeDropper API', () => {
    openPopover();

    expect(screen.queryByTitle('Pick colour from screen')).not.toBeInTheDocument();
  });

  it('picking with the eyedropper hands the picked colour to onChange', async () => {
    vi.stubGlobal('EyeDropper', class {
      open() {
        return Promise.resolve({ sRGBHex: '#654321' });
      }
    });

    const onChange = openPopover();

    fireEvent.click(await screen.findByTitle('Pick colour from screen'));

    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith('#654321'));
  });

  // -- N6: arrow-key access to the two pointer-only sliders -----------------

  it('ArrowRight on the saturation/brightness square steps saturation up by one (N6)', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Saturation and brightness' }), {
      key: 'ArrowRight',
    });

    expect(onChange).toHaveBeenCalledWith(hsvToHex({ h: 0, s: 100, v: 100 }));
  });

  it('ArrowDown on the saturation/brightness square steps brightness down by one (N6)', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Saturation and brightness' }), {
      key: 'ArrowDown',
    });

    expect(onChange).toHaveBeenCalledWith(hsvToHex({ h: 0, s: 100, v: 99 }));
  });

  it('Shift steps the saturation/brightness square by ten (N6)', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Saturation and brightness' }), {
      key: 'ArrowDown',
      shiftKey: true,
    });

    expect(onChange).toHaveBeenCalledWith(hsvToHex({ h: 0, s: 100, v: 90 }));
  });

  it('ArrowLeft on the hue slider steps hue down by one (N6)', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Hue' }), { key: 'ArrowLeft' });

    // Red is hue 0 - clamped at the bottom, so it stays 0 (still a real commit).
    expect(onChange).toHaveBeenCalledWith(hsvToHex({ h: 0, s: 100, v: 100 }));
  });

  it('ArrowRight on the hue slider steps hue up by one (N6)', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Hue' }), { key: 'ArrowRight' });

    expect(onChange).toHaveBeenCalledWith(hsvToHex({ h: 1, s: 100, v: 100 }));
  });

  it('an unrelated key on either slider does nothing', () => {
    const onChange = openPopover('#ff0000');

    fireEvent.keyDown(screen.getByRole('slider', { name: 'Hue' }), { key: 'Tab' });
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Saturation and brightness' }), {
      key: 'Tab',
    });

    expect(onChange).not.toHaveBeenCalled();
  });

  // -- N3: a cancelled pointer still detaches and commits -------------------

  it('a pointercancel mid-drag on the SV square detaches its listeners and commits the last live value', () => {
    const onChange = openPopover('#000000');
    const square = screen.getByRole('slider', { name: 'Saturation and brightness' });
    square.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 100, height: 100 }) as DOMRect;
    square.setPointerCapture = vi.fn();
    square.releasePointerCapture = vi.fn();

    fireEvent.pointerDown(square, { pointerId: 1, clientX: 50, clientY: 50 });
    fireEvent(
      square,
      new PointerEvent('pointermove', { pointerId: 1, clientX: 80, clientY: 20 }),
    );
    fireEvent(square, new PointerEvent('pointercancel', { pointerId: 1 }));

    // Committed once, off the pointercancel - the drag never got a pointerup.
    expect(onChange).toHaveBeenCalledTimes(1);

    // The cancel already detached the move/up listeners - a stray pointerup
    // arriving afterwards (some browsers fire both) does not commit again.
    fireEvent(square, new PointerEvent('pointerup', { pointerId: 1 }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

/**
 * PRICETAG-COMBO-FORMAT AC-3: the colour popover is ONE control, `components/common/ColorPicker.tsx`.
 * The tag designer imports it from there and the old path no longer exists.
 */
describe('one colour control (AC-3)', () => {
  const root = path.resolve(__dirname, '..', '..');
  const skip = new Set(['node_modules', '.next', 'e2e', 'coverage', '.git']);

  function sources(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      if (skip.has(entry.name)) return [];
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return sources(full);
      return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
    });
  }

  it('AC-3: the old file at the tag-templates path is gone', () => {
    const old = path.join(root, 'app/(protected)/dealer-kit/tag-templates/components/ColorPicker.tsx');
    expect(existsSync(old)).toBe(false);
  });

  it('AC-3: no file imports the tag-templates ColorPicker', () => {
    const offenders = sources(root)
      .filter((file) => !file.endsWith('ColorPicker.test.tsx'))
      .filter((file) => {
        const text = readFileSync(file, 'utf8');
        if (/tag-templates\/components\/ColorPicker/.test(text)) return true;
        // The designer's own components used the sibling import `./ColorPicker`.
        return file.includes(`${path.sep}tag-templates${path.sep}components${path.sep}`) &&
          /from ['"]\.\/ColorPicker['"]/.test(text);
      })
      .map((file) => path.relative(root, file));
    expect(offenders).toEqual([]);
  });

  it('AC-3: the designer inspector takes the shared component', () => {
    const inspector = readFileSync(
      path.join(root, 'app/(protected)/dealer-kit/tag-templates/components/InspectorPanel.tsx'),
      'utf8',
    );
    expect(inspector).toMatch(/from '@\/components\/common\/ColorPicker'/);
  });
});
