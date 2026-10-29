# UAC: chatbot lookup lists + list-free prompt version (CHAT-SLIM-INDEX build, 25 Oct 2026)

Plan: `PLAN-chat-lookup-lists-25oct.md`. Customer names masked (public repo).

## Gate and today's input
- AC-1 A parser version WITHOUT the "== LOOKUP LISTS ==" line (prod v63) gets a user turn byte-identical to today for
  the same message and state (no candidate block, every per-turn list line unchanged).
- AC-2 A version WITH the line gets the candidate blocks and NO per-turn Product types, Product details, Known brands,
  Promotion kinds or Sales channels line.

## Candidate blocks (version with the line)
- AC-3 Each list prints at most one block: header "<Noun> candidates (pick one only if the message means it):" then
  one "- <label>" line per kept row; a list with no kept row prints nothing.
- AC-4 Categories: "water closet", "tandas", "马桶", "wc" offer the water-closet class / categories; a category that is
  not searchable (is_searchable false) is never offered.
- AC-5 Sales channels: "dealer only" offers "- dealer"; "channel project sahaja" offers "- project".
- AC-6 Spec words: a colour / finish / material / bowl / trap word (any language, typo) offers the matching spec
  value(s).
- AC-7 Spec numbers: "200 mm", "200mm", "20 cm" all offer every spec holding the stored value 200 mm, named with the
  spec ("- trap length 200mm", "- width 200mm"); a number held by no spec offers nothing.
- AC-8 File types / certificate kinds: "gambar", "lukisan", "sijil" offer photo / drawing / certificate.
- AC-9 Brands: "srt" offers SORENTO (alias from the brand_alias lookup set); the label is spelt as the brand list
  spells it ("- SORENTO (SRT)").
- AC-10 Salespeople, locations, promotion kinds, customers: a name / short code / kind word in the message offers the
  row; customers at most 5 lines.
- AC-11 One-span-one-list: a piece that is exactly a brand name / code / alias offers no category or customer rows; a
  piece that is exactly a category, channel or location word offers no customer rows ("srt a3 flyer": no category
  block; "tiles" alone: no customer lines from the word "tiles" when it is a category word).
- AC-12 Product codes and DO / SO / PO numbers are never offered in any block (today's exact path after the parser).
- AC-13 Embedding call fails or times out: blocks are built from spelling only and the turn answers normally.
- AC-14 The blocks and their pieces appear in the turn trace.

## Prompt version
- AC-15 Migration `lkp_0001` publishes exactly one new parser version, UNLABELLED, built from the production-labelled
  text at migration time: every list span removed, rule text naming a removed per-turn line renamed to its block, the
  marker line added. Running it twice publishes nothing new. The production label does not move.
- AC-16 Any anchor missing or found more than once: nothing is published, the reason is logged, the upgrade succeeds.
- AC-17 Applied to a text that also carries SALES-TARGET-CHAT's sales_target / opportunity inserts, every removal
  applies and both inserts survive unchanged.
- AC-18 The new version is at most ~131k characters (v63 140,897 minus the list spans).

## Owner hand test (crew copy, label moved for the window)
- AC-19 "Dealer <customer F> oct total sales for water closet" -> one reply, F's October total for water closet; no
  customer pick on "water", no promotion file.
- AC-20 "dealer only" after a sales-agent ranking -> the ranking re-run for dealer.
- AC-21 "srt a3 flyer" -> the SORENTO A3 flyer (risk: prompt-dependent).
- AC-22 A spec size, a brand, a salesperson, a location and a customer name each reach the right row.
