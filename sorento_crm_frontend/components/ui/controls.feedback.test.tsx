/**
 * S1-09, S1-10, S1-12 - the controls answer on the way down, and a thumb can hit them.
 *
 * Every control in the product answered on RELEASE: nothing moved between
 * pointer-down and pointer-up, so a tap on a slow screen read as a control that
 * had not registered. And a 20px checkbox is a 20px target on a phone, well
 * under the 44px a thumb needs.
 *
 * jsdom has no pointer and no layout, so what is pinned here is that every
 * control carries the shared rule rather than each file inventing its own.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Button } from './button';
import { Checkbox } from './checkbox';
import { Switch, SwitchWrapper } from './switch';
import { RadioGroup, RadioGroupItem } from './radio-group';
import { Toggle } from './toggle';
import { Slider, SliderThumb } from './slider';
import { Tabs, TabsList, TabsTrigger } from './tabs';

function classOf(el: Element | null) {
  return el?.getAttribute('class') ?? '';
}

describe('Pressed states (S1-09)', () => {
  const pressable: Array<[string, () => React.ReactElement, string]> = [
    ['button', () => <Button>Save</Button>, '[data-slot="button"]'],
    ['checkbox', () => <Checkbox />, '[data-slot="checkbox"]'],
    [
      'switch',
      () => (
        <SwitchWrapper>
          <Switch />
        </SwitchWrapper>
      ),
      '[data-slot="switch"]',
    ],
    [
      'radio',
      () => (
        <RadioGroup>
          <RadioGroupItem value="a" />
        </RadioGroup>
      ),
      '[data-slot="radio-group-item"]',
    ],
    ['toggle', () => <Toggle>B</Toggle>, '[data-slot="toggle"]'],
    [
      'tab trigger',
      () => (
        <Tabs defaultValue="a">
          <TabsList>
            <TabsTrigger value="a">One</TabsTrigger>
          </TabsList>
        </Tabs>
      ),
      '[data-slot="tabs-trigger"]',
    ],
    [
      'slider thumb',
      () => (
        <Slider defaultValue={[10]}>
          <SliderThumb />
        </Slider>
      ),
      '[data-slot="slider-thumb"]',
    ],
  ];

  for (const [name, renderControl, selector] of pressable) {
    it(`S1-09: the ${name} shows a pressed state before release`, () => {
      render(renderControl());
      expect(classOf(document.querySelector(selector))).toContain('active:scale-[0.97]');
    });

    it(`S1-09: the ${name} suppresses it under prefers-reduced-motion`, () => {
      render(renderControl());
      expect(classOf(document.querySelector(selector))).toContain('motion-reduce:active:scale-100');
    });

    it(`M1-01: the ${name} runs the press on duration-fast / ease-standard`, () => {
      render(renderControl());
      const className = classOf(document.querySelector(selector));
      expect(className).toContain('duration-(--duration-fast)');
      expect(className).toContain('ease-(--ease-standard)');
    });
  }
});

describe('Touch targets (S1-10)', () => {
  const touchable: Array<[string, () => React.ReactElement, string]> = [
    ['button', () => <Button>Save</Button>, '[data-slot="button"]'],
    ['checkbox', () => <Checkbox />, '[data-slot="checkbox"]'],
    [
      'switch',
      () => (
        <SwitchWrapper>
          <Switch />
        </SwitchWrapper>
      ),
      '[data-slot="switch"]',
    ],
    [
      'radio',
      () => (
        <RadioGroup>
          <RadioGroupItem value="a" />
        </RadioGroup>
      ),
      '[data-slot="radio-group-item"]',
    ],
  ];

  for (const [name, renderControl, selector] of touchable) {
    it(`S1-10: the ${name} is at least 44x44 to a thumb, without growing on screen`, () => {
      render(renderControl());
      const className = classOf(document.querySelector(selector));

      expect(className).toContain('pointer-coarse:after:min-h-11');
      expect(className).toContain('pointer-coarse:after:min-w-11');
      // The target is a pseudo-element, so the control's own size is untouched.
      expect(className).toContain('pointer-coarse:after:absolute');
      expect(className).toContain('relative');
    });
  }

  it('S1-10: a size prop still decides what is drawn', () => {
    render(<Checkbox size="sm" />);
    expect(screen.getByRole('checkbox')).toHaveClass('size-4.5');
  });

  it('S1-10: an icon button gets the target too', () => {
    render(<Button size="icon" aria-label="Refresh" />);
    expect(classOf(screen.getByRole('button'))).toContain('pointer-coarse:after:min-h-11');
  });

  it('S1-10: a small button in a dense cluster does NOT, or its target eats its neighbour', () => {
    render(<Button size="sm">Page 3</Button>);
    // The pagination strip is 28px buttons 4px apart: a 44px target overflows
    // its own box and a thumb aimed at page 3 lands on page 4. Their spacing is
    // S4 layout work; until then the smaller target is the honest one.
    expect(classOf(screen.getByRole('button'))).not.toContain('pointer-coarse:after:min-h-11');
  });
});

describe('Toaster (S1-12)', () => {
  it('S1-12: every toast has a close button', async () => {
    const received: Record<string, unknown>[] = [];
    vi.doMock('sonner', () => ({
      Toaster: (props: Record<string, unknown>) => {
        received.push(props);
        return null;
      },
    }));
    vi.doMock('next-themes', () => ({ useTheme: () => ({ theme: 'light' }) }));

    const { Toaster } = await import('./sonner');
    render(<Toaster />);

    expect(received[0]?.closeButton).toBe(true);
  });
});
