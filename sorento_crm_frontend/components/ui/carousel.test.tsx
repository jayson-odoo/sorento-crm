/**
 * M2-02 - arrow keys jump, buttons and drag still animate.
 *
 * The carousel's own `onKeyDownCapture` called the animated `scrollNext()` /
 * `scrollPrev()`, so any carousel driven from the keyboard eased between
 * slides - and a keyboard-initiated action never animates (DESIGN-LANGUAGE
 * section 3, frequency gate). Embla's optional `jump` argument is the same one
 * `AttachmentPreviewModal` already passes on its own arrow-key handler.
 *
 * A real Embla engine needs layout APIs jsdom does not have, so the hook is
 * stubbed and the assertion is on the argument the carousel hands it.
 *
 * The fix round adds the modal-shaped case: `AttachmentPreviewModal` puts its
 * own bubble-phase `onKeyDown` on the dialog panel and the Carousel inside it,
 * so a key pressed while focus sits in the carousel region (which is where it
 * lands after clicking the next/previous buttons, since those render inside
 * that region) reached BOTH handlers and moved two slides on one press.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const fakeApi = vi.hoisted(() => ({
  scrollNext: vi.fn(),
  scrollPrev: vi.fn(),
  canScrollNext: vi.fn(() => true),
  canScrollPrev: vi.fn(() => true),
  on: vi.fn(),
  off: vi.fn(),
}));

vi.mock('embla-carousel-react', () => ({
  default: () => [() => {}, fakeApi],
}));

import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from './carousel';

beforeEach(() => {
  fakeApi.scrollNext.mockClear();
  fakeApi.scrollPrev.mockClear();
});

function Harness() {
  return (
    <Carousel>
      <CarouselContent>
        <CarouselItem>One</CarouselItem>
        <CarouselItem>Two</CarouselItem>
      </CarouselContent>
      <CarouselPrevious />
      <CarouselNext />
    </Carousel>
  );
}

describe('Carousel arrow keys jump (M2-02)', () => {
  it('ArrowRight scrolls to the next slide with no animation', () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole('region'), { key: 'ArrowRight' });

    expect(fakeApi.scrollNext).toHaveBeenCalledWith(true);
  });

  it('ArrowLeft scrolls to the previous slide with no animation', () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole('region'), { key: 'ArrowLeft' });

    expect(fakeApi.scrollPrev).toHaveBeenCalledWith(true);
  });

  it('the next/previous buttons still animate', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'Next slide' }));

    expect(fakeApi.scrollNext).toHaveBeenCalledWith();
  });
});

/**
 * The shape AttachmentPreviewModal ships: a bubble-phase handler on the panel
 * around a Carousel whose region carries the capture handler. Both call the
 * same api, so a press that reaches both is two slides.
 */
function ModalShapedHarness() {
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowRight') fakeApi.scrollNext(true);
    else if (event.key === 'ArrowLeft') fakeApi.scrollPrev(true);
  };

  return (
    <div onKeyDown={onKeyDown} role="dialog">
      <Harness />
    </div>
  );
}

describe('Carousel arrow keys do not double-fire (M2-02 fix round)', () => {
  it('ArrowRight from inside the region moves exactly one slide', () => {
    render(<ModalShapedHarness />);

    fireEvent.keyDown(screen.getByRole('button', { name: 'Next slide' }), { key: 'ArrowRight' });

    expect(fakeApi.scrollNext).toHaveBeenCalledTimes(1);
    expect(fakeApi.scrollNext).toHaveBeenCalledWith(true);
  });

  it('ArrowLeft from inside the region moves exactly one slide', () => {
    render(<ModalShapedHarness />);

    fireEvent.keyDown(screen.getByRole('button', { name: 'Previous slide' }), { key: 'ArrowLeft' });

    expect(fakeApi.scrollPrev).toHaveBeenCalledTimes(1);
    expect(fakeApi.scrollPrev).toHaveBeenCalledWith(true);
  });

  it('a key the carousel ignores still reaches the panel handler', () => {
    const onKeyDown = vi.fn();
    render(
      <div onKeyDown={onKeyDown} role="dialog">
        <Harness />
      </div>,
    );

    fireEvent.keyDown(screen.getByRole('region'), { key: 'Escape' });

    expect(onKeyDown).toHaveBeenCalledTimes(1);
  });

  it('an arrow pressed outside the region is left to the panel handler', () => {
    render(
      <ModalShapedHarness />,
    );

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowRight' });

    expect(fakeApi.scrollNext).toHaveBeenCalledTimes(1);
    expect(fakeApi.scrollNext).toHaveBeenCalledWith(true);
  });
});
