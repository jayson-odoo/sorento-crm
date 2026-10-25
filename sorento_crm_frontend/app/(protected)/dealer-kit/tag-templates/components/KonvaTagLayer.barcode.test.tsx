/**
 * Barcode layer pending vs failed on the Konva editor canvas (review fix,
 * AC-S7-6).
 *
 * `useBarcodeCanvas` used to fold "still drawing" and "jsbarcode threw" into
 * the same `null`, so a value `jsbarcode` cannot encode showed the SAME
 * "Loading" text a genuinely-pending draw shows - forever, since nothing
 * re-triggers the effect on a value that never changes. This pins the two
 * apart: a thrown draw shows a distinct failure state, not "Loading".
 *
 * `jsbarcode`'s draw is synchronous, so real Konva canvas rendering is not
 * needed to observe this - `react-konva`'s primitives are stood in for by a
 * div carrying the props that matter, the same pattern
 * `TagCanvasEditor.preview.test.tsx` uses for the same reason (Konva needs a
 * real Stage/container to mount, which jsdom has no layout engine for).
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: {
      children?: React.ReactNode;
      text?: string;
      image?: { src?: string } | null;
      width?: number;
      height?: number;
      fill?: string;
    }) {
      return (
        <div
          data-konva={name}
          data-text={props.text ?? ''}
          data-src={props.image?.src ?? ''}
          data-width={props.width ?? ''}
          data-height={props.height ?? ''}
          data-fill={props.fill ?? ''}
        >
          {props.text}
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
  };
});

const jsBarcodeMock = vi.fn();
vi.mock('jsbarcode', () => ({
  default: (...args: unknown[]) => jsBarcodeMock(...args),
}));

// jsdom never decodes an image, so the loaded element is stood in for by an
// object carrying the URL it was asked to load - which is what the canvas
// hands Konva once a real browser has decoded it.
vi.mock('./useHtmlImage', () => ({
  useHtmlImage: (url: string | null | undefined) => (url ? { src: url } : null),
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { barcodeSvg, svgDataUrl } from '@/lib/dealer-kit/barcode';
import { KonvaTagLayer } from './KonvaTagLayer';

const realJsBarcode = (await vi.importActual<{ default: (...args: unknown[]) => unknown }>(
  'jsbarcode',
)).default;

function barcodeLayer(): TagLayer {
  return {
    id: 'bc1',
    type: 'barcode',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 22,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'barcode',
    text_override: null,
    props: { kind: 'barcode', show_code: true },
  } as TagLayer;
}

describe('KonvaTagLayer barcode: pending vs failed', () => {
  it('draws the bars (no "Loading" / no failure text) when jsbarcode succeeds', () => {
    jsBarcodeMock.mockImplementation(realJsBarcode);

    render(
      <KonvaTagLayer
        layer={barcodeLayer()}
        scale={3}
        display={{ text: '4006381333931', code: 'SK-1' }}
      />,
    );

    expect(screen.queryByText('Loading')).toBeNull();
    expect(screen.queryByText('cannot encode')).toBeNull();
  });

  it('shows a distinct failure state, not "Loading" forever, when jsbarcode throws', () => {
    jsBarcodeMock.mockImplementation(() => {
      throw new Error('bad value');
    });

    render(
      <KonvaTagLayer
        layer={barcodeLayer()}
        scale={3}
        display={{ text: '4006381333931', code: 'SK-1' }}
      />,
    );

    expect(screen.getByText('cannot encode')).toBeInTheDocument();
    expect(screen.queryByText('Loading')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// An empty override draws NOTHING - the "no barcode" placeholder, never the
// product value (S5, AC-S5-1). `display.text` is what `layerDisplay` would
// hand this component for an empty `text_override` (`'' ?? x` is `''`, not
// `x` - nullish coalescing never falls back to the product for an empty
// string), so passing it directly here is the same input the real host
// produces once `InspectorPanel`'s clear no longer coerces `''` to `null`.
// ---------------------------------------------------------------------------

describe('KonvaTagLayer barcode: an empty override draws no bars (S5)', () => {
  beforeEach(() => {
    jsBarcodeMock.mockClear();
  });

  it('draws the "no barcode" placeholder, not the bars, for an empty override', () => {
    jsBarcodeMock.mockImplementation(() => {});

    render(
      <KonvaTagLayer
        layer={barcodeLayer()}
        scale={3}
        display={{ text: '', code: 'SK-1' }}
      />,
    );

    expect(jsBarcodeMock).not.toHaveBeenCalled();
    expect(screen.getByText('barcode')).toBeInTheDocument();
  });

  it('never falls back to a product value that IS present in `code`', () => {
    jsBarcodeMock.mockImplementation(() => {});

    render(
      <KonvaTagLayer
        layer={barcodeLayer()}
        scale={3}
        display={{ text: '', code: 'SK-1' }}
      />,
    );

    // The code strip only ever appears alongside real bars (same branch) -
    // an empty override must not print the product's code strip either.
    expect(screen.queryByText('SK-1')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// One renderer (PRICETAG-BARCODE-MATCH): the canvas draws the SAME SVG the
// request preview and the printed PDF draw (`TagSheetRenderer`), as one image
// filling the layer box - no Konva-drawn code strip, bars or digits of its own
// that could be laid out differently from the print page's.
// ---------------------------------------------------------------------------

describe('KonvaTagLayer barcode: one renderer with the print page', () => {
  beforeEach(() => {
    jsBarcodeMock.mockImplementation(realJsBarcode);
  });

  it('draws the shared barcode SVG as one image over the whole layer box', () => {
    const { container } = render(
      <KonvaTagLayer
        layer={barcodeLayer()}
        scale={3}
        display={{ text: '4006381333931', code: 'SK-1' }}
      />,
    );

    const expected = svgDataUrl(
      barcodeSvg({
        value: '4006381333931',
        code: 'SK-1',
        showCode: true,
        widthMm: 40,
        heightMm: 22,
      })!,
    );
    const images = container.querySelectorAll('[data-konva="image"]');
    expect(images).toHaveLength(1);
    expect(images[0].getAttribute('data-src')).toBe(expected);
    expect(images[0].getAttribute('data-width')).toBe('120');
    expect(images[0].getAttribute('data-height')).toBe('66');

    // The code and digits are inside the SVG, not drawn again by Konva, and
    // there is no black header strip.
    expect(screen.queryByText('SK-1')).toBeNull();
    expect(screen.queryByText('4 006381 333931')).toBeNull();
    expect(container.querySelector('[data-konva="rect"][data-fill="#000000"]')).toBeNull();
  });

  it('passes show_code through: off draws the SVG without the code row', () => {
    const layer = barcodeLayer();
    const { container } = render(
      <KonvaTagLayer
        layer={{ ...layer, props: { kind: 'barcode', show_code: false } } as TagLayer}
        scale={3}
        display={{ text: '4006381333931', code: 'SK-1' }}
      />,
    );

    const expected = svgDataUrl(
      barcodeSvg({
        value: '4006381333931',
        code: 'SK-1',
        showCode: false,
        widthMm: 40,
        heightMm: 22,
      })!,
    );
    expect(container.querySelector('[data-konva="image"]')?.getAttribute('data-src')).toBe(
      expected,
    );
  });
});
