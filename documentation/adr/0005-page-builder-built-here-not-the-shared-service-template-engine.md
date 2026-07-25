# The Dealer Kit page builder is built here, not on the shared-service template engine

`foundryx-shared-service/service_backend/app/template_engine` already renders documents from
a block model, has a canvas editor, merge tokens, contexts and a WeasyPrint PDF path. We are
not reusing it for the Dealer Kit's web pages. It stays where it is, for email and print.

The engine is print-first, and the Kit's pages are screen-first. That is not a preference —
it is the coordinate system:

- `CanvasDocumentModel` is **one fixed card**: millimetres, `bleed`, `sides[front|back]`,
  absolutely-positioned elements. No pagination, no repeater, no notion of a breakpoint.
- `TemplateDocumentModel` is a **flowing block document** — `RepeaterBlock` over a list fact,
  emitted as semantic HTML plus `@page` print CSS for WeasyPrint.

A catalogue page needs three things neither surface has: a **per-breakpoint layout** (the
same page at 375px, 768px and 1280px, authored once), a **grid block bound to a curated
product set** whose prices and visibility resolve per viewer, and a **print profile** that is
a view of the screen document rather than a second document. Bending mm-and-bleed geometry
into a responsive page means retrofitting the one concept the model was built without.

Embedding the shared service by iframe was rejected separately: the Kit's data — products,
prices, images, stock, orders, dealer identity — all lives in this database, so the boundary
would buy an iframe and cost a full mirror of the product and pricing domain plus a second
auth handshake, for a page that is Sorento's catalogue and reusable by nobody else. The
ideation embed already showed what that costs (`embed_connections.tenant_id VARCHAR(32)`
silently truncating a 36-char UUID into an empty iframe).

The reuse axis that does matter is **`dreamz_ems`**, which needs a website builder. A
responsive section-and-grid document model ports there directly; a print document model does
not. That is why the new engine is web-first even though the first artefact it produces is a
catalogue.

The print path does not fork the renderer: PDF is headless Chromium printing the same React
runtime, so what marketing designs is byte-for-byte what exports. The shared-service engine
keeps email, where its MJML output is correct and ours would not be.

If the two engines ever converge, the merge direction is the web model gaining a print
profile — not the print model gaining breakpoints.
