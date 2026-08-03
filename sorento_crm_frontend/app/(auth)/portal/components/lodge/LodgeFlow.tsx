'use client';

/**
 * S3 Phase 1 - the consumer lodging a complaint. Frontend-first, against mocks.
 *
 * The journey, and the reason each step exists:
 *
 *   photos -> "Did I get this right?" -> which item -> what's wrong -> where -> done
 *
 * **Nothing is typed before the receipt is read.** The consumer photographs the receipt and
 * the fault; the system reads the shop, the date and the model. Every extracted value then
 * lands in an ORDINARY EDITABLE INPUT rather than a read-only confirmation (AC-C10a): a
 * misread shop name costs the consumer one edit instead of costing Customer Service a
 * cleanup. That single decision is what makes 68% dealer resolution acceptable rather than
 * alarming.
 *
 * **No SKU, product code, UUID or dealer picker is ever shown** (AC-C11). The item chooser
 * is tiles of Warranty Product Kinds, never 11,415 codes.
 *
 * **Nothing blocks submission** (AC-C14, AC-M38). A failed dealer match, an unreadable
 * receipt, a photo the validator dislikes, a refused location permission - each one carries
 * on and flags for CS. A consumer with a broken toilet is not the person to punish for a bad
 * OCR result.
 *
 * Phase 2 replaces `lodgeMocks` with real calls. The step machine, the copy and the states
 * are the deliverable of this phase.
 */

import { useCallback, useMemo, useState } from 'react';
import {
  ArrowLeft,
  Camera,
  Check,
  Loader2,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  MOCK_KINDS,
  mockCheckPhoto,
  mockExtract,
  mockSubmit,
  type ExtractResult,
  type LodgeResult,
  type MockScenario,
  type PhotoCheck,
} from './lodgeMocks';

type Step = 'upload' | 'confirm' | 'kind' | 'fault' | 'place' | 'done';

interface ProofPhoto {
  name: string;
  checking: boolean;
  check: PhotoCheck | null;
}

/** Pin state. Three outcomes to draw, not one (AC-M38). */
type PinState = 'none' | 'locating' | 'set' | 'denied';

const STEP_ORDER: Step[] = ['upload', 'confirm', 'kind', 'fault', 'place', 'done'];

