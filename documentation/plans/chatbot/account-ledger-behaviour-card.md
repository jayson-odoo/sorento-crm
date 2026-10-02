# ACCOUNT-LEDGER behaviour card (2 Oct 2026)

"account 1" in a chatbot message selects the `[A/C I]` ledger of the customer it names.

## Today (main 066b966e6, traced)

- Parser has no account/ledger field; the words stay inside the entity `raw`
  (`app/services/chatbot/head/parser.py:139-186` entity schema).
- Linked (enforced) contacts: `ContactCustomerScope.match_words`
  (`app/services/contact_customer_scope.py:61-76`) is a substring match on linked names, so
  "Soon Heng account 1" matches nothing and refuses; called from
  `engine._customer_scope_gate` (`app/services/chatbot/engine.py:1380-1433`).
- Staff: `entity_resolver._probe_customer` (`app/services/entity_resolver.py:1069-1151`) then
  the gate groups every ledger of one trading name into one picker line
  (`ledger_family.py:44-60`, `turn/narrow.py:84-160`, `lanes/business/gate.py:975-1060`),
  so a staff "Soon Heng account 1" today gets the whole family (I-IV + bare + PROJECT ...).

## Proposed rules

1. Parser emits a new per-entity key `account` on customer entities: the ledger number the
   message names, as a roman numeral `"I"`..`"X"`, else null. Triggers: "account 1",
   "acc 1", "a/c 1", "A/C I", "ac2", "akaun 2", "户口1"; arabic converted to roman. The account
   words are removed from `raw` ("Soon Heng account 1" -> raw "Soon Heng", account "I").
   A bare "my account" (no number) is NOT an account signal (stays `self_reference`).
2. A customer row's ledger = the `A/C <n>` marker inside any bracket of its name
   (`[A/C I]`, `(A/C I)`, `(A/C 2)`, `[A/C II]-( KL OUTLET)`); arabic and roman compare equal.
   A row with no A/C marker (bare name, `(PROJECT)`, `[CERAMIC]`, `(SRT)` ...) is no numbered
   ledger, so it is excluded when an account is asked.
3. No `account` -> behaviour unchanged (name covers every ledger, as today).
4. Linked contact: name words match as today, then keep only links whose ledger equals
   `account`. Nothing left -> refuse, naming the ledgers of THAT name the contact IS linked
   to (never an unlinked ledger: that would leak other accounts exist).
5. Staff: resolver rows for that customer word are narrowed to the asked ledger before the
   family grouping, so the picker / answer carries that ledger only. Name has no such
   ledger -> refuse naming the ledgers the name has.

## Real examples (dev data: sorento_ai_automation_0925 customers, sorento_cagent_stack links)

| # | Who | Message | Today | Proposed |
|---|-----|---------|-------|----------|
| 1 | contact 80560c8f (12 links incl. SOON HENG HARDWARE CO.SDN.BHD. [A/C I], HANLIM TRADING SDN BHD bare/[CERAMIC & ELLECI]/[A/C I..IV]) | "Hanlim account 2 outstanding" | all 6 HANLIM links | HANLIM TRADING SDN BHD [A/C II] only |
| 2 | same contact | "Soon Heng account 1 sales" | refused (no linked name contains "soon heng account 1") | SOON HENG HARDWARE CO.SDN.BHD. [A/C I] |
| 3 | same contact | "Soon Heng account 2" | refused | refuse: "You're linked to SOON HENG HARDWARE CO.SDN.BHD. [A/C I] only." |
| 4 | contact 046a9d73 (1 link: HANLIM TRADING SDN BHD [A/C II]) | "my account 1 outstanding" | UNVERIFIED: depends on what raw the LLM emits for "account 1" | refuse naming [A/C II] |
| 5 | staff | "Soon Heng account 1 outstanding" | UNVERIFIED: raw "Soon Heng account 1" likely matches no name; raw "Soon Heng" gives 3 family lines each folding every ledger | picker of 3: SOON HENG HARDWARE [A/C I] (300-S002), PLUMBING [A/C I] (300-S037), TRADING [A/C I] (300-S254) |
| 6 | staff | "Soon Heng Trading account 2" | whole TRADING family | refuse: SOON HENG TRADING has accounts I, III and IV (no [A/C II] row exists) |

## Edge cases

- "account 3" on a name with only I, II -> refusal listing I, II (rule 4/5).
- Number above any ledger seen ("account 7"; data max is `[A/C V]`, CHIP BEE TRADING COMPANY) -> same refusal.
- "my account 1" (linked contact): links filtered to [A/C I]; several left -> answered together, as "my" is today.
- Staff "my account 1": staff "my" means its links (engine.py:1398-1400) -> same filter on links.
- Two customers, two accounts ("Hanlim acc 2 and 1 Living acc 1"): per-entity key keeps each right.
- Account said with no customer and no "my" ("account 2 outstanding" after "Hanlim" last turn): applies to the carried customer.
- Data quirk (UNVERIFIED cause): the bare SOON HENG HARDWARE row shares code 300-S002 with [A/C I] (6 vs 79 orders); `(CERAMIC & ELLECI)` shares 300-S132 with [A/C III].

## Questions (recommendation first)

1. Bare / PROJECT / CERAMIC rows on "account 1": (a) excluded, marker match only [rec: simplest, matches what the user typed]; (b) also include rows sharing the [A/C I] row's customer_code (pulls the bare 300-S002 row in).
2. "account N" with no customer named this turn: (a) applies to the carried customer / "my" links [rec]; (b) ignored unless a name is in the same message.
3. Linked contact asks a ledger it is not linked to: (a) refuse naming only its linked ledgers of that name [rec: no leak]; (b) generic refusal line unchanged.
4. Staff asks a ledger the name lacks: (a) refuse naming the ledgers it has [rec]; (b) fall back to the whole family with a note.
5. Prompt rollout: (a) new UNLABELLED parser prompt version via migration, owner moves `production` label; kept to one small addendum so PR #1405 (PROMPT-DYNAMIC) rebases cleanly [rec]; (b) wait for #1405 and add it as a variable block.
