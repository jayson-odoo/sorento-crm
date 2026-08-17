'use client';

import * as React from 'react';
import { Eraser, PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardToolbar } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useNearestPlace } from '@/hooks/useNearestPlace';
import { cn } from '@/lib/utils';

export type SignatureMode = 'draw' | 'type' | 'initials';

/**
 * What a signature IS, once the user has committed one.
 *
 * All three capture modes end as one PNG data URI on purpose: the PDF renderer, the stored
 * attachment and the read-only render then have a single shape to handle. A "typed" signature
 * that travelled as text would need its own font handling in WeasyPrint, its own fallback when
 * the face is missing, and its own read-only renderer - three divergent paths for one field.
 */
export type SignatureValue = {
  /** `data:image/png;base64,...` - always PNG, whichever mode produced it. */
  dataUrl: string;
  mode: SignatureMode;
  /** The name or initials behind a typed signature; null for a drawn one. */
  typedText: string | null;
  /**
   * ISO 8601 UTC instant the user pressed Apply. The SERVER remains the authority for the
   * stored `signed_at` (a client clock can be wrong or lied to); this is what the browser
   * observed, and it is what the pad can render back straight away.
   */
  signedAt: string | null;
  /** Null when the browser refused, has no sensor, or answered too late. Never guessed. */
  gpsLat: number | null;
  gpsLng: number | null;
  /**
   * The nearest known town to those coordinates, e.g. `Kajang, Selangor`, as resolved BY THE
   * BACKEND (`gps_place` on every serialized signature) from one offline table it shares with the
   * PDF renderer. The browser never derives it: a second copy of that table here would drift from
   * the server's, and then the screen and the printed document would disagree about where
   * somebody signed.
   *
   * Absent on a signature the browser has only just captured - nothing is recorded yet, so there
   * is no server answer to show - and null when nothing known is close enough to name honestly.
   * Either way the coordinates are still rendered: they are the evidence, this is the convenience.
   */
  gpsPlace?: string | null;
};

export interface SignaturePadProps {
  /**
   * The committed signature. In `readOnly` this is what gets rendered; in edit mode it is
   * only used to tell the caller-owned state apart from a blank pad (the pad itself always
   * starts empty, so re-signing never inherits the previous strokes).
   */
  value?: SignatureValue | null;
  /**
   * Fires ONLY on Apply, and with null on Clear-after-Apply. Pointer movement, typing and
   * mode switches never call it: a half-drawn stroke is not a signature, and the whole point
   * of AC-H2 is that the user confirms what they are putting their name to.
   */
  onChange: (value: SignatureValue | null) => void;
  disabled?: boolean;
  /** Already signed: render the image plus its metadata, with no editing affordances. */
  readOnly?: boolean;
  /** Prefills Type mode and seeds Initials, so a known signer is never asked for their name. */
  typedNameDefault?: string;
  /** Heading on the card. */
  label?: string;
  /** Copy on the commit button. "Apply signature" unless the flow words it differently. */
  commitLabel?: string;
  /**
   * Extra metadata rows for the read-only panel, e.g. the IP address and user agent - both
   * server-observed facts the browser must not attempt to source itself. Rendered as `-`
   * when null, the ecohub rule: an absent value is stated, not hidden.
   */
  extraMetadata?: { label: string; value?: string | null }[];
  /** Set false to skip the geolocation prompt entirely (e.g. an internal desk signature). */
  requestGeolocation?: boolean;
  className?: string;
}

/**
 * Local and system faces only. A CDN webfont is not an option here: the artifact CSP blocks
 * the request, and the counter-sign page has to work for a customer on a bad site connection.
 * The list walks Windows, macOS/iOS, Android and finally the generic `cursive` keyword, so
 * every platform lands on something handwritten without a network round trip.
 */
const SCRIPT_FONT_STACK =
  '"Segoe Script", "Bradley Hand", "Snell Roundhand", "Apple Chancery", "Brush Script MT", "Lucida Handwriting", "Comic Sans MS", cursive';

