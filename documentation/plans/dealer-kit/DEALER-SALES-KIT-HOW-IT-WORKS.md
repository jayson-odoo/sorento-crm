# Dealer Sales Kit - How It Works

**For:** product, sales and dealer-facing teams
**What this is:** a walkthrough of what each person sees and does. No technical detail.
**Companion document:** *Dealer Sales Kit - Design and Build Plan* (the engineering view).

---

## 1. The problem, as a dealer experiences it today

A customer walks into a dealer's showroom wanting a new bathroom.

1. The dealer opens a printed catalogue. It is from last year. Two of the products the customer
   likes have been discontinued, and the dealer does not know that yet.
2. The customer asks "will this fit?" The dealer says "should do" and they both imagine it.
3. The customer asks "how much altogether?" The dealer writes numbers on paper and adds them up.
4. The customer says "let me think about it" and leaves with nothing in their hand.
5. The dealer phones the office the next day to check stock, then phones the customer back.
   Sometimes.

Every step loses information. The catalogue is stale, the fit is a guess, the total is
handwritten, and the follow-up depends on someone remembering.

## 2. The same visit, with the Dealer Sales Kit

1. The dealer opens the catalogue **on screen**. It is whatever Sorento's marketing team
   published this morning, at this dealer's prices.
2. They tap the products the customer likes. Anything no longer available is **marked as such,
   right there**.
3. They sketch the customer's room by dragging four corners into shape. Wall lengths appear as
   they drag.
4. The chosen products appear **standing in that room**, at their real size, and can be moved
   around. The customer can see it.
5. A summary shows everything chosen, the quantities, the prices **at this customer's level**,
   the room size, and the total.
6. The design is saved. The customer can come back next week and it is still there.

The customer leaves having *seen* their bathroom instead of imagining it.

---

## 3. Who uses it

| Person | Where they are | What they want |
|--------|----------------|----------------|
| **Sorento marketing designer** | Head office | Publish a catalogue once and have every dealer see it |
| **Sorento office staff** | Head office | Send a customer or dealer a PDF of the catalogue at the right prices |
| **Dealer** | Their showroom, customer beside them | Get to a believable answer in minutes, not days |
| **Consumer** | At home, on a phone | See what it looks like, find out what it costs, ask for a quote |

---

## 4. Walkthrough: the marketing designer builds a catalogue

**Goal:** publish a catalogue that every dealer sees, without waiting on a print run.

1. She opens **Dealer Kit → Catalogue Pages** and creates a page.
2. She builds it by adding blocks to a canvas: a heading, some text, an image, a grid of
   products, a bundle offer.
3. For the product grid, she chooses which products appear in one of two ways:
 - **By rule** - "every basin in this category under RM 800". The page then keeps itself
     current: a new basin that matches simply appears.
 - **By hand** - she picks the exact products she wants featured.
   She can also combine the two, and remove individual products she does not want. Removing
   always wins over including, so she can never be surprised by something she took out.
4. She decides **what each product tile shows** - photo, name, code, price - and can save that
   as a reusable style so every page in a campaign looks the same.
5. She checks the page on **desktop, tablet, phone and paper**, because dealers use all four.
6. She hits **Publish**.

**What she gets that she does not have today:**

- **Publishing never destroys the old version.** If today's version has a mistake, she rolls
  back and the previous one is live again in seconds. Nothing was overwritten.
- **A preview she can share before it goes live**, so a manager can approve it without every
  dealer seeing it first.
- **Reusable product sets.** If she saves "Spring Promotion" as a set and uses it on four pages,
  editing it once updates all four. No hunting.

---

## 5. Walkthrough: the dealer in the showroom

**Goal:** answer "what will it look like and what does it cost" while the customer is standing
there.

1. The dealer opens the catalogue, or goes straight to **Room Designer**.
2. **The room.** The screen starts with a simple 4m x 3m room. The dealer drags the corners to
   match the customer's actual room. Each wall shows its length in millimetres **as they drag**,
   so they can match the customer's measurements exactly. The floor area updates itself - nobody
   types it.
3. **The products.** They pick products from the same catalogue the customer was just looking
   at. Each one appears in the room at its **real size**.
