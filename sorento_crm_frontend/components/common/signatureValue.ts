import type { SignatureMode, SignatureValue } from './SignaturePad';

/**
 * One adapter from a stored signature row to what `SignaturePad readOnly` renders.
 *
 * Every backend that stores a signature serializes the same shape (`quotation_signatures` today),
 * and BOTH surfaces that render one - the internal quotation screen and the public counter-sign
 * page - need this conversion. Written once here, beside the pad, so the two cannot drift on how
 * a null GPS or an unknown mode is handled.
 */
export type StoredSignature = {
  signer_name?: string | null;
  mode?: string | null;
  image_data_uri?: string | null;
  signed_at?: string | null;
  /** Decimal strings on the wire. Coordinates, not money, so Number() is safe here. */
  gps_lat?: string | number | null;
  gps_lng?: string | number | null;
};

const MODES: readonly SignatureMode[] = ['draw', 'type', 'initials'];

function coordinate(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function signatureValueFrom(
  record: StoredSignature | null | undefined,
): SignatureValue | null {
  // No image means nothing to render, and the pad's own "Not signed yet" state is the honest
  // answer - better than an empty white box that reads as a broken image.
  if (!record?.image_data_uri) return null;
  const mode = MODES.find((candidate) => candidate === record.mode) ?? 'draw';
  return {
    dataUrl: record.image_data_uri,
    mode,
    typedText: record.signer_name ?? null,
    signedAt: record.signed_at ?? null,
    gpsLat: coordinate(record.gps_lat),
    gpsLng: coordinate(record.gps_lng),
  };
}
