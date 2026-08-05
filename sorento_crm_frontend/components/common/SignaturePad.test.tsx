import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * The place lookup is one small PUBLIC call to the backend, against the same table the PDF
 * renders from. Stubbed here because what these specs are about is the pad's behaviour around it:
 * ask only with a fix, never block on the answer, never keep it against different coordinates.
 */
const getNearestPlace = vi.fn();
vi.mock('@/services/geoPlaceService', () => ({
  getNearestPlace: (...args: unknown[]) => getNearestPlace(...args),
}));

import { SignaturePad, type SignatureValue } from './SignaturePad';

const STUB_PNG = 'data:image/png;base64,STUB';

/**
 * jsdom implements <canvas> as an element but ships NO 2d context (that needs the optional
 * `canvas` native module), so `getContext('2d')` returns null and `toDataURL` throws. The pad
 * would then be untestable, and skipping the tests would leave the one component whose whole
 * job is producing a PNG uncovered. So stub the two members the pad touches: what is under
 * test here is the state machine (which mode, when the output is produced, what metadata rides
 * along), not Skia's rasteriser. Pixel fidelity is a browser concern, checked in Playwright.
 */
function makeStubContext(): CanvasRenderingContext2D {
  const noop = () => {};
  const stub = {
    setTransform: noop,
    fillRect: noop,
    clearRect: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    stroke: noop,
    fillText: noop,
    // Narrow enough that the fit-to-width loop in the pad actually runs a few passes.
    measureText: (text: string) => ({ width: text.length * 24 }),
    save: noop,
    restore: noop,
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
    font: '',
    textAlign: 'center',
    textBaseline: 'middle',
  };
  // Deliberate cast: only the members the pad calls are implemented, and listing the other
  // ~90 members of the real interface as no-ops would say nothing.
  return stub as unknown as CanvasRenderingContext2D;
}

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () => makeStubContext(),
  ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.toDataURL = vi.fn(() => STUB_PNG);
});

/** Radix activates a tab on mousedown, not click, so a plain click does not switch modes. */
function switchTo(name: 'Draw' | 'Type' | 'Initials') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0 });
}

const canvas = () => screen.getByTestId('signature-pad-canvas');
/**
 * By role, not by label text: Radix labels each tab PANEL with its trigger, so
 * `getByLabelText('Initials')` matches both the panel and the field inside it.
 */
const nameField = () => screen.getByRole('textbox', { name: 'Full name' });
const initialsField = () => screen.getByRole('textbox', { name: 'Initials' });
const applyButton = () => screen.getByRole('button', { name: 'Apply signature' });
const clearButton = () => screen.getByRole('button', { name: /clear/i });

function drawAStroke() {
  const target = canvas();
  fireEvent.pointerDown(target, { pointerId: 1, clientX: 20, clientY: 30 });
  fireEvent.pointerMove(target, { pointerId: 1, clientX: 60, clientY: 55 });
  fireEvent.pointerMove(target, { pointerId: 1, clientX: 90, clientY: 40 });
  fireEvent.pointerUp(target, { pointerId: 1, clientX: 90, clientY: 40 });
}

function stubGeolocation(behaviour: 'granted' | 'denied' | 'absent') {
  if (behaviour === 'absent') {
    Object.defineProperty(navigator, 'geolocation', { value: undefined, configurable: true });
    return;
  }
  const getCurrentPosition = vi.fn(
    (success: PositionCallback, failure?: PositionErrorCallback | null) => {
      if (behaviour === 'granted') {
        success({
          coords: { latitude: 3.13901, longitude: 101.68685 },
          timestamp: Date.now(),
        } as GeolocationPosition);
      } else {
        // PERMISSION_DENIED. The pad must carry on and report null coordinates.
        failure?.({ code: 1, message: 'denied' } as GeolocationPositionError);
      }
    },
  );
  Object.defineProperty(navigator, 'geolocation', {
    value: { getCurrentPosition },
    configurable: true,
  });
}

