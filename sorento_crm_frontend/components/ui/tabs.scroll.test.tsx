/**
 * A mouse user has no way to move an overflowing `TabsList` (prod defect, 5
 * Sep): trackpad and shift+wheel work, but a plain vertical wheel, a mouse
 * with no horizontal axis, and a keyboard user tabbing through a long strip
 * do not - the strip just sits scrolled wherever it last was, with a tab
 * clipped mid-word ("Complaints" read "aints") and nothing on screen a mouse
 * can act on.
 *
 * This is the primitive's fix, not a thirteenth per-screen workaround
 * (`tabs.overflow.inventory.test.ts` guards against a fourteenth): a wheel
 * over the list scrolls it, chevrons appear at whichever edge still has more
 * to show, and the active/focused tab is kept in view.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs';

function setMetrics(el: HTMLElement, metrics: { scrollWidth: number; clientWidth: number; scrollLeft: number }) {
  Object.defineProperty(el, 'scrollWidth', { value: metrics.scrollWidth, configurable: true });
  Object.defineProperty(el, 'clientWidth', { value: metrics.clientWidth, configurable: true });
  Object.defineProperty(el, 'scrollLeft', { value: metrics.scrollLeft, configurable: true, writable: true });
}

function Harness({ value, onValueChange }: { value?: string; onValueChange?: (value: string) => void }) {
  return (
    <Tabs value={value} defaultValue={value ? undefined : 'a'} onValueChange={onValueChange}>
      <TabsList data-testid="list">
        <TabsTrigger value="a">Overview</TabsTrigger>
        <TabsTrigger value="b">History</TabsTrigger>
        <TabsTrigger value="c">Complaints</TabsTrigger>
      </TabsList>
      <TabsContent value="a">A</TabsContent>
      <TabsContent value="b">B</TabsContent>
      <TabsContent value="c">C</TabsContent>
    </Tabs>
  );
}

beforeEach(() => {
  Element.prototype.scrollBy = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
});

describe('TabsList scroll affordances (prod defect, 5 Sep)', () => {
  it('marks both edges independently and masks accordingly', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');

    // jsdom has no layout: fits by default, no fade either side.
    expect(list).toHaveAttribute('data-fade-start', 'false');
    expect(list).toHaveAttribute('data-fade-end', 'false');

    // Overflowing, still at the start: only the end fades.
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });
    expect(list).toHaveAttribute('data-fade-start', 'false');
    expect(list).toHaveAttribute('data-fade-end', 'true');
    expect(list.className).toContain(
      'data-[fade-end=true]:data-[fade-start=false]:[mask-image:linear-gradient(to_right,black_calc(100%-24px),transparent)]',
    );

    // Scrolled to the middle: both edges fade, one mask, two stops.
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 300 });
    act(() => {
      fireEvent.scroll(list);
    });
    expect(list).toHaveAttribute('data-fade-start', 'true');
    expect(list).toHaveAttribute('data-fade-end', 'true');
    expect(list.className).toContain(
      'data-[fade-start=true]:data-[fade-end=true]:[mask-image:linear-gradient(to_right,transparent,black_24px,black_calc(100%-24px),transparent)]',
    );

    // Scrolled to the end: only the start fades.
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 600 });
    act(() => {
      fireEvent.scroll(list);
    });
    expect(list).toHaveAttribute('data-fade-start', 'true');
    expect(list).toHaveAttribute('data-fade-end', 'false');
    expect(list.className).toContain(
      'data-[fade-start=true]:data-[fade-end=false]:[mask-image:linear-gradient(to_right,transparent,black_24px)]',
    );
  });

  it('a plain vertical wheel scrolls an overflowing list and prevents default', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    const event = new WheelEvent('wheel', { deltaY: 80, deltaX: 0, cancelable: true, bubbles: true });
    act(() => {
      list.dispatchEvent(event);
    });

    expect(list.scrollLeft).toBe(80);
    expect(event.defaultPrevented).toBe(true);
  });

  it('a line-based wheel (deltaMode 1) still moves the strip a usable distance', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    // Firefox / some Windows wheel settings report a handful of lines
    // rather than pixels; deltaY: 5 unscaled would barely move the strip.
    const event = new WheelEvent('wheel', { deltaY: 5, deltaX: 0, deltaMode: 1, cancelable: true, bubbles: true });
    act(() => {
      list.dispatchEvent(event);
    });

    expect(list.scrollLeft).toBe(80);
    expect(event.defaultPrevented).toBe(true);
  });

  it('does nothing on a list that fits', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    // jsdom: fits by default (scrollWidth === clientWidth === 0).

    const event = new WheelEvent('wheel', { deltaY: 80, deltaX: 0, cancelable: true, bubbles: true });
    act(() => {
      list.dispatchEvent(event);
    });

    expect(list.scrollLeft).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });

  it('leaves an already-horizontal gesture alone (trackpad, shift+wheel)', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    const event = new WheelEvent('wheel', { deltaY: 10, deltaX: 80, cancelable: true, bubbles: true });
    act(() => {
      list.dispatchEvent(event);
    });

    expect(list.scrollLeft).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });

  it('shows the right chevron only at the start, both mid-way, left only at the end', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });
    expect(screen.queryByRole('button', { name: 'Scroll tabs left' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scroll tabs right' })).toBeInTheDocument();

    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 300 });
    act(() => {
      fireEvent.scroll(list);
    });
    expect(screen.getByRole('button', { name: 'Scroll tabs left' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scroll tabs right' })).toBeInTheDocument();

    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 600 });
    act(() => {
      fireEvent.scroll(list);
    });
    expect(screen.getByRole('button', { name: 'Scroll tabs left' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Scroll tabs right' })).not.toBeInTheDocument();
  });

  it('S1-10 (44px hit area, 5 Sep evidence check 5b): a chevron carries a 44px interactive box beyond its 28px circle', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    const chevron = screen.getByRole('button', { name: 'Scroll tabs right' });
    // The visible circle itself is untouched...
    expect(chevron.className).toContain('size-7');
    // ...an invisible `::before` widens only the interactive box (-inset-2 =
    // 8px each side, 28 + 8 + 8 = 44).
    expect(chevron.className).toContain('before:absolute');
    expect(chevron.className).toContain('before:-inset-2');
    expect(chevron.className).toContain("before:content-['']");
  });

  it('a chevron click scrolls by 80% of the visible width, in its own direction', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');
    setMetrics(list, { scrollWidth: 900, clientWidth: 300, scrollLeft: 300 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    fireEvent.click(screen.getByRole('button', { name: 'Scroll tabs right' }));
    expect(list.scrollBy).toHaveBeenCalledWith(expect.objectContaining({ left: 240 }));

    fireEvent.click(screen.getByRole('button', { name: 'Scroll tabs left' }));
    expect(list.scrollBy).toHaveBeenLastCalledWith(expect.objectContaining({ left: -240 }));
  });

  it('scrolls the active tab into view on mount', () => {
    render(<Harness value="b" onValueChange={() => {}} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    const calledOn = (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.instances.at(-1);
    expect(calledOn).toHaveTextContent('History');
  });

  it('scrolls the newly active tab into view when the value changes', async () => {
    const { rerender } = render(<Harness value="a" onValueChange={() => {}} />);
    (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mockClear();

    rerender(<Harness value="c" onValueChange={() => {}} />);

    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    const calledOn = (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.instances.at(-1);
    expect(calledOn).toHaveTextContent('Complaints');
  });

  it('keeps a focused trigger visible', () => {
    render(<Harness />);
    (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mockClear();

    screen.getByRole('tab', { name: 'History' }).focus();

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });
});
