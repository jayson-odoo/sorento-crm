# PLAN: Catalogue image extraction (CATALOG-IMAGES)

Status: Plan (scouting; behaviour card pending owner answers). Track: full (new upload ingest surface).

Owner ask (27 Oct 2026, verbatim): "i got this code that reads pdf like [catalogue page] and turns it into
images with their proximity product code as the file name, i want to generalize this and have this
capability in our system".

## Journey
Upload a catalogue PDF -> system extracts each product photo, finds the product code(s) near it by layout,
matches them against the product master -> review grid (thumbnail, page, matched codes, confidence,
unmatched bucket) -> user confirms / reassigns / skips -> confirmed photos attach to products as product
images through the existing attachments model. Re-upload of a newer catalogue never duplicates (hash).

## Scout
(filled in next commit)
