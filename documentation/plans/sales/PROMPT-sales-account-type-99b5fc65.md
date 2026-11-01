# Parser prompt change, SALES-ACCOUNT-TYPE PR 2

Base: production parser text md5 `57d7d4126f28b8df812e2be2de3a3893`. Result: md5 `99b5fc650abed7a2c063ab4701370771`. Not published; only the owner moves the production label. On another base (#2030's text E), apply the same five edits by these anchors, then re-run gold before use. Gate results and limits: plan section 6.

## Edit 1, a line after the line starting `  - brand → a name from the Brand candidates block`

```text
  - account_type → the account type of a customer's ledger (see the ACCOUNT TYPE rule below)
```

## Edit 2, in the line starting `Each entity:`, replace `"confident": true|false }` with

```text
"confident": true|false, "kind_said": the word of this message that says what kind this entity is ("brand", "account", "account type", "debtor type"), else null }
```

## Edit 3, in the line starting `group_by also takes`, replace `"channel" (dealer / project);` with

```text
"channel" (dealer / project), "account_type" ("by account type", no entity for it);
```

## Edit 4, replace the line `and group_by may also be "month" or "year".` with

```text
and group_by may also be "month" or "year", only when the message asks that split ("by month", "monthly", "breakdown by month", "ikut bulan", "按月"). A month or year named as the period ("in Jan", "Jan 2026", "for 2026") sets date_filter_start and date_filter_end with group_by null.
```

## Edit 5, at the end of the line starting `== BRAND CANDIDATES:`, add

```text
 A brand entity whose name the message calls a brand ("cabana brand", "brand cabana") has kind_said "brand" (see ACCOUNT TYPE).
```

and on the lines right after it, this block:

```text
== ACCOUNT TYPE: entities[].hint "account_type" == The user block may carry a "Known account types:" line, built fresh every turn: the account types stored on the customers' ledgers. On a sales or outstanding ask:
  - These stay what they are, never account_type, unless the message says account type: "top accounts" are customers (group_by "customer"); a customer named with a number ("ZZT TRADING a/c 3") is ONE customer entity with account 3 and no account_type entity; "project" is sales_channel.
  - Otherwise a word on that line and in no Brand candidates block, or a number or tag the message calls an account type with no customer named for it ("account type 4", "account 4", "A/C IV", "debtor type 4"), is an entity {raw: the word, number or tag only ("ceramic", "4", "A/C IV"), hint: "account_type", canonical_code: null, hint_confident: true}.
  - A word in both keeps the kind the message says. Neither said -> hint "brand", kind_said null (the assistant asks which).
  - kind_said is the word of THIS message that says the kind, else null: "cabana brand", "brand cabana", "for sorento brand" -> {raw: "cabana", hint: "brand", kind_said: "brand"}. "cabana account" -> {raw: "cabana", hint: "account_type", kind_said: "account"}. "cabana debtor type" -> {raw: "cabana", hint: "account_type", kind_said: "debtor type"}. The kind word is never a raw itself. An earlier turn never fills it.
  - No "Known account types:" line this turn: a bare word is no account_type entity. A number the message calls an account type still is.
```
