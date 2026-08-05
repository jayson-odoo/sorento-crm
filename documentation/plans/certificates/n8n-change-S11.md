# S11 - the n8n change, prepared but NOT applied

**Status:** ready to apply, awaiting explicit go.
**Why it is not applied:** `system-upload-attachments` (workflow id `_NbFU3cCoEQwPSbvn14vV`) is a live
production automation. Editing it is an outward-facing change, so it is written out here rather than
pushed. Nothing in the backend depends on this being applied first: until it is, cert fields simply never
arrive and the ingest path behaves exactly as it does today (ING-5).

---

## Scope: one prompt edit and one parser edit. No node added, no branch rewired.

`Switch` already routes `attachment_type == "Certification"` to output index 2, which funnels into
`switch-attachment-type` and then `analyze-product-document`. `technical-attachments-create` keeps POSTing
to the same URL with the same body expression (`{{ $json.toJsonString() }}`).

---

## 1. Node `analyze-product-document` (googleGemini, `models/gemini-2.5-flash`)

### Current prompt

```
The document is an attachment tied to 1 or multiple products. Analyze the document and extract a list of products in this format

Output format:
{
  "products": ["TESLA",'"BYD"]
}
```

Note the example is not valid JSON - `'"BYD"` carries a stray apostrophe. The downstream parser survives it
only because it slices to the outermost braces and retries after stripping `" + "`. Worth fixing while we
are here.

### Replacement prompt

```
The document is an attachment tied to one or more products.

Extract:
1. Every product code or model name the document applies to.
2. If, and only if, the document is a regulatory or certification document, its certificate details.

A certification document names an approval scheme (for example PPS, SPAN, SIRIM), a certifying body (for
example IKRAM, JBC), a certificate or approval number, and usually an expiry date. If the document is a
datasheet, brochure, drawing or photo, it is NOT a certificate: return null for every certificate field
even if a certificate number is mentioned somewhere in the text.

Return ONLY valid JSON in exactly this shape, with no markdown fence and no commentary:

{
  "products": ["WC8038", "WC8040"],
  "scheme": "PPS",
  "certifying_body": "IKRAM",
  "certificate_number": "04424FC",
  "issuer": null,
  "issued_at": "2024-12-24",
  "valid_from": "2024-12-24",
  "valid_until": "2026-12-23"
}

Rules:
- Dates are ISO `YYYY-MM-DD`, or null if the document does not state them. Never guess a date.
- `scheme` is the approval scheme only (PPS, SPAN, ...), not the certifying body.
- `certificate_number` excludes the scheme prefix: for "PPS - IKRAM 04424FC" the number is "04424FC".
- Use null, never an empty string, for anything absent.
```

### Also set (node options)

Enable Gemini structured output / JSON response mode on this node so the model cannot emit a markdown
fence. The parser below still strips fences defensively, but the schema is the real fix.

---

## 2. Node `analyze_document_output_parser1` (Code, runOnceForEachItem)

Keep the existing fence-stripping and brace-slicing. Add the certificate passthrough at the end.

### Current tail

```js
const products = Array.isArray(parsed.products) ? parsed.products : [];
if (filename && !products.includes(filename)) products.push(filename);

return {
  products,
  attachment_id: $('Webhook').first().json.body.attachment_id,
  access_level:  $('Webhook').first().json.body.access_levels,
};
```

### Replacement tail

```js
const products = Array.isArray(parsed.products) ? parsed.products : [];
if (filename && !products.includes(filename)) products.push(filename);

// Certificate fields ride along on the SAME payload to the SAME endpoint. The backend
// ignores them unless the attachment's type has is_certificate = true (ING-4), so a
// datasheet that happens to quote a certificate number cannot mint a certificate.
const orNull = (v) => (v === undefined || v === '' ? null : v);

return {
  products,
  attachment_id: $('Webhook').first().json.body.attachment_id,
  access_level:  $('Webhook').first().json.body.access_levels,

  scheme:             orNull(parsed.scheme),
  certifying_body:    orNull(parsed.certifying_body),
  certificate_number: orNull(parsed.certificate_number),
  issuer:             orNull(parsed.issuer),
  issued_at:          orNull(parsed.issued_at),
  valid_from:         orNull(parsed.valid_from),
  valid_until:        orNull(parsed.valid_until),
};
```

`analyze-product-image` and `analyze-product-video` feed the same parser. They will not return certificate
fields, so `orNull` yields nulls and the backend takes the plain product-linking path. No change needed on
those two nodes.

---

## 3. Nothing to change on `technical-attachments-create`

URL, auth, and `jsonBody: {{ $json.toJsonString() }}` all stay. The extra keys simply ride along.

---

## Rollback

Revert the two node bodies. The backend keeps working: with no cert fields in the payload, ingest is
byte-identical to today's behaviour, which is exactly what ING-5 pins with a regression test.

## How to verify after applying

1. Re-upload one existing certification PDF (for example `PPS - IKRAM 04424FC - EXP 23 DEC 2026.pdf`).
2. Confirm the `integration_log` row for that attachment shows the cert fields in the request payload.
3. Confirm one `certificates` row exists with scheme `PPS`, number `04424FC`, and a revision carrying the
   expiry.
4. Re-upload the SAME file again: it must append revision 2 to the SAME certificate, not create a second
   one, and coverage must be unchanged.
5. Upload a Technical Specifications PDF that mentions a certificate number: it must create NO certificate.