4. **Arranging.** They drag things around, rotate them, remove them. Two views of the same room:
   a plan from above, and a 3D view they can spin around for the customer. Both always agree,
   because it is one room, not two drawings.
5. **The summary.** Down the side: every product, how many, the price at this dealer's level,
   the room area, and the total.
6. **Save.** The design is theirs. Reopening it tomorrow brings back the room and everything in
   it.

### Three things the dealer will notice, all deliberate

- **Products are shown as accurate boxes, not photo-realistic models.** Every product in the
  catalogue has real measurements, so every product works from day one and each box is exactly
  the right size. Photo-realistic models would only exist for a handful of items and be missing
  for the rest, which is worse. The customer sees genuine scale and fit; they are looking at the
  real product photo in the catalogue alongside.
- **If a product has no measurements recorded, its box is drawn at a default size and clearly
  says so, naming the product.** A wrongly-sized box that looks confident is far more damaging
  than one that admits it is a placeholder. This also tells the data team exactly which products
  need measuring.
- **A discontinued product stays in the design, marked, and is left out of the total.** It is
  not silently deleted - the customer chose it and deserves to be told. It is also not counted,
  because a total including something unbuyable is a promise we cannot keep.

---

## 6. Walkthrough: the consumer at home

**Goal:** browse, try it in their own room, ask for a quote - without an account.

1. They follow a link (from WhatsApp, an email, a QR code on a leaflet).
2. They see the published catalogue at **consumer prices**. Dealer and internal pricing simply
   are not there.
3. They can do the same room exercise: shape the room, add products, look at it in 3D.
4. They confirm, and a **request goes to the dealer** - not an order. A consumer cannot place an
   order directly; a person always handles it.

The consumer never creates a password. If they have contacted Sorento before, the system already
knows who they are from their phone number.

---

## 7. Walkthrough: office staff sending a PDF

Some customers still want a document.

1. Office staff open a published catalogue page and choose **Export PDF**.
2. They choose **who it is for** - staff, dealer, or consumer.
3. They get a PDF priced correctly for that audience.

The PDF is produced from the actual page, so it cannot drift from what is on screen. And because
the audience is fixed at the moment of the request, internal prices cannot accidentally end up
in a document sent to a customer.

---

## 8. What the system works out so nobody has to type it

This is the design principle behind the whole thing: **if a user is typing something we already
know, that is a fault in the product.**

| Not asked | Because |
|-----------|---------|
| Product sizes | Already in the catalogue |
| Prices | Worked out for whoever is looking, at that moment |
| Whether something is available | Checked live |
| Room area | Calculated from the shape they drew |
| The total | Added up from the choices |
| The dealer's company and price level | Known from who is signed in |
| The customer's contact details | Known from the link they followed |

---

## 9. One rule worth understanding: prices are never stored in the document

A catalogue page does not contain prices. It contains *instructions* - "show this set of
products here". The price is worked out when someone opens it, for that person.

**Why this matters to you:**

- One published catalogue serves staff, dealers and consumers, each seeing their own prices.
  There are not three versions to keep in step.
- When the price list changes, every catalogue is instantly correct. Nothing to republish.
- A price a person is not entitled to see is **not sent to their device at all**. It is not
  hidden on the page where a curious person could dig it out.

The same applies to a saved design: it records *what* the customer chose, never *what it cost*.
Reopen it in three months and it prices itself against today's list, which is the only honest
answer.

---

## 10. What is ready, and what is not

### Ready to demonstrate

- Building and publishing catalogue pages, with rollback
- Product photos on tiles, with trade-only imagery withheld from consumers
- Product sets, defined by rule or by hand, reusable across pages
- Tile styling
- Bundles - several products sold at one price, with the parts listed underneath
- The public catalogue page
- PDF export at the right prices for the chosen audience
- The room designer: draw the room, add products, plan and 3D views, live wall dimensions
- Saved designs that reopen
- Connecting a WhatsApp contact to the customer account they buy under

### Not built yet

| Missing | What it means in practice | Why not yet |
|---------|---------------------------|-------------|
| **Turning a design into a quote** | The dealer can save a design but cannot yet press "send as quote" | The business has never defined what a quote *is* - see §11 |
| **Upload a floor plan photo** | The dealer draws the room by hand, which works but takes a minute longer | Drawing had to exist first; upload is a shortcut on top |
| **Editing a saved product set from the library** | A set can be created and reused, but changing it means going into a page | Known gap, needs prioritising |

