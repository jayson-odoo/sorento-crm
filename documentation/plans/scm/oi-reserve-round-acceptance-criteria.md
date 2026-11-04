# UAC: reserve email button opens that email's lines (OI-RESERVE-ROUND)

Plan: `PLAN-oi-reserve-round.md`. Card: `oi-reserve-round-behaviour-card.md`.

## Backend: the link

- **AC-1** An email built from ONE request context keeps `reserve.link` =
  `<OI link>?reserve=<request id>` (request email and reserved notice alike).
- **AC-2** An email built from several contexts of the SAME OI (parked notices sent together)
  links `<OI link>?reserve=<id1>,<id2>`: distinct request ids, first-seen order. Two contexts
  of the same request give one id.
- **AC-3** An email covering two or more OIs links
  `<list link>?display=lines&inquiry_no=<OI nos sorted, comma-joined>&reserve_request=<request ids
  in the same OI order, comma-joined>`. No "and N more" cap: a 21-OI email carries 21 ids.

## Backend: the list filter

- **AC-4** `GET /api/v1/order-inquiries?reserve_request=<a>,<b>` returns exactly the OI rows
  named by the request rows of requests a and b, whatever their answer: open (`qty_reserved`
  NULL), fully reserved, partly reserved, rejected (0). It returns no row of the same OI that
  was not asked, and no row asked only in another request. The summary and export routes
  apply the same filter.
- **AC-5** A `reserve_request` value that is not a UUID answers 422, like the list's other id
  filters.

## Frontend: the OI page (one-OI link)

- **AC-6** Opening `/order-inquiries/<OI>?reserve=<request id>` shows only the lines that
  request asked for, in every state; the "Request" dropdown shows `Request #<ordinal>` ticked;
  the State filter is empty.
- **AC-7** Clearing the Request dropdown shows every line; ticking two requests shows the lines
  of both. `?reserve=<id1>,<id2>` ticks both.
- **AC-8** `?reserve=needs_reserve` or `parked` still preselects State "Request to reserve";
  `reserved` / `notice_parked` still preselect nothing; an id that is not one of this OI's
  requests narrows nothing.
- **AC-9** The Request dropdown is absent when the OI has no reserve request.

## Frontend: the OI list (two-or-more-OI link)

- **AC-10** Opening `/order-inquiries?display=lines&inquiry_no=a,b&reserve_request=x,y` sends
  `reserve_request=x,y` (with `inquiry_no`) on the list and summary calls, shows a chip
  "Reserve requests: 2", and the chip's clear and "Clear filters" both drop the param from the
  URL and the calls.