export function LodgeFlow({ scenario = 'resolved' }: { scenario?: MockScenario }) {
  const [step, setStep] = useState<Step>('upload');
  const [busy, setBusy] = useState(false);
  const [extract, setExtract] = useState<ExtractResult | null>(null);

  // Everything extracted is held as EDITABLE form state from the moment it arrives.
  const [shopName, setShopName] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [kindCode, setKindCode] = useState<string | null>(null);
  const [fault, setFault] = useState('');
  const [photos, setPhotos] = useState<ProofPhoto[]>([]);
  const [pin, setPin] = useState<PinState>('none');
  const [address, setAddress] = useState('');
  const [result, setResult] = useState<LodgeResult | null>(null);

  const progress = useMemo(
    () => (STEP_ORDER.indexOf(step) / (STEP_ORDER.length - 1)) * 100,
    [step],
  );

  const runExtract = useCallback(async () => {
    setBusy(true);
    try {
      const data = await mockExtract(scenario);
      setExtract(data);
      // Pre-fill from extraction - but NEVER pre-fill a dealer we are not sure of. A
      // `candidate` is a suggestion for CS, not an answer to show the consumer as fact.
      setShopName(data.shop_name_raw ?? '');
      setPurchaseDate(data.purchase_date ?? '');
      setKindCode(data.lines[0]?.kind_code ?? null);
      setStep('confirm');
    } finally {
      setBusy(false);
    }
  }, [scenario]);

  const addPhoto = useCallback(async () => {
    const index = photos.length;
    setPhotos((prev) => [
      ...prev,
      { name: `photo-${index + 1}.jpg`, checking: true, check: null },
    ]);
    const check = await mockCheckPhoto(index);
    setPhotos((prev) =>
      prev.map((p, i) => (i === index ? { ...p, checking: false, check } : p)),
    );
  }, [photos.length]);

  const retakePhoto = useCallback(async (index: number) => {
    setPhotos((prev) => prev.map((p, i) => (i === index ? { ...p, checking: true, check: null } : p)));
    // A retake is a fresh shot, so it is checked afresh. Passing it deterministically here
    // keeps the prototype honest about the affordance without pretending the AI improved.
    const check = await mockCheckPhoto(index + 1);
    setPhotos((prev) => prev.map((p, i) => (i === index ? { ...p, checking: false, check } : p)));
  }, []);

  const askForLocation = useCallback(() => {
    setPin('locating');
    // Denial is a first-class outcome, not an error path: a consumer who refuses location
    // permission must still be able to lodge (AC-M38). The prototype shows both.
    window.setTimeout(() => setPin(Math.random() > 0.5 ? 'set' : 'denied'), 900);
  }, []);

  const submit = useCallback(async () => {
    setBusy(true);
    try {
      setResult(await mockSubmit());
      setStep('done');
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          {step !== 'upload' && step !== 'done' ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2"
              onClick={() => setStep(STEP_ORDER[Math.max(0, STEP_ORDER.indexOf(step) - 1)])}
            >
              <ArrowLeft className="size-4" />
            </Button>
          ) : null}
          <h1 className="min-w-0 text-lg font-semibold break-words">
            {step === 'done' ? 'All done' : 'Report a problem'}
          </h1>
        </div>
        {step !== 'done' ? (
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
        ) : null}
      </header>

      {step === 'upload' ? (
        <StepUpload busy={busy} onContinue={runExtract} />
      ) : null}

      {step === 'confirm' && extract ? (
        <StepConfirm
          extract={extract}
          shopName={shopName}
          purchaseDate={purchaseDate}
          onShopName={setShopName}
          onPurchaseDate={setPurchaseDate}
          onContinue={() => setStep('kind')}
        />
      ) : null}

      {step === 'kind' ? (
        <StepKind selected={kindCode} onSelect={setKindCode} onContinue={() => setStep('fault')} />
      ) : null}

      {step === 'fault' ? (
        <StepFault
          fault={fault}
          onFault={setFault}
          photos={photos}
          onAddPhoto={addPhoto}
          onRetake={retakePhoto}
          onContinue={() => setStep('place')}
        />
      ) : null}

      {step === 'place' ? (
        <StepPlace
          pin={pin}
          address={address}
          onAddress={setAddress}
          onLocate={askForLocation}
          busy={busy}
          onSubmit={submit}
        />
      ) : null}

      {step === 'done' && result ? <StepDone result={result} /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ step 1 */

function StepUpload({ busy, onContinue }: { busy: boolean; onContinue: () => void }) {
  const [count, setCount] = useState(0);
  return (
    <section className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Take a photo of your receipt and of the problem. We will read the rest ourselves.
      </p>
      <button
        type="button"
        onClick={() => setCount((c) => c + 1)}
        className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors hover:bg-muted/50"
      >
        <Camera className="size-8 text-muted-foreground" />
        <span className="text-sm font-medium">Add a photo</span>
        <span className="text-xs text-muted-foreground">Receipt, invoice, or the fault itself</span>
      </button>
      {count > 0 ? (
        <p className="text-sm text-muted-foreground">
          {count} photo{count === 1 ? '' : 's'} ready.
        </p>
      ) : null}
      <Button onClick={onContinue} disabled={busy || count === 0} className="h-11">
        {busy ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            Reading your receipt
          </>
        ) : (
          <>
            <Sparkles className="mr-2 size-4" />
            Continue
          </>
        )}
      </Button>
    </section>
  );
}

/* ------------------------------------------------------------------ step 2 */

function StepConfirm({
  extract,
  shopName,
  purchaseDate,
  onShopName,
  onPurchaseDate,
  onContinue,
}: {
  extract: ExtractResult;
  shopName: string;
  purchaseDate: string;
  onShopName: (v: string) => void;
  onPurchaseDate: (v: string) => void;
  onContinue: () => void;
}) {
  const line = extract.lines[0];
  // "Did we get this right?" is the wrong question when we got nothing - it asks the
  // consumer to confirm an empty sentence, which reads as a broken screen rather than an
  // honest one. Roughly a quarter of real receipts print no usable shop name, so this is
  // normal traffic, not an error path. Found by walking the `unmatched` scenario.
  const readSomething = Boolean(line?.kind_label || shopName || purchaseDate);
  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl border bg-muted/30 p-4">
        {readSomething ? (
          <p className="text-sm">
            {line?.kind_label ? <strong>{line.kind_label}</strong> : <strong>Your item</strong>}
            {shopName ? (
              <>
                {' '}bought from <strong>{shopName}</strong>
              </>
            ) : null}
            {purchaseDate ? (
              <>
                {' '}on <strong>{purchaseDate}</strong>
              </>
            ) : null}
            . Did we get this right?
          </p>
        ) : (
          <p className="text-sm">
            We could not read much from that photo. Fill in whatever you know below - none of
            it is compulsory, and you can still send your report.
          </p>
        )}
      </div>

      {/* Every value is an ordinary input. Nothing here is read-only (AC-C10a). */}
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Where did you buy it?</span>
        <Input
          value={shopName}
          onChange={(e) => onShopName(e.target.value)}
          placeholder="Shop name on your receipt"
          className="h-11"
        />
        {!shopName ? (
          <span className="text-xs text-muted-foreground">
            We could not read a shop name. Type it if you know it - it is not compulsory.
          </span>
        ) : null}
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">When did you buy it?</span>
        <Input
          type="date"
          value={purchaseDate}
          onChange={(e) => onPurchaseDate(e.target.value)}
          className="h-11"
        />
      </label>

      {/* The consumer is never shown the dealer match, the customer code, or a picker
          (AC-C11). `candidate` and `unmatched` are deliberately indistinguishable here -
          the difference travels to CS, not to them. */}
      <Button onClick={onContinue} className="h-11">
        {readSomething ? 'Yes, that is right' : 'Continue'}
      </Button>
    </section>
  );
}

/* ------------------------------------------------------------------ step 3 */

function StepKind({
  selected,
  onSelect,
  onContinue,
}: {
  selected: string | null;
  onSelect: (code: string) => void;
  onContinue: () => void;
}) {
  return (
    <section className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">Which item has the problem?</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {MOCK_KINDS.map((kind) => {
          const active = selected === kind.code;
          return (
            <button
              key={kind.code}
              type="button"
              onClick={() => onSelect(kind.code)}
              className={`flex min-h-24 flex-col items-center justify-center gap-2 rounded-xl border p-3 text-center transition-colors ${
                active ? 'border-primary bg-primary/5 ring-2 ring-primary' : 'hover:bg-muted/50'
              }`}
            >
              {/* No icon exists for any of the 31 kinds yet, so the tile falls back to an
                  initial. That fallback is deliberately plain rather than pretty: it is the
                  visible cost of the missing consumer_icon data, and hiding it would let the
                  decision slide. */}
              <span className="flex size-10 items-center justify-center rounded-full bg-muted text-base font-semibold">
                {kind.label.charAt(0)}
              </span>
              <span className="text-xs leading-tight">{kind.label}</span>
            </button>
          );
        })}
      </div>
      <Button onClick={onContinue} disabled={!selected} className="h-11">
        Continue
      </Button>
    </section>
  );
}

