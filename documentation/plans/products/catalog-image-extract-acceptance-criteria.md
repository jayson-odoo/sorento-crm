# UAC: Catalogue photo extraction (CATALOG-IMAGES)

Plan: `PLAN-catalog-image-extract-27oct.md`. Mock: `documentation/mockups/CATALOG-IMAGES/index.html`
(v2, approved 27 Oct 19:19 with conditions: reuse components, pagination, simple guided UI).
Q6-Q9 follow the lead's recommendations (no explicit owner answer); Q10 = (b): no production storage
read, the duplicate count is measured at the hand test.

## Entry and upload
- AC-1 The Products list "Actions" menu has "Extract photos from catalogue", shown only to users with
  `dealer_kit.page.edit`.
- AC-2 It opens the existing upload dialog: PDF only, 50 MB ceiling. A non-PDF, an encrypted PDF or a
  file over 50 MB is refused with a plain message and nothing is stored.
- AC-3 After upload the reading appears in the existing upload-activity drawer and the user lands on the
  review page, which shows the step indicator (Upload, Review, Attach) on Upload with progress until the
  worker finishes.
- AC-4 The worker stores every kept photo as a file in a new folder "Catalogue photos/<PDF name>",
  named by its first code (`SRTWT1906-BL-DIY.jpg`, a second one `SRTWT1906-BL-DIY (2).jpg`, no code
  `p01-photo-01.jpg`), attachment type "Product Photos" when that type exists. No n8n upload webhook
  fires for these files.

## Review (step 2)
- AC-5 Four line tabs with counts: Ready, Looks like an existing photo, Needs a product, Skipped. Each tab
  is a DataGrid with server-side pagination and sorting (default page, then position).
- AC-6 Ready rows: thumbnail, page, printed code, product, confidence (High exact; Medium normalised,
  suffix or alias). Other matched codes of the same caption are "Also attach" choices, off by default.
- AC-7 A placeholder (`SRTWB_____`) is shown as a placeholder and never matched.
- AC-8 Needs a product rows: thumbnail, page, printed code or "No code found", a "Did you mean" hint when
  one exists (shown, never applied), a product picker (SearchableSelect, clearable) and Skip. Picking a
  product moves the row to Ready.
- AC-9 Looks like an existing photo: a photo whose image is close to one of the product's existing
  photos (perceptual hash, not only sha256) shows both thumbnails side by side and a per-row choice
  Skip (default), Keep both, Replace.
- AC-10 Skip moves a row to Skipped; Skipped rows can be restored.
- AC-11 Header: one primary action "Attach N photos" (N = rows that will attach), plus "Download all as
  ZIP" (existing bulk download of the folder) and "Open folder" (existing drive view, where files move
  by drag and drop).
- AC-12 No product UUID, no "main photo" wording, no explanation text in the UI.

## Attach (step 3)
- AC-13 Attach links each chosen photo to its product (and to ticked "also attach" products) through the
  existing product photo link. Nothing is written before Attach.
- AC-14 A product whose single photo shows automatically today keeps showing it (that photo is pinned
  behind the scenes before the new one is linked).
- AC-15 Replace removes the product's link to the look-alike photo (the file stays in its folder) and
  links the new one. Keep both links the new one only.
- AC-16 A photo whose bytes are already linked to that product is not linked again. Attaching twice adds
  nothing the second time.
- AC-17 After Attach a summary toast names attached, replaced and skipped counts; attached rows show
  "Attached" and cannot be changed.

## Access and scope
- AC-18 Upload and review need `dealer_kit.page.edit`; Attach also needs `master_data.products.edit`
  (403 otherwise).
- AC-19 Readings, photos and products are company-scoped: another company's reading is 404 and its
  products are never proposed or assignable.

## Layout
- AC-20 Usable and not clipped at 375px and 1280px.
