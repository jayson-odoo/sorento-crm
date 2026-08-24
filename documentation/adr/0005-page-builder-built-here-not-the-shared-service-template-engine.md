# The Dealer Kit page builder is built here, not on the shared-service template engine

`foundryx-shared-service/service_backend/app/template_engine` already renders documents from
a block model, has a canvas editor, merge tokens, contexts and a WeasyPrint PDF path. We are
not reusing it for the Dealer Kit's web pages. It stays where it is, serving the shared
service's own products. (Amended below: email moves here too.)

The engine is print-first, and the Kit's pages are screen-first. That is not a preference - 
it is the coordinate system:

- `CanvasDocumentModel` is **one fixed card**: millimetres, `bleed`, `sides[front|back]`,
  absolutely-positioned elements. No pagination, no repeater, no notion of a breakpoint.
- `TemplateDocumentModel` is a **flowing block document** - `RepeaterBlock` over a list fact,
  emitted as semantic HTML plus `@page` print CSS for WeasyPrint.

A catalogue page needs three things neither surface has: a **per-breakpoint layout** (the
same page at 375px, 768px and 1280px, authored once), a **grid block bound to a curated
product set** whose prices and visibility resolve per viewer, and a **print profile** that is
a view of the screen document rather than a second document. Bending mm-and-bleed geometry
into a responsive page means retrofitting the one concept the model was built without.

Embedding the shared service by iframe was rejected separately: the Kit's data - products,
prices, images, stock, orders, dealer identity - all lives in this database, so the boundary
would buy an iframe and cost a full mirror of the product and pricing domain plus a second
auth handshake, for a page that is Sorento's catalogue and reusable by nobody else. The
ideation embed already showed what that costs (`embed_connections.tenant_id VARCHAR(32)`
silently truncating a 36-char UUID into an empty iframe).

The reuse axis that does matter is **`dreamz_ems`**, which needs a website builder. A
responsive section-and-grid document model ports there directly; a print document model does
not. That is why the new engine is web-first even though the first artefact it produces is a
catalogue.

The print path does not fork the renderer: PDF is headless Chromium printing the same React
runtime, so what marketing designs is byte-for-byte what exports.

If the two engines ever converge, the merge direction is the web model gaining a print
profile - not the print model gaining breakpoints.

## Amendment (2026-07-25) - email comes here too

This ADR originally left email with the shared service, on the grounds that its MJML output is
correct and ours would not be. That is reversed: **Sorento gets its own email templating in
this engine**, so a marketer authors screen, print and email in one place against one asset
library.

The technical objection stands and is not being waved away - email is not a browser. Outlook
renders through Word, so CSS Grid, flexbox and free positioning are unavailable, and the
emitter must produce nested tables with inline styles. So this is **three emitters over one
document model**, not one renderer with three settings: screen keeps the full grid, print goes
through Chromium at paper geometry, and email degrades to stacked table rows with a
constrained block set. A template declares which emitters it targets, and the editor hides the
blocks the chosen emitters cannot express, rather than letting someone design something that
silently breaks in Outlook.

What genuinely carries across all three is the asset library, the tile designs, tokens, and
the product binding. What does not is artboard positioning, fine-grained grid spans and
anything interactive.

The consequence accepted deliberately: the shared service keeps its MJML engine for its own
products, so two email engines exist in the estate. They serve different products with
different lifecycles, and one authoring surface per product beats one engine across products
that never share a template.