/* ------------------------------------------------------------------ step 4 */

function StepFault({
  fault,
  onFault,
  photos,
  onAddPhoto,
  onRetake,
  onContinue,
}: {
  fault: string;
  onFault: (v: string) => void;
  photos: ProofPhoto[];
  onAddPhoto: () => void;
  onRetake: (index: number) => void;
  onContinue: () => void;
}) {
  return (
    <section className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">What is wrong with it?</span>
        <Textarea
          value={fault}
          onChange={(e) => onFault(e.target.value)}
          placeholder="Tell us in your own words"
          rows={4}
        />
      </label>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">Photos of the problem</span>
        {photos.map((photo, index) => (
          <div key={photo.name} className="rounded-lg border p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-sm">{photo.name}</span>
              {photo.checking ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
              ) : photo.check?.passed ? (
                <Check className="size-4 shrink-0 text-emerald-600" />
              ) : null}
            </div>
            {/* Advisory, never blocking. The nudge is about the SHOT, never the person. */}
            {photo.check && !photo.check.passed ? (
              <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="min-w-0 text-xs text-amber-700 dark:text-amber-500">
                  {photo.check.suggestion}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 shrink-0"
                  onClick={() => onRetake(index)}
                >
                  <RefreshCw className="mr-1.5 size-3" />
                  Retake
                </Button>
              </div>
            ) : null}
          </div>
        ))}
        <Button variant="outline" onClick={onAddPhoto} className="h-11">
          <Camera className="mr-2 size-4" />
          Add a photo
        </Button>
      </div>

      {/* Deliberately enabled with no photos and no text: nothing blocks submission. */}
      <Button onClick={onContinue} className="h-11">
        Continue
      </Button>
    </section>
  );
}