/**
 * Ink and paper are literals, not theme tokens. The bytes leave the browser and get composited
 * onto a PDF page and into an <img> on other surfaces, so they cannot depend on whatever
 * `--foreground` resolved to in the tab that produced them - a signature captured in dark mode
 * would otherwise be white-on-white on the printed quotation.
 */
const INK = '#111827';
const PAPER = '#ffffff';

/** Only used before layout has measured the box (jsdom, and the first paint before mount). */
const FALLBACK_WIDTH = 320;

type Point = { x: number; y: number };

/** "Ahmad Faizal bin Hassan" -> "A.F.B." Capped at three, past which initials stop reading as initials. */
function deriveInitials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    // `Array.from` walks CODE POINTS, not UTF-16 units: `word[0]` on a name written in a script
    // outside the basic plane hands back half a surrogate pair, which renders as a replacement
    // box. `toUpperCase` is simply a no-op for scripts without case, which is the right answer.
    .map((word) => Array.from(word)[0]?.toUpperCase() ?? '')
    .filter(Boolean);
  return letters.length ? `${letters.join('.')}.` : '';
}

/**
 * `near Kajang, Selangor`, falling back to the bare coordinates only when no place is known.
 *
 * Client decision, 2026-08-05, overruling the earlier "never drop the coordinates" reading: a
 * customer or salesperson reading `3.03927, 101.80660` gets nothing readable out of it, and the
 * exact figures still exist on the row (`gps_lat`/`gps_lng`) for anyone who needs the evidence,
 * not on this label. "near", never an address: the lookup behind `place` knows towns, not
 * streets.
 */
function formatCoordinate(
  lat: number | null,
  lng: number | null,
  place?: string | null,
): string {
  if (lat == null || lng == null) return '-';
  if (place?.trim()) return `near ${place.trim()}`;
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

/** One row of the ecohub-style metadata block: the label is always there, the value may be `-`. */
function MetaRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words text-sm">{value?.trim() ? value : '-'}</p>
    </div>
  );
}

/**
 * The one signature-capture surface in the system.
 *
 * Three ways in (draw, type, initials), one PNG out. Used by the customer counter-sign page
 * and by the internal pre-issue signature, which is why it lives in `common/` and knows
 * nothing about quotations: it takes no ids, makes no API call, and hands the caller a value.
 *
 * Accessibility: the canvas carries a label but cannot be operated from a keyboard - a stroke
 * is a pointer gesture. TYPE MODE IS THE KEYBOARD-REACHABLE ALTERNATIVE, reachable from the
 * same tab list, and it produces the identical output shape. That is why the three modes are
 * peers in one control rather than "draw, with a fallback hidden somewhere".
 */
