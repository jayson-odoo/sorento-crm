# How the chatbot matches a product code it cannot find

When someone asks the chatbot about a product code that is not in the catalogue exactly as typed, the bot looks for
close codes and offers them. It answers on its own only when it is sure. This page explains what the bot does, so you
can tell a customer or dealer what to expect.

## When the bot answers straight away

The bot answers without asking only when:

- the typed code is a catalogue code with only spaces, dashes or capital letters different
  (`srtwc 8354 sh uf` is answered as SRTWC8354-SH-UF), or
- the typed code is a registered product set (typed with or without its dashes).

Everything else is offered, and the bot asks which one was meant. It never answers a guess. This includes a code that
is only the start of one catalogue code (for example a typed `SRTWC83` when only `SRTWC8354-SH-UF` starts that way): the
bot offers it and asks, for staff and dealers alike. A code followed by a colour or finish word (`SRTWT8259 gold`)
is also offered ("Did you mean SRTWT8259-GLD?"): one "yes" gets the answer.

The bot also offers close codes in these cases:

- a code made of letters only, typed among other codes in the same message;
- a code typed inside a longer code;
- a code that is not found right after the bot asked "How many units?" or asked which product was meant. The close
  codes are numbered on after that question's own options, in the same reply;
- an incoming stock or ETA question. The dealer can reply "yes" or a number to pick the offered code.

## What an offer looks like

> Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?

With more than one close code, the bot lists up to three, numbered:

> Couldn't find SRTWC286-150. Did you mean:
> 1. SRTWC286-SH-150
> 2. SRTWC286-SH-NEW-150
> 3. SRTWC286-SH

- Reply with the number (or "yes" when there is one option) to get that product's answer. The quantity typed in the
  first message is kept.
- Codes that hold every part that was typed (for example both "SH" and "150") are listed first. They are chosen from
  the whole list of close codes, not only the first few found.
- Inactive products, discontinued products and products hidden from the chatbot are never offered.
- A code is never shown twice in one reply.
- When a message names several codes, each code that is not found gets its own list, in the same order it would get on
  its own. Codes already answered in the same reply are not offered again.

## Dealers

Dealers get the same close-code offer, up to three codes, instead of "Please refer to your salesman." The offer only
shows codes of the dealer's own company; codes from another company are never offered. This also holds for incoming
stock and ETA questions: when a close code is offered, the reply does not say "Please refer to your salesman." When
there is no close code, or the dealer answers "no", the reply is still "Please refer to your salesman."

## Product sets

When the typed code is close to a registered product set (Products > Product Sets), the set is offered first, then
its member products. Picking the set gives the same answer as typing the set code. A set with a member the dealer may
not see is never offered.

A product also counts as part of a code's family when its **family code** was set by hand to that family, or when it
is a member of a registered set headed by that code. Setting the family code on a product is how you link a product
whose code does not start with its model code.

## Sizes

The bot never assumes a size. A size comes only from the size stored on the product (the size field the Spec Registry
gives the product's category, for example the trap outlet length of a water closet) or from a number in the typed code
that equals a stored size.

- Offers show each code's stored size on its own line, for example "Trap outlet length: 300 mm", or "not recorded"
  when the product has none.
- A size that no product in the family stores reads: "Couldn't find SRTWC8152-SH-UF with size 400 mm. Did you mean:"
  followed by the family's codes and their stored sizes. Nothing is answered.
- These size rules apply when a message names one product code. A message with several codes and a size is answered
  as before.

To make sizes show, fill the size field on each product. Admins can list the active products with no stored size with
the read-only report `scripts/chatbot_products_without_size.sql` (ask the system team to run it).

## Checking what the bot considered

In the Chatbot Console, open a turn's trace: the `code_candidates` entry lists every close code the bot considered for
a code it could not find, in the order offered, and whether each was offered or answered. For each offered code it also
shows whether that code holds every part the customer typed. When nothing close was found, the entry reads
`no_candidate`.