/* ------------------------------------------------------------------ step 5 */

function StepPlace({
  pin,
  address,
  onAddress,
  onLocate,
  busy,
  onSubmit,
}: {
  pin: PinState;
  address: string;
  onAddress: (v: string) => void;
  onLocate: () => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  return (
    <section className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Where is the item installed?</span>
        <Textarea
          value={address}
          onChange={(e) => onAddress(e.target.value)}
          placeholder="Address where our technician should go"
          rows={3}
        />
      </label>

      {/* Pin and address are both kept and neither is reconciled (AC-M39): the pin is what
          the technician navigates to, the address is what appears on documents. Asking a
          consumer to resolve a disagreement they do not perceive helps nobody. */}
      <div className="rounded-lg border p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium">Drop a pin (optional)</p>
            <p className="text-xs text-muted-foreground">
              {pin === 'set'
                ? 'Pin saved - this is what the technician will navigate to.'
                : pin === 'denied'
                  ? 'No problem. We will use the address you typed.'
                  : 'Helps our technician find you. You can skip this.'}
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0"
            onClick={onLocate}
            disabled={pin === 'locating'}
          >
            {pin === 'locating' ? (
              <Loader2 className="mr-1.5 size-3 animate-spin" />
            ) : (
              <MapPin className="mr-1.5 size-3" />
            )}
            {pin === 'set' ? 'Move pin' : 'Use my location'}
          </Button>
        </div>
      </div>

      <Button onClick={onSubmit} disabled={busy} className="h-11">
        {busy ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            Sending
          </>
        ) : (
          'Submit'
        )}
      </Button>
    </section>
  );
}

/* ------------------------------------------------------------------ step 6 */

function StepDone({ result }: { result: LodgeResult }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col items-center gap-2 py-6 text-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950">
          <Check className="size-7 text-emerald-600" />
        </span>
        <p className="text-base font-semibold">We have your report</p>
        <p className="text-sm text-muted-foreground">
          Reference <strong>{result.complaint_number}</strong>
        </p>
      </div>

      {/* The verdict is the value exchanged for the data. Showing it here is the whole
          bargain of the journey made visible. */}
      <div className="rounded-xl border bg-muted/30 p-4">
        <p className="flex items-start gap-2 text-sm">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" />
          <span className="min-w-0">{result.warranty.summary}</span>
        </p>
      </div>

      <p className="text-sm text-muted-foreground">
        We will message you here as things progress. You do not need to chase anyone.
      </p>
    </section>
  );
}