export function SignaturePad({
  value = null,
  onChange,
  disabled = false,
  readOnly = false,
  typedNameDefault = '',
  label = 'Signature',
  commitLabel = 'Apply signature',
  extraMetadata,
  requestGeolocation = true,
  className,
}: SignaturePadProps) {
  const fieldId = React.useId();
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  /**
   * Strokes are kept as points, not just as pixels, because ANY resize (rotating a phone,
   * opening a sidebar) resets the backing store and wipes the bitmap. Replaying the model is
   * also what makes Clear and mode switching free.
   */
  const strokesRef = React.useRef<Point[][]>([]);
  /** The pointer id currently drawing, so a second finger cannot start a competing stroke. */
  const activePointerRef = React.useRef<number | null>(null);

  const [mode, setMode] = React.useState<SignatureMode>('draw');
  const [hasInk, setHasInk] = React.useState(false);
  /**
   * Null means "still following `typedNameDefault`"; a string means the user typed their own.
   *
   * Seeding state once at mount was the bug the client reported: the counter-sign page asks for
   * the name in a field ABOVE the pad, so it is empty at mount and arrives keystroke by keystroke
   * afterwards, and the pad never saw any of it. Tracking the prop is the same idea the initials
   * already used, applied one level up, rather than a second mechanism bolted on beside it.
   */
  const [nameOverride, setNameOverride] = React.useState<string | null>(null);
  /** Null means "still derived from the name"; a string means the user typed their own. */
  const [initialsOverride, setInitialsOverride] = React.useState<string | null>(null);
  const [coords, setCoords] = React.useState<{ lat: number; lng: number } | null>(null);
  /**
   * The place name for the fix currently held, WHILE capturing.
   *
   * The lookup was server-only until now, so nothing was resolved until a signature had been
   * saved and the pad showed bare numbers to the person actually signing. The client read that
   * as a service nobody had switched on. It is one small public call, against the same table the
   * PDF renders from, so the screen and the printed document still cannot disagree - and it never
   * holds anything up: no answer simply means the coordinates already on screen stay.
   */
  const nearestPlace = useNearestPlace(coords);

  const name = nameOverride ?? typedNameDefault;
  const initials = initialsOverride ?? deriveInitials(name);
  const activeText = mode === 'initials' ? initials : name;
  const hasContent = mode === 'draw' ? hasInk : activeText.trim().length > 0;
  const locked = disabled || readOnly;

  /**
   * Asked for once, never waited on. AC-H4 wants GPS when the browser gives it, and a
   * permission prompt the user ignores must not hold up signing - so the answer lands in
   * state whenever it arrives and Apply stamps whatever is known at that moment.
   */
  React.useEffect(() => {
    if (locked || !requestGeolocation) return;
    const geolocation = typeof navigator === 'undefined' ? undefined : navigator.geolocation;
    if (!geolocation) return;

    let alive = true;
    geolocation.getCurrentPosition(
      (position) => {
        if (alive) setCoords({ lat: position.coords.latitude, lng: position.coords.longitude });
      },
      // A refusal is a normal answer, not an error worth showing: the record reads `-`.
      () => {},
      { timeout: 10000, maximumAge: 300000 },
    );
    return () => {
      alive = false;
    };
  }, [locked, requestGeolocation]);

  const paint = React.useCallback(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;

    const cssWidth = canvas.clientWidth || FALLBACK_WIDTH;
    const cssHeight = canvas.clientHeight || Math.round(FALLBACK_WIDTH * 0.5);
    const ratio = (typeof window === 'undefined' ? 1 : window.devicePixelRatio) || 1;

    // Backing store in device pixels, every coordinate below in CSS pixels. Without the
    // ratio the stroke is a 1x bitmap stretched over a retina screen, and it looks it.
    const targetWidth = Math.round(cssWidth * ratio);
    const targetHeight = Math.round(cssHeight * ratio);
    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth;
      canvas.height = targetHeight;
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    context.fillStyle = PAPER;
    context.fillRect(0, 0, cssWidth, cssHeight);

    if (mode === 'draw') {
      context.strokeStyle = INK;
      context.lineWidth = 2.2;
      context.lineCap = 'round';
      context.lineJoin = 'round';
      for (const stroke of strokesRef.current) {
        if (!stroke.length) continue;
        context.beginPath();
        context.moveTo(stroke[0].x, stroke[0].y);
        // A single tap is still a mark, so a one-point stroke draws a dot on itself.
        if (stroke.length === 1) context.lineTo(stroke[0].x, stroke[0].y);
        for (const point of stroke.slice(1)) context.lineTo(point.x, point.y);
        context.stroke();
      }
      return;
    }

    const text = activeText.trim();
    if (!text) return;
    context.fillStyle = INK;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    let size = Math.min(Math.round(cssHeight * 0.45), 56);
    const maxWidth = cssWidth * 0.86;
    // Shrink to fit. Bounded rather than `while`, so an odd metric cannot spin forever.
    for (let attempt = 0; attempt < 24; attempt += 1) {
      context.font = `${size}px ${SCRIPT_FONT_STACK}`;
      const measured = context.measureText(text).width;
      if (!Number.isFinite(measured) || measured <= maxWidth || size <= 14) break;
      size -= 2;
    }
    context.fillText(text, cssWidth / 2, cssHeight * 0.56);
  }, [activeText, mode]);

  React.useLayoutEffect(() => {
    if (readOnly) return;
    paint();
  }, [paint, readOnly]);

  React.useEffect(() => {
    if (readOnly) return;
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => paint());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [paint, readOnly]);

  const pointFrom = (event: React.PointerEvent<HTMLCanvasElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const drawSegment = (from: Point, to: Point) => {
    const context = canvasRef.current?.getContext('2d');
    if (!context) return;
    context.strokeStyle = INK;
    context.lineWidth = 2.2;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.stroke();
  };

  // Pointer Events only: mouse, finger and stylus arrive through this one path, so there is
  // no second set of touch handlers to keep in step with the first.
  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (locked || mode !== 'draw' || activePointerRef.current !== null) return;
    // Capture keeps the stroke alive when the pointer leaves the canvas mid-gesture, instead
    // of ending it at the edge and leaving a half signature.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    activePointerRef.current = event.pointerId;
    const point = pointFrom(event);
    strokesRef.current = [...strokesRef.current, [point]];
    setHasInk(true);
    drawSegment(point, point);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (activePointerRef.current !== event.pointerId) return;
    const stroke = strokesRef.current[strokesRef.current.length - 1];
    if (!stroke) return;
    const point = pointFrom(event);
    // Drawn incrementally rather than by repainting the whole model on every move: a repaint
    // per pointermove is what makes a finger signature feel laggy.
    drawSegment(stroke[stroke.length - 1], point);
    stroke.push(point);
  };

  const endStroke = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (activePointerRef.current !== event.pointerId) return;
    try {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    } catch {
      // A cancelled pointer (a phone call arriving mid-signature) may already be gone, and
      // browsers throw NotFoundError for releasing one. The stroke still has to end cleanly.
    }
    activePointerRef.current = null;
  };

  const clear = () => {
    strokesRef.current = [];
    activePointerRef.current = null;
    setHasInk(false);
    // An EMPTY override, not a reset to null: clearing has to leave the field empty, and a null
    // override would spring straight back to whatever name the caller is still passing down.
    if (mode === 'type') setNameOverride('');
    if (mode === 'initials') setInitialsOverride('');
    // Strokes live in a ref, so clearing a drawing changes nothing `paint` depends on and the
    // layout effect will not fire. Repaint by hand.
    paint();
    // A blank pad beside a still-committed image would be a lie about what is signed.
    if (value) onChange(null);
  };

  const commit = () => {
    const canvas = canvasRef.current;
    if (!canvas || !hasContent || locked) return;
    onChange({
      dataUrl: canvas.toDataURL('image/png'),
      mode,
      typedText: mode === 'draw' ? null : activeText.trim(),
      signedAt: new Date().toISOString(),
      gpsLat: coords?.lat ?? null,
      gpsLng: coords?.lng ?? null,
    });
  };

  const metadata = (
    <div className="grid gap-3 sm:grid-cols-2">
      <MetaRow label="Signed at" value={value?.signedAt ? formatDateTimeInMalaysia(value.signedAt) : null} />
      <MetaRow
        label="GPS location"
        value={formatCoordinate(value?.gpsLat ?? null, value?.gpsLng ?? null, value?.gpsPlace)}
      />
      {extraMetadata?.map((row) => (
        <MetaRow key={row.label} label={row.label} value={row.value} />
      ))}
    </div>
  );

  if (readOnly) {
    return (
      <Card className={cn('w-full', className)} data-testid="signature-pad-readonly">
        <CardHeader>
          <CardTitle>{label}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {value?.dataUrl ? (
            // White paper even in dark mode: this is a rendering of the signed artifact, and
            // the artifact is on white paper.
            <div
              className="flex min-h-[140px] items-center justify-center rounded-lg border border-border bg-white p-3"
              style={{ backgroundColor: PAPER }}
            >
              <img
                src={value.dataUrl}
                alt={`${label} image`}
                className="max-h-40 w-auto max-w-full"
              />
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-muted-foreground/25 px-4 py-10 text-center">
              <PenLine className="mx-auto size-5 text-muted-foreground" aria-hidden />
              <p className="mt-2 text-sm font-medium">Not signed yet</p>
            </div>
          )}
          {metadata}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('w-full', className)} data-testid="signature-pad">
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardToolbar>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled || (!hasContent && !value)}
            onClick={clear}
          >
            <Eraser className="size-3.5" aria-hidden />
            Clear
          </Button>
        </CardToolbar>
      </CardHeader>

      <CardContent className="space-y-4">
        <Tabs value={mode} onValueChange={(next) => setMode(next as SignatureMode)}>
          {/* Scrolls rather than overflowing the card at 375px, where three triggers plus the
              container padding are tight. */}
          <TabsList variant="button" size="sm" className="w-full justify-start overflow-x-auto">
            <TabsTrigger value="draw">Draw</TabsTrigger>
            <TabsTrigger value="type">Type</TabsTrigger>
            <TabsTrigger value="initials">Initials</TabsTrigger>
          </TabsList>

          <TabsContent value="draw">
            <p className="sr-only" id={`${fieldId}-draw-hint`}>
              Sign with a mouse, a finger or a stylus. To sign without pointing, use the Type tab.
            </p>
          </TabsContent>

          <TabsContent value="type" className="space-y-1.5">
            <Label htmlFor={`${fieldId}-name`}>Full name</Label>
            <Input
              id={`${fieldId}-name`}
              value={name}
              disabled={disabled}
              autoComplete="name"
              placeholder="As it should read on the document"
              // Follows the caller's name until the signer types here, and their version then
              // survives a later change to the prop rather than being silently overwritten.
              onChange={(event) => setNameOverride(event.target.value)}
            />
          </TabsContent>

          <TabsContent value="initials" className="space-y-1.5">
            <Label htmlFor={`${fieldId}-initials`}>Initials</Label>
            <Input
              id={`${fieldId}-initials`}
              value={initials}
              disabled={disabled}
              placeholder="A.F."
              // Derived from the name until the user overrides it, and their override then
              // survives a later edit to the name rather than being silently recomputed.
              onChange={(event) => setInitialsOverride(event.target.value)}
            />
          </TabsContent>
        </Tabs>

        {/* The canvas is the single output surface for all three modes, which is why it sits
            outside the tabs: one element, one toDataURL, no per-mode divergence. */}
        <canvas
          ref={canvasRef}
          data-testid="signature-pad-canvas"
          role="img"
          aria-label={`${label} drawing area`}
          aria-describedby={mode === 'draw' ? `${fieldId}-draw-hint` : undefined}
          // touch-none is load-bearing: without touch-action none, dragging a finger across
          // the pad scrolls the page instead of drawing on it.
          className={cn(
            'block h-40 w-full touch-none rounded-lg border border-border bg-white sm:h-48',
            mode === 'draw' && !disabled ? 'cursor-crosshair' : 'cursor-default',
          )}
          style={{ backgroundColor: PAPER }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endStroke}
          onPointerCancel={endStroke}
        />

        {/* The place name once it resolves, the coordinates until then, and the coordinates for
            good if the lookup fails. The browser never derives the name itself: it asks the same
            table the PDF renders from, so the two cannot describe different places. */}
        <MetaRow
          label="GPS location"
          value={
            nearestPlace
              ? `near ${nearestPlace}`
              : formatCoordinate(coords?.lat ?? null, coords?.lng ?? null)
          }
        />
      </CardContent>

      <CardFooter className="justify-end gap-2.5 py-3">
        <Button type="button" disabled={disabled || !hasContent} onClick={commit}>
          {commitLabel}
        </Button>
      </CardFooter>
    </Card>
  );
}

export default SignaturePad;
