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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Camera,
  Check,
  Clipboard,
  FileText,
  Loader2,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  mockCheckPhoto,
  type ExtractResult,
  type LodgeResult,
  type MockScenario,
  type PhotoCheck,
  type ExtractedLine,
} from './lodgeMocks';
import { mockLodgeBackend, recheckDealer, type LodgeBackend } from './lodgeBackend';
import { AttachmentDropzone } from '../AttachmentDropzone';
import {
  EMPTY_SITE_ADDRESS,
  SitePicker,
  composeSiteAddress,
  type SiteAddress,
} from './SitePicker';

type Step = 'upload' | 'confirm' | 'items' | 'fault' | 'place' | 'done';

interface ProofPhoto {
  name: string;
  checking: boolean;
  check: PhotoCheck | null;
}

/** Pin state. Three outcomes to draw, not one (AC-M38). */

const STEP_ORDER: Step[] = ['upload', 'confirm', 'items', 'fault', 'place', 'done'];

export function LodgeFlow({
  scenario = 'resolved',
  backend = mockLodgeBackend,
  live = false,
  contact,
  mapsApiKey = null,
}: {
  scenario?: MockScenario;
  /** Who the token says this is. Supplied on the live route so neither the phone nor the
   *  name is ever asked for. */
  contact?: { phone: string | null; name: string | null };
  /** Mock by default, so the `?scenario=` demo route keeps working with no token. */
  backend?: LodgeBackend;
  /** The tenant's Maps browser key, from `/me`. Null means fields only and no map. */
  mapsApiKey?: string | null;
  /** True on the token-scoped route. Enables the dealer re-check, which needs a real
   *  customer table to match against. */
  live?: boolean;
}) {
  const [step, setStep] = useState<Step>('upload');
  const [busy, setBusy] = useState(false);
  const [extract, setExtract] = useState<ExtractResult | null>(null);
  const [dealerEcho, setDealerEcho] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Everything extracted is held as EDITABLE form state from the moment it arrives.
  const [shopName, setShopName] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  // Known on the live route from the token's contact, so the consumer is not asked for
  // either (Phase 0: anything knowable is never asked for). Held here because the mock
  // route has no contact and the submit payload needs both.
  const [phone, setPhone] = useState('');
  const [fullName, setFullName] = useState('');
  // WHICH extracted products are faulty, by index. Replaces the Kind question: the
  // consumer knows which of their items broke, and does not know - and should never be
  // asked - what taxonomy Sorento files it under.
  const [faultyLines, setFaultyLines] = useState<number[]>([]);
  // What they type when the receipt yielded nothing. Free text on purpose: a consumer who
  // cannot see a product list has no vocabulary to pick from either.
  const [manualItems, setManualItems] = useState<string[]>([]);
  const [fault, setFault] = useState('');
  const [photos, setPhotos] = useState<ProofPhoto[]>([]);
  // AC-M37: what a technician navigates to. Deliberately NOT reconciled against the typed
  // address (AC-M39) - the pin is for navigation, the address for documents.
  const [coords, setCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  const [address, setAddress] = useState<SiteAddress>(EMPTY_SITE_ADDRESS);
  const [result, setResult] = useState<LodgeResult | null>(null);

  const progress = useMemo(
    () => (STEP_ORDER.indexOf(step) / (STEP_ORDER.length - 1)) * 100,
    [step],
  );

  useEffect(() => {
    if (contact?.phone) setPhone(contact.phone);
    if (contact?.name) setFullName(contact.name);
  }, [contact?.name, contact?.phone]);


  const runExtract = useCallback(async (files: File[] = []) => {
    setBusy(true);
    try {
      const data = await backend.extract(scenario, files);
      setExtract(data);
      // Pre-fill from extraction - but NEVER pre-fill a dealer we are not sure of. A
      // `candidate` is a suggestion for CS, not an answer to show the consumer as fact.
      setShopName(data.shop_name_raw ?? '');
      setPurchaseDate(data.purchase_date ?? '');
      // Default to ALL of them. A receipt is one purchase and the ordinary complaint is
      // about the thing that broke; pre-selecting everything means a consumer with one
      // item taps nothing, and a consumer with three unticks the two that are fine.
      setFaultyLines(data.lines.map((_line, index) => index));
      setManualItems([]);
      setStep('confirm');
    } finally {
      setBusy(false);
    }
  }, [backend, scenario]);

  /**
   * Re-run the dealer match when the consumer finishes editing the shop name.
   *
   * The whole point of pre-filling an EDITABLE form is that a correction changes the
   * answer. Without this, fixing a misread shop name changes what is on screen and
   * nothing else, and the ledger still records the wrong dealer.
   */
  const recheckShopName = useCallback(
    async (value: string) => {
      const echo = await recheckDealer(live, value);
      setDealerEcho(echo?.state === 'resolved' ? echo.customerName : null);
    },
    [live],
  );

  /**
   * Photo quality feedback. MOCK-ONLY, and gated on `live` for that reason.
   *
   * The mock returns a plausible AI verdict on every second shot so the retake affordance
   * is always walkable in the prototype. Running it on the real route would show a consumer
   * a fabricated judgement of a photo nothing actually looked at - worse than showing them
   * nothing, because they would retake a perfectly good shot on our say-so. Real validation
   * is S2a's `attachment_validation_service`, which this flow does not call yet.
   */
  const addPhoto = useCallback(async () => {
    const index = photos.length;
    setPhotos((prev) => [
      ...prev,
      { name: `photo-${index + 1}.jpg`, checking: !live, check: null },
    ]);
    if (live) return;
    const check = await mockCheckPhoto(index);
    setPhotos((prev) =>
      prev.map((p, i) => (i === index ? { ...p, checking: false, check } : p)),
    );
  }, [live, photos.length]);

  const retakePhoto = useCallback(
    async (index: number) => {
      setPhotos((prev) =>
        prev.map((p, i) => (i === index ? { ...p, checking: !live, check: null } : p)),
      );
      if (live) return;
      // A retake is a fresh shot, so it is checked afresh. Passing it deterministically
      // keeps the prototype honest about the affordance without pretending the AI improved.
      const check = await mockCheckPhoto(index + 1);
      setPhotos((prev) => prev.map((p, i) => (i === index ? { ...p, checking: false, check } : p)));
    },
    [live],
  );

  const submit = useCallback(async () => {
    setBusy(true);
    setSubmitError(null);
    try {
      setResult(
        await backend.submit({
          // The phone is the profile's identity. On the live route the token already
          // establishes the contact, and the backend normalises whatever spelling
          // arrives to E.164 before resolving the profile.
          phone: phone,
          full_name: fullName || null,
          shop_name: shopName || null,
          purchase_date: purchaseDate || null,
          // Both the composed line and its parts. The server recomposes from the parts,
          // so the one-liner here is what a client without them would have sent.
          site_address: composeSiteAddress(address) || null,
          site_address_line1: address.line1 || null,
          site_address_line2: address.line2 || null,
          site_postcode: address.postcode || null,
          site_city: address.city || null,
          site_state: address.state || null,
          site_country: address.country || null,
          latitude: coords?.latitude ?? null,
          longitude: coords?.longitude ?? null,
          defect_description: fault || null,
          // Every file the consumer uploaded on step one, already stored server-side when
          // it was read. Sent so the receipt and the photo of the fault end up ON the
          // complaint: before this they were posted to a model and dropped, and a
          // consumer who photographed their receipt got a complaint with no receipt on it.
          attachment_ids: extract?.attachment_ids ?? [],
          // EVERY extracted line, not just the first. A receipt with a toilet and a tap
          // on it is one purchase covering two products, and sending only `lines[0]`
          // silently dropped the rest - the ledger then records half a sale, and the
          // second product has no purchase date to compute its cover from.
          //
          // The chosen Kind applies to the first line only. The tiled chooser asks one
          // question ("which item has the problem?"), and answering it on the consumer's
          // behalf for every other product on the receipt would be a guess wearing a
          // warranty term. CS resolves the rest from `claimed_text`.
          //
          // `kind_code` is never sent. The Kind decides warranty TERMS (ADR-0010), which
          // makes it Sorento's classification of its own catalogue - derivable from the
          // model code server-side, and CS's problem when the code resolves to nothing.
          // Asking a consumer which of 31 categories their broken toilet belongs to was
          // making them do that filing, and a wrong answer is a warranty term.
          lines: [
            ...(extract?.lines ?? []).map((line, index) => ({
              claimed_text: line.claimed_text ?? null,
              model_code_raw: line.model_code_raw ?? null,
              kind_code: null,
              quantity: line.quantity ?? 1,
              // The fault is attached to the lines the consumer said are broken. An
              // untouched line is still sent - it is part of the same purchase and the
              // ledger needs it - but carries no fault.
              fault_description: faultyLines.includes(index) ? fault || null : null,
            })),
            ...manualItems
              .map((text) => text.trim())
              .filter(Boolean)
              .map((text) => ({
                claimed_text: text,
                model_code_raw: null,
                kind_code: null,
                quantity: 1,
                fault_description: fault || null,
              })),
          ],
        }),
      );
      setStep('done');
    } catch (error) {
      // Submission is the one place a consumer cannot simply be told "it worked". The
      // only refusal the backend issues is consent, and it has to be visible.
      setSubmitError(error instanceof Error ? error.message : 'Could not submit your report.');
    } finally {
      setBusy(false);
    }
  }, [address, backend, coords, extract, fault, faultyLines, fullName, manualItems, phone, purchaseDate, shopName]);

  // Phone-first, because the journey arrives from a WhatsApp link - but it grows with the
  // viewport rather than sitting in a 576px column with empty gutters on a desktop. Still
  // capped: a single-column form stretched across 1400px puts a label and its input at
  // opposite ends of the screen.
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-4 px-4 py-6 sm:max-w-2xl sm:px-6 lg:max-w-4xl">
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
        <StepUpload busy={busy} live={live} onContinue={runExtract} />
      ) : null}

      {step === 'confirm' && extract ? (
        <StepConfirm
          extract={extract}
          shopName={shopName}
          purchaseDate={purchaseDate}
          onShopName={setShopName}
          onShopNameSettled={recheckShopName}
          dealerEcho={dealerEcho}
          onPurchaseDate={setPurchaseDate}
          onContinue={() => setStep('items')}
        />
      ) : null}

      {step === 'items' ? (
        <StepItems
          lines={extract?.lines ?? []}
          faulty={faultyLines}
          onToggle={(index) =>
            setFaultyLines((current) =>
              current.includes(index)
                ? current.filter((i) => i !== index)
                : [...current, index],
            )
          }
          manualItems={manualItems}
          onManualItems={setManualItems}
          onContinue={() => setStep('fault')}
        />
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
          address={address}
          onAddress={setAddress}
          coords={coords}
          onCoords={setCoords}
          mapsApiKey={mapsApiKey}
          busy={busy}
          error={submitError}
          onSubmit={submit}
        />
      ) : null}

      {step === 'done' && result ? <StepDone result={result} /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ step 1 */

function StepUpload({
  busy,
  live,
  onContinue,
}: {
  busy: boolean;
  /** On the mock route there is no upload endpoint, so a tap just counts a photo. */
  live: boolean;
  onContinue: (files: File[]) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [count, setCount] = useState(0);

  const ready = live ? files.length : count;

  return (
    <section className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Take a photo of your receipt and of the problem. We will read the rest ourselves.
      </p>

      {live ? (
        /* The SAME component the rest of the portal attaches files with. The first version
           here was a bespoke tile that had to re-learn drag-and-drop, clipboard paste,
           previews and removal one bug at a time - and had already lost photos once by
           replacing the list instead of appending to it. `pendingFiles` mode exists for
           exactly this case: there is no submission to attach to yet, so the files are held
           and handed to extraction on Continue. */
        <AttachmentDropzone
          kind="complaint"
          submissionId={null}
          attachments={[]}
          onChange={() => {}}
          disabled={busy}
          pendingFiles={files}
          onPendingFilesChange={setFiles}
        />
      ) : (
        <button
          type="button"
          onClick={() => setCount((c) => c + 1)}
          className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors hover:bg-muted/50"
        >
          <Camera className="size-8 text-muted-foreground" />
          <span className="text-sm font-medium">Add a photo</span>
          <span className="text-xs text-muted-foreground">
            Preview route - no file is uploaded
          </span>
        </button>
      )}

      {ready > 0 ? (
        <p className="text-sm text-muted-foreground">
          {ready} photo{ready === 1 ? '' : 's'} ready.
        </p>
      ) : null}
      <Button onClick={() => onContinue(files)} disabled={busy || ready === 0} className="h-11">
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
  onShopNameSettled,
  dealerEcho,
  onPurchaseDate,
  onContinue,
}: {
  extract: ExtractResult;
  shopName: string;
  purchaseDate: string;
  onShopName: (v: string) => void;
  /** Fired on blur, not per keystroke: a match on every character would fire a request
   *  per letter and flicker an answer that is wrong until the name is finished. */
  onShopNameSettled: (v: string) => void;
  /** The dealer's own name, only when the match was exact. A `candidate` is never shown
   *  as a fact - three receipts in thirty-eight matched a real but WRONG shop. */
  dealerEcho: string | null;
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
          onBlur={(e) => onShopNameSettled(e.target.value)}
          placeholder="Shop name on your receipt"
          className="h-11"
        />
        {dealerEcho ? (
          <span className="text-xs text-muted-foreground">
            <Check className="mr-1 inline size-3" />
            We found them: {dealerEcho}
          </span>
        ) : !shopName ? (
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

/**
 * Which of YOUR items broke - not which of Sorento's 31 categories it belongs to.
 *
 * The receipt has already been read, so the products are known. Showing the full Kind
 * catalogue here threw that away and asked a consumer to file their own broken toilet into
 * a taxonomy invented for warranty terms: 31 tiles, four of which begin "Kitchen", to answer
 * a question they had already answered by photographing the receipt.
 *
 * **The Kind is not asked at all any more.** It decides warranty TERMS (ADR-0010), which
 * makes it Sorento's classification of Sorento's own catalogue - derivable from the model
 * code server-side, and CS's job when the code resolves to nothing (`SRTWC8152` matches
 * three variants and resolves to none, AC-C17). A consumer's guess at it is a warranty term
 * entered by someone with no stake in it being right.
 *
 * **No fallback to the catalogue when extraction found nothing.** A consumer who cannot see
 * their own product in a list has no vocabulary to pick one from either, so they type what
 * broke in their own words and CS reads it. That is strictly more information than a tile
 * chosen by elimination.
 */
function StepItems({
  lines,
  faulty,
  onToggle,
  manualItems,
  onManualItems,
  onContinue,
}: {
  lines: ExtractedLine[];
  faulty: number[];
  onToggle: (index: number) => void;
  manualItems: string[];
  onManualItems: (next: string[]) => void;
  onContinue: () => void;
}) {
  const nothingFound = lines.length === 0;
  const typed = manualItems.filter((text) => text.trim()).length;
  // Nothing to send on is the one state worth blocking: the report would name no product.
  const canContinue = nothingFound ? typed > 0 : faulty.length > 0;

  return (
    <section className="flex flex-col gap-4">
      {nothingFound ? (
        <>
          <div className="rounded-md border bg-muted/40 p-3">
            <p className="text-sm font-medium">We could not read any products.</p>
            <p className="mt-1 text-xs text-muted-foreground">
              The receipt may be blurred or handwritten. Tell us what broke in your own words
              and we will work it out - nothing is lost.
            </p>
          </div>
          {(manualItems.length ? manualItems : ['']).map((value, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={value}
                placeholder="e.g. the toilet seat, or SRTWC8152"
                onChange={(event) => {
                  const next = manualItems.length ? [...manualItems] : [''];
                  next[index] = event.target.value;
                  onManualItems(next);
                }}
              />
              {manualItems.length > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  aria-label={`Remove item ${index + 1}`}
                  onClick={() => onManualItems(manualItems.filter((_, i) => i !== index))}
                >
                  <X className="size-4" />
                </Button>
              ) : null}
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => onManualItems([...(manualItems.length ? manualItems : ['']), ''])}
          >
            Add another item
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Which of these has the problem? Tap to unselect anything that is fine.
          </p>
          <ul className="flex flex-col gap-2">
            {lines.map((line, index) => {
              const active = faulty.includes(index);
              const label = line.claimed_text || line.model_code_raw || 'Item on your receipt';
              return (
                <li key={`${line.model_code_raw ?? 'line'}-${index}`}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => onToggle(index)}
                    className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors ${
                      active ? 'border-primary bg-primary/5 ring-2 ring-primary' : 'hover:bg-muted/50'
                    }`}
                  >
                    <span
                      className={`flex size-5 shrink-0 items-center justify-center rounded border ${
                        active ? 'border-primary bg-primary text-primary-foreground' : 'border-input'
                      }`}
                    >
                      {active ? <Check className="size-3.5" /> : null}
                    </span>
                    <span className="min-w-0">
                      <span className="block break-words text-sm font-medium">{label}</span>
                      {line.quantity && line.quantity > 1 ? (
                        <span className="block text-xs text-muted-foreground">
                          Quantity {line.quantity}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <Button
            type="button"
            variant="outline"
            onClick={() => onManualItems([...manualItems, ''])}
          >
            Something else is broken
          </Button>
          {manualItems.map((value, index) => (
            <div key={`manual-${index}`} className="flex gap-2">
              <Input
                value={value}
                placeholder="e.g. the toilet seat"
                onChange={(event) => {
                  const next = [...manualItems];
                  next[index] = event.target.value;
                  onManualItems(next);
                }}
              />
              <Button
                type="button"
                variant="outline"
                aria-label={`Remove item ${index + 1}`}
                onClick={() => onManualItems(manualItems.filter((_, i) => i !== index))}
              >
                <X className="size-4" />
              </Button>
            </div>
          ))}
        </>
      )}
      <Button className="h-11" disabled={!canContinue} onClick={onContinue}>
        Continue
      </Button>
    </section>
  );
}

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
  address,
  onAddress,
  coords,
  onCoords,
  mapsApiKey,
  busy,
  error,
  onSubmit,
}: {
  address: SiteAddress;
  onAddress: (next: SiteAddress) => void;
  coords: { latitude: number; longitude: number } | null;
  onCoords: (next: { latitude: number; longitude: number } | null) => void;
  mapsApiKey: string | null;
  busy: boolean;
  /** The one refusal the backend issues is consent. It has to be visible: a consumer who
   *  thinks the form silently failed submits again. */
  error: string | null;
  onSubmit: () => void;
}) {
  return (
    <section className="flex flex-col gap-4">
      <p className="text-sm font-medium">Where is the item installed?</p>
      <SitePicker
        address={address}
        onAddress={onAddress}
        coords={coords}
        onCoords={onCoords}
        apiKey={mapsApiKey}
      />

      {error ? (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}

      {/* Nothing here blocks submission (AC-C14, AC-M38). An address a consumer could not
          complete is still a report CS can chase; a form that will not send is a phone
          call to the office. */}
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
    </section>
  );
}
