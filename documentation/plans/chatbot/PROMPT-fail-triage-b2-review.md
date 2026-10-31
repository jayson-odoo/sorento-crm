# Parser text review: chatbot failure triage, batch 2

For the owner to review before pasting into production. The exact edits are in
`PROMPT-fail-triage-b2-e90461ef.patch`. Whole new text: `crew/state/eval/fail-triage-b2/texts/E.txt`, kept with crew.

- Base: production parser text, md5 `57d7d4126f28b8df812e2be2de3a3893`.
- Result: md5 `e90461efac72529ef0df7138e726593c`.
- Size: 7 edits, 2 existing lines changed and 5 lines added. Nothing removed.

## The 7 edits

| # | Where | What changes for the contact | Example message |
|---|---|---|---|
| 1 | `portal_link` line | "price tag request" joins the forms the bot can link to. | "give me link to request pricetag" |
| 2 | New `portal_form` key | The parser names which form was asked for, so the link opens on that form. Measured on today's text: it names none, even for a complaint. | "link for complaint form" |
| 3 | New line after the bare family code rule | A size stuck on the end of a code is read as the code plus a size. Before, the whole thing was one unknown code and the contact got "Couldn't find". | "SRTWC286200MM" answers the two 200 mm variants |
| 4 | `specification` rule, one clause | Lets edit 3 work: a size stuck on a code may be used though no candidate line offered it. No other spec is affected. | Same as edit 3 |
| 5 | New line in `ROUTING` | A team the contact names wins. One team named: routes there. A word that fits several, or none: the bot asks which, instead of guessing one. | "Please escalate to product marketing team"; "escalate marketing" asks which marketing team |
| 6 | New line in `ROUTING` | A domain from the routing map always fills the team, on every ask. Needed because the other edits made the model drop the team on plain questions. | "stock for SRTWC8122" records team warehouse |
| 7 | New line in `LAST PURCHASE COST` | "my cost", "dealer cost" and "costing" read as a cost ask. The code then decides by who asks: a dealer tag gets their promotions, a holder of the permission gets supplier cost, anyone else "not allowed". | "my cost for MWC8154-RL-P" |

Edit 3 only answers the right variants with the code in #2030, and the price tag link in edit 1 needs #2018. Both are on main before this text goes in.

## What was measured

| Check | Today's text | New text |
|---|---|---|
| Hidden set, whole message read right, 2 runs, 226 readings | 181 | 181 |
| Hidden set, team filled, per run of 113 | 102, 101 | 105, 107 |
| 36 written test messages for these edits | 17 of the first 32 | 35 of 36 |

So the new text reads messages no better or worse overall, and does the 7 new things.

## Known misses, your call

- A size stuck on a code is read right about 9 times in 10 (13 of 15), not always. The miss falls back to today's "Couldn't find".
- "can the sales team call me" passed on this text but missed on a near-identical earlier one (it went to customer service), so it may not be stable.
- On the hidden set, one follow-up pick reads worse in both runs, and on 3 messages the new text always sets a team where today's never does. Crew holds these; the texts are sealed from the lane, so ask crew to show you them.
- Edit 6 sets a team on some plain questions where today's text sets none. I read that as what the rule always meant, but it is a change.

## When you paste it

1. After the release. Check production's parser text is md5 `57d7d412...` first. Only restored copies were checked, never production itself. If it differs, stop: the gate was on this base, so tell crew.
2. Paste the whole new text as a new version and confirm md5 `e90461ef...`, then move the label. No other edit without a new gate.
3. Set Tier = Dealer on the tags "Sorento Dealer Brand", "Sorento Mocha Dealer Tag" and "Mocha Dealer Tag". Until then every dealer keeps today's "not allowed".
4. Do NOT press Apply on those tags. It writes the tier onto every contact holding them and changes what the parser sees, and this text was not tested that way.
