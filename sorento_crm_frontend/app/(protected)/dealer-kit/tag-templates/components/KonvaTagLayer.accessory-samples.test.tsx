/**
 * SPEC-SHEET-PARITY-B2 crew pass: with nothing previewed, an Accessories box outside "Edit card"
 * drew blank white cards (two bare name + spec samples that the designed card has no field for).
 * It must draw the same full design samples "Edit card" shows: picture area, the bold BRAND CODE
 * line and the description.
 */
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div data-konva={name} data-text={String(props.text ?? '')}>
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
    Circle: passthrough('circle'),
  };
});

import { accessoryDesignSamples, cardElementsFor, defaultSpecSheetCard } from '@/lib/dealer-kit/accessory-card';
import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { KonvaTagLayer } from './KonvaTagLayer';

class StubImage {
  width = 100;
  height = 100;
  onload: (() => void) | null = null;
  set src(_v: string) {
    Promise.resolve().then(() => this.onload?.());
  }
}

beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

function specSheetBox(): TagLayer {
  return {
    id: 'acc',
    type: 'accessories',
    x_mm: 0,
    y_mm: 0,
    width_mm: 200,
    height_mm: 80,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultAccessoriesProps(), card: defaultSpecSheetCard() },
  } as TagLayer;
}

async function drawTexts(l: TagLayer): Promise<string[]> {
  // No `accessories` in the display: nothing is previewed (the template editor's empty preview).
  const { container } = render(<KonvaTagLayer layer={l} scale={4} display={{}} />);
  await act(async () => {
    await Promise.resolve();
  });
  return [...container.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text') ?? '');
}

describe('an Accessories box with nothing previewed (not under Edit card)', () => {
  it('draws the full design samples: the BRAND CODE line and the description on every card', async () => {
    const texts = await drawTexts(specSheetBox());
    const expected = cardElementsFor(accessoryDesignSamples()[0], defaultSpecSheetCard())
      .filter((e) => e.kind === 'text')
      .map((e) => (e as { text: string }).text);
    expect(expected[0]).toMatch(/BRAND CODE/);
    for (const text of expected) {
      expect(texts.filter((t) => t === text), text).toHaveLength(accessoryDesignSamples().length);
    }
  });
});