beforeEach(() => {
  stubGeolocation('absent');
  getNearestPlace.mockReset();
  // Never resolves by default, so every existing spec sees exactly what it saw before: the
  // coordinates alone, with the place name still outstanding.
  getNearestPlace.mockReturnValue(new Promise(() => {}));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('SignaturePad modes', () => {
  it('opens on Draw and moves between all three modes', () => {
    render(<SignaturePad onChange={vi.fn()} />);

    expect(screen.getByRole('tab', { name: 'Draw' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('textbox', { name: 'Full name' })).not.toBeInTheDocument();

    switchTo('Type');
    expect(screen.getByRole('tab', { name: 'Type' })).toHaveAttribute('aria-selected', 'true');
    expect(nameField()).toBeInTheDocument();

    switchTo('Initials');
    expect(screen.getByRole('tab', { name: 'Initials' })).toHaveAttribute('aria-selected', 'true');
    expect(initialsField()).toBeInTheDocument();

    switchTo('Draw');
    expect(screen.getByRole('tab', { name: 'Draw' })).toHaveAttribute('aria-selected', 'true');
  });

  it('turns a typed name into one PNG', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    switchTo('Type');
    expect(applyButton()).toBeDisabled();

    fireEvent.change(nameField(), { target: { value: 'Ahmad Faizal' } });
    expect(applyButton()).toBeEnabled();

    fireEvent.click(applyButton());

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toMatchObject({
      dataUrl: STUB_PNG,
      mode: 'type',
      typedText: 'Ahmad Faizal',
      gpsLat: null,
      gpsLng: null,
    });
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledWith('image/png');
  });

  it('derives initials from the name and lets the signer edit them', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} typedNameDefault="Ahmad Faizal Hassan" />);

    switchTo('Initials');
    expect(initialsField()).toHaveValue('A.F.H.');

    fireEvent.change(initialsField(), { target: { value: 'AFH' } });
    fireEvent.click(applyButton());

    expect(onChange.mock.calls[0][0]).toMatchObject({
      dataUrl: STUB_PNG,
      mode: 'initials',
      typedText: 'AFH',
    });
  });

  it('turns a drawn stroke into the same PNG shape', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    expect(applyButton()).toBeDisabled();
    drawAStroke();
    expect(applyButton()).toBeEnabled();

    fireEvent.click(applyButton());

    expect(onChange.mock.calls[0][0]).toMatchObject({
      dataUrl: STUB_PNG,
      mode: 'draw',
      typedText: null,
    });
  });
});

describe('SignaturePad initials follow the name', () => {
  it('fills the Initials tab from a name that arrives after the pad mounted', () => {
    // The counter-sign page asks for the name in a field ABOVE the pad and feeds it down as
    // `typedNameDefault`, so the name almost never exists at mount. Seeding once left the
    // signer looking at an empty Initials tab while their name sat on screen.
    const { rerender } = render(<SignaturePad onChange={vi.fn()} typedNameDefault="" />);

    switchTo('Initials');
    expect(initialsField()).toHaveValue('');

    rerender(<SignaturePad onChange={vi.fn()} typedNameDefault="Jayson" />);

    expect(initialsField()).toHaveValue('J.');
    switchTo('Type');
    expect(nameField()).toHaveValue('Jayson');
  });

  it('never overwrites initials the signer typed themselves', () => {
    const { rerender } = render(<SignaturePad onChange={vi.fn()} typedNameDefault="Jayson" />);

    switchTo('Initials');
    expect(initialsField()).toHaveValue('J.');

    fireEvent.change(initialsField(), { target: { value: 'JCT' } });
    // The name keeps changing underneath. Auto-fill is a convenience, not a correction: once the
    // signer has typed their own initials they own the field.
    rerender(<SignaturePad onChange={vi.fn()} typedNameDefault="Jayson Chan" />);

    expect(initialsField()).toHaveValue('JCT');
  });

  it('leaves a name the signer typed in the pad alone when the caller sends another', () => {
    const { rerender } = render(<SignaturePad onChange={vi.fn()} typedNameDefault="Kelly" />);

    switchTo('Type');
    fireEvent.change(nameField(), { target: { value: 'Kelly Tan a/p Lim' } });
    rerender(<SignaturePad onChange={vi.fn()} typedNameDefault="Kelly Tan" />);

    expect(nameField()).toHaveValue('Kelly Tan a/p Lim');
  });

  it.each([
    ['Jayson', 'J.'],
    ['  Ahmad   Faizal  ', 'A.F.'],
    ['Ahmad Faizal bin Hassan Ismail', 'A.F.B.'],
    ['tan wei ming', 'T.W.M.'],
    ['陈大文', '陈.'],
    ['نور هدى', 'ن.ه.'],
    ['   ', ''],
  ])('derives initials from %s', (name, expected) => {
    render(<SignaturePad onChange={vi.fn()} typedNameDefault={name} />);

    switchTo('Initials');
    expect(initialsField()).toHaveValue(expected);
  });
});

