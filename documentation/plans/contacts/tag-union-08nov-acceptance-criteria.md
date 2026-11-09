# UAC - TAG-UNION (contact tags add up)

Plan `PLAN-tag-union-08nov.md`, card `CARD-tag-union-08nov.md`.

- U1 A contact with tag A (companies Sorento) and tag B (companies Mocha) holds both companies; same for access
  types, segments, attachment types, brands, item classes, regions, warehouses shown, specs shown.
- U2 Any tag "All brands" / "All classes" gives All.
- U3 Every switch adds up: any tag on = on (AI replies, stock checks, escalation, packing list, notify salesman,
  messaging, portal forms, field reveals, agents, agent fields, image / voice access, skip date-range questions,
  files as links, ETA buffer).
- U4 Restrictions only when every tag says so: excluded warehouses / hidden specs intersect, "hide empty
  locations" and "requires registered project" need every tag that sets them.
- U5 Include list on one tag, exclude list on another resolves to the exclude list minus the include list.
- U6 Limits and memory level: the highest; stock mode: the loosest.
- U7 An inactive tag counts for nothing (settings, AI model, dealer check, Differs count).
- U8 Adding a tag writes its grants at once; removing it removes what only it granted; editing or switching off a
  tag updates every holder at once; deleting a tag does the same.
- U9 A company a person added by hand survives the removal of a tag; a company a person removed by hand stays
  removed when a tag changes; a switch a person changed by hand keeps its value.
- U10 A setting nobody touched goes back to its value from before tags set it when the last tag setting it goes.
- U11 Existing contacts: a value that differs from today's tag result is kept as an own change.
- U12 "Apply settings" (name unchanged) resets the contact to its tags, preview first.
- U13 Adding / removing a tag that sets companies needs superadmin (403 otherwise); stock / agents / messaging their
  rights; the same for switching the tag active / inactive and for the WhatsApp agent path.
- U14 Script: dry run reports the counts and writes nothing; `--apply --expect N` refuses on a mismatch and writes
  with one audit row per changed contact.
- U15 Contact Tag settings section says "Own change" where it said "Differs".