### Not started (the rest of the nine packages)

Stock check (already exists in the CRM, needs surfacing here), warranty, display rack, product
knowledge, extra discount, exhibition request.

---

## 11. What we need from product

These are business decisions. Engineering cannot pick them.

### 11.1 What is a quote? - *blocking*

The dealer designs a room, presses confirm, and then... what exactly?

- Does the quote get a number, and who issues it?
- Does it expire? After how long?
- Who owns it - the dealer, or Sorento?
- Does anyone approve it before the customer sees it?
- When the customer accepts, how does it become an order?

Until these are answered, the journey stops one step before its payoff. Everything else is ready
for it.

### 11.2 Confirm: a consumer can never order directly

We have built on the assumption that a consumer confirming a design sends a **request to the
dealer**, never an order. Please confirm, because it is expensive to change later.

### 11.3 Are accurate boxes good enough to sell?

The 3D view shows correctly-sized boxes with product names, not photo-realistic furniture. Our
view is that honest scale beats partial glamour, and it works for the whole catalogue today.
If sales believe photo-realism is required to win dealers, that is a separate investment and we
should scope it now rather than discover it in a demo.

### 11.4 Only 7% of products have a photo - *this decides how the launch looks*

Of 17,402 sellable products, **1,363 have a photograph** attached. The other 93%
will render as a clean "no image" tile.

Nothing is broken: the catalogue shows a photo the moment one exists, and it is already
withholding trade-only imagery from consumers. But a brochure generator is judged on how it
looks, and today most of the range has nothing to show.

This is a content job, not an engineering one, and it is the single biggest lever on whether
a dealer finds this impressive or embarrassing. Worth deciding:

- Which range gets photographed first? A complete bathroom category demonstrates far better
  than a thin scattering across everything.
- Who owns getting them in? Photos attach to a product in the existing CRM screens.
- Is a placeholder acceptable at launch for the long tail, or should unphotographed products be
  excluded from published pages until they have one?

A second observation from looking at the ones that DO exist: many are technical line drawings
rather than product photography. They are legitimate images and they render, but a dimensioned
outline drawing is a different thing from a photograph of a tap in a bathroom, and it changes
how a catalogue page reads to a consumer. Worth a decision on which of the two the tile should
prefer when a product has both.

A related note: the same screens also attach PDFs and videos to products. Those are correctly
ignored as tile photos - a spec sheet where a product picture should be looks like a fault.

### 11.5 Nobody's phone number is on their customer record

The system links a WhatsApp contact to the customer account they buy under by matching phone
numbers, and it proposes the match for a human to confirm rather than applying it silently.

Against today's data it can propose **nothing**: of 3,284 customer records, **7 have a phone
number**, and of the 55 WhatsApp contacts, **none** match one. The separate "contact people"
table that could hold them is completely empty.

The consequence is not a broken feature - the link works, and a person can make it in a couple
of clicks - but every link will be manual, and anything downstream that wants to know "which
account is this consumer buying under" will have to ask. If quotes are to flow automatically
from a consumer's design to the right dealer account, capturing phone numbers on customers is
the prerequisite.

### 11.6 Which of the remaining six packages comes next?

Stock check is the cheapest - it already exists and needs surfacing. Warranty is the most
designed. Everything else is greenfield.

---

## 12. Frequently asked

**Does the dealer need internet?** Yes. Everything is live, which is what keeps prices and
availability correct.

**Why do most products show no picture?** Only 7% currently have a photo attached. See §11.4.

**Can a dealer see Sorento's cost?** No. Internal pricing is never sent to a dealer's device,
regardless of settings.

**What if two dealers want different prices?** That is exactly the design - one catalogue,
prices resolved per viewer.

**What happens when a product is discontinued mid-campaign?** Catalogue pages built by rule drop
it automatically. Saved customer designs keep it, marked as unavailable, and exclude it from the
total.

**Can a customer share their design?** They can reopen it. Sharing by link is a small addition
once quotes are settled.

**Does this replace the printed catalogue?** It can produce the PDF that gets printed, from the
same source, so the two can never disagree.