describe('SignaturePad commit discipline', () => {
  it('stays silent until the signer presses Apply', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    drawAStroke();
    switchTo('Type');
    fireEvent.change(nameField(), { target: { value: 'Siti' } });

    expect(onChange).not.toHaveBeenCalled();

    fireEvent.click(applyButton());

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('empties a drawing on Clear without committing anything', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    drawAStroke();
    expect(applyButton()).toBeEnabled();

    fireEvent.click(clearButton());

    expect(applyButton()).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('empties a typed name on Clear', () => {
    render(<SignaturePad onChange={vi.fn()} typedNameDefault="Ahmad Faizal" />);

    switchTo('Type');
    expect(nameField()).toHaveValue('Ahmad Faizal');

    fireEvent.click(clearButton());

    expect(nameField()).toHaveValue('');
    expect(applyButton()).toBeDisabled();
  });

  it('drops an already-applied signature when the pad is cleared', () => {
    const onChange = vi.fn();
    const applied: SignatureValue = {
      dataUrl: STUB_PNG,
      mode: 'draw',
      typedText: null,
      signedAt: '2026-08-04T02:15:00Z',
      gpsLat: null,
      gpsLng: null,
    };
    render(<SignaturePad onChange={onChange} value={applied} />);

    fireEvent.click(clearButton());

    // A blank pad beside a committed image would misstate what is signed.
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('offers nothing to press while disabled', () => {
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} disabled />);

    drawAStroke();

    expect(applyButton()).toBeDisabled();
    expect(clearButton()).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('SignaturePad metadata', () => {
  it('reports the coordinates the browser granted', () => {
    stubGeolocation('granted');
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    drawAStroke();
    fireEvent.click(applyButton());

    expect(onChange.mock.calls[0][0]).toMatchObject({ gpsLat: 3.13901, gpsLng: 101.68685 });
    expect(screen.getByText('3.13901, 101.68685')).toBeInTheDocument();
  });

  it('still signs, with null coordinates, when GPS is refused', () => {
    stubGeolocation('denied');
    const onChange = vi.fn();
    render(<SignaturePad onChange={onChange} />);

    drawAStroke();
    fireEvent.click(applyButton());

    const committed = onChange.mock.calls[0][0] as SignatureValue;
    expect(committed.dataUrl).toBe(STUB_PNG);
    expect(committed.gpsLat).toBeNull();
    expect(committed.gpsLng).toBeNull();
    expect(typeof committed.signedAt).toBe('string');
    // Stated as absent, not hidden.
    expect(screen.getByText('GPS location')).toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('never asks for a fix when the caller opted out', () => {
    stubGeolocation('granted');
    render(<SignaturePad onChange={vi.fn()} requestGeolocation={false} />);

    expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  });
});

/**
 * S13 - the place name WHILE capturing.
 *
 * The lookup used to be backend-only, so `near Kajang, Selangor` appeared once a signature had
 * been SAVED and the person actually signing saw bare numbers. The client read that as a service
 * nobody had switched on. The table still stays on the server - one definition, shared with the
 * PDF - and the browser asks.
 *
 * The place REPLACES the coordinates once one is known (client decision, 2026-08-05, overruling
 * the earlier "beside, never instead" reading): the numbers alone are noise to whoever reads the
 * pad, and the exact figures are still captured onto the signature record regardless of what
 * this label shows.
 */
describe('SignaturePad place name while capturing', () => {
  it('names the place once the lookup answers, without waiting for a save', async () => {
    stubGeolocation('granted');
    getNearestPlace.mockResolvedValue({
      lat: 3.13901,
      lng: 101.68685,
      coordinates: '3.13901, 101.68685',
      description: 'near Kuala Lumpur, Wilayah Persekutuan (3.13901, 101.68685)',
      place: 'Kuala Lumpur, Wilayah Persekutuan',
      place_name: 'Kuala Lumpur',
      state: 'Wilayah Persekutuan',
      distance_km: 1.2,
    });

    render(<SignaturePad onChange={vi.fn()} />);

    // The numbers first, because they are what the browser knows on its own, before the lookup
    // has answered.
    expect(screen.getByText('3.13901, 101.68685')).toBeInTheDocument();
    // Asked with the fix the browser granted, and only with it.
    expect(getNearestPlace).toHaveBeenCalledWith(3.13901, 101.68685, expect.anything());

    // Once the place resolves, it REPLACES the bare numbers on screen.
    expect(
      await screen.findByText('near Kuala Lumpur, Wilayah Persekutuan'),
    ).toBeInTheDocument();
    expect(screen.queryByText('3.13901, 101.68685')).not.toBeInTheDocument();
  });

  it('never asks without a fix', () => {
    stubGeolocation('denied');
    render(<SignaturePad onChange={vi.fn()} />);

    expect(getNearestPlace).not.toHaveBeenCalled();
    expect(screen.getByText('GPS location')).toBeInTheDocument();
  });

  it('signs on the coordinates alone when the lookup fails', async () => {
    stubGeolocation('granted');
    getNearestPlace.mockRejectedValue(new Error('offline'));
    const onChange = vi.fn();

    render(<SignaturePad onChange={onChange} />);

    drawAStroke();
    fireEvent.click(applyButton());

    // A place name is a convenience. Nothing about it may hold up somebody putting their name
    // to a document, and nothing about it reaches the record either.
    expect(onChange.mock.calls[0][0]).toMatchObject({ gpsLat: 3.13901, gpsLng: 101.68685 });
    await waitFor(() =>
      expect(screen.getByText('3.13901, 101.68685')).toBeInTheDocument(),
    );
    expect(screen.queryByText(/near/i)).toBeNull();
  });

  it('asks for no place name in read-only, where the server already answered', () => {
    render(
      <SignaturePad
        readOnly
        onChange={vi.fn()}
        value={{
          dataUrl: STUB_PNG,
          mode: 'draw',
          typedText: null,
          signedAt: '2026-08-04T02:15:00Z',
          gpsLat: 3.03927,
          gpsLng: 101.8066,
          gpsPlace: 'Kajang, Selangor',
        }}
      />,
    );

    // The stored `gps_place` is the record's own answer. Asking again could only produce a
    // second opinion about a place somebody already signed at.
    expect(getNearestPlace).not.toHaveBeenCalled();
    expect(screen.getByText('near Kajang, Selangor')).toBeInTheDocument();
    expect(screen.queryByText(/3\.03927/)).not.toBeInTheDocument();
  });
});

describe('SignaturePad read-only', () => {
  const signed: SignatureValue = {
    dataUrl: STUB_PNG,
    mode: 'draw',
    typedText: null,
    signedAt: '2026-08-04T02:15:00Z',
    gpsLat: 3.13901,
    gpsLng: 101.68685,
  };

  it('shows the signed image and its metadata with no editing controls', () => {
    render(
      <SignaturePad
        readOnly
        onChange={vi.fn()}
        value={signed}
        extraMetadata={[{ label: 'IP address', value: '203.0.113.9' }]}
      />,
    );

    expect(screen.getByRole('img', { name: /signature image/i })).toHaveAttribute('src', STUB_PNG);
    expect(screen.getByText('3.13901, 101.68685')).toBeInTheDocument();
    expect(screen.getByText('203.0.113.9')).toBeInTheDocument();
    // 10:15 am Malaysia time for the 02:15 UTC stamp above. Case-insensitive because the
    // meridiem casing Intl emits for en-GB differs between Node and browser ICU builds.
    expect(screen.getByText(/04\/08\/2026, 10:15\s?am/i)).toBeInTheDocument();

    expect(screen.queryAllByRole('tab')).toHaveLength(0);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByTestId('signature-pad-canvas')).not.toBeInTheDocument();
  });

  it('says a document is unsigned rather than rendering an empty box', () => {
    render(<SignaturePad readOnly onChange={vi.fn()} value={null} />);

    expect(screen.getByText('Not signed yet')).toBeInTheDocument();
    expect(screen.getByText('GPS location')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('names the place and drops the raw numbers once one is known', () => {
    // Bare numbers tell the reader nothing. The place replaces them (client decision,
    // 2026-08-05); the exact figures remain on the stored row, just not on this label. The
    // name is resolved by the BACKEND (one offline table, shared with the PDF) and consumed
    // here as-is.
    render(
      <SignaturePad
        readOnly
        onChange={vi.fn()}
        value={{
          ...signed,
          gpsLat: 3.03927,
          gpsLng: 101.8066,
          gpsPlace: 'Kajang, Selangor',
        }}
      />,
    );

    expect(screen.getByText('near Kajang, Selangor')).toBeInTheDocument();
    expect(screen.queryByText(/3\.03927/)).not.toBeInTheDocument();
  });

  it('falls back to the raw coordinates when nothing known is near enough to name', () => {
    render(<SignaturePad readOnly onChange={vi.fn()} value={{ ...signed, gpsPlace: null }} />);

    expect(screen.getByText('3.13901, 101.68685')).toBeInTheDocument();
    // Naming somewhere hundreds of kilometres away would be a confident lie on a signed record.
    expect(screen.queryByText(/near/i)).not.toBeInTheDocument();
  });

  it('asks for no location fix in read-only', () => {
    stubGeolocation('granted');
    render(<SignaturePad readOnly onChange={vi.fn()} value={signed} />);

    expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  });
});

describe('SignaturePad accessibility and touch', () => {
  it('labels the canvas and blocks the page from scrolling under a finger', () => {
    render(<SignaturePad onChange={vi.fn()} label="Customer signature" />);

    const target = canvas();
    expect(target).toHaveAttribute('aria-label', 'Customer signature drawing area');
    expect(target).toHaveClass('touch-none');
    // Type mode is the keyboard-reachable path to the same output.
    expect(screen.getByRole('tab', { name: 'Type' })).toBeInTheDocument();
  });
});
