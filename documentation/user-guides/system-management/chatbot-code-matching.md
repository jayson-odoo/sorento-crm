# How the chatbot matches a product code it cannot find

When someone asks the chatbot about a product code that is not in the catalogue exactly as typed, the bot looks for close codes and offers them. It answers on its own only when it is sure. This page explains what the bot does, so you can tell a customer or dealer what to expect.

## When the bot answers straight away

The bot answers without asking only when:

* the typed code is a catalogue code with only spaces, dashes or capital letters different (`srtwc 8354 sh uf` is answered as SRTWC8354-SH-UF), or
* the typed code is a registered product set (typed with or without its dashes).

Everything else is offered, and the bot asks which one was meant. It never answers a guess.

## What an offer looks like

> Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?

With more than one close code, the bot lists up to three, numbered:

> Couldn't find SRTWC286-150. Did you mean:
>
> 
> 1. SRTWC286-SH-150
> 2. SRTWC286-SH-NEW-150
> 3. SRTWC286-SH

* Reply with the number (or "yes" when there is one option) to get that product's answer. The quantity typed in the first message is kept.
* Codes that hold every part that was typed (for example both "SH" and "150") are listed first.
* Inactive products and products hidden from the chatbot are never offered.
* When a message names several codes, each code that is not found gets its own list, in the same order it would get on its own. Codes already answered in the same reply are not offered again.

## Dealers

Dealers now get the same close-code offer instead of "Please refer to your salesman." The offer only shows codes of the dealer's own company. When there is no close code, or the dealer answers "no", the reply is still "Please refer to your salesman."

## Product sets

A registered product set (Products > Product Sets) is answered as the set when its code is typed with only spaces, dashes or capital letters different: `cwc604prl`, `cwc604-p-rl` and `cwc604 p rl` all give the set CWC604-P-RL, with its member products' stock. Only that set is answered, never the longer set codes that start with it (typing CWC605-RL does not also answer CWC605-RL-SOFT). Other punctuation does not count: `cwc604/p/rl` is not the set. The same holds when the last part of the code is typed as a separate word on the same line: `CWC605-RL soft x 1` is the set CWC605-RL-SOFT. A word on the next line never joins the code above it, and a word that completes no real code changes nothing.

When the typed code is close to a set but not the same:

* If only one set holds every part that was typed, that set is offered first, then its member products.
* If several sets hold every part that was typed (`cwc604-rl` is close to CWC604-P-RL, CWC604-S-RL and their -NEW versions), the bot offers those sets, up to three, so the person picks which one they meant.

When a dealer types a set WITH a quantity (`CWC604-P-RL x 2`), the bot answers each part of the set at that quantity, one line per part, the same way it answers a single code ("CWCX604-P-RL x 2: Got stock.", "CWCY604 x 2: Only 1 got stock."). A part that counts more than once in the set is asked at that multiple. A part also typed on its own in the same message is asked at the total. With no quantity, the bot still asks how many units are needed; one number in reply (for example "4") counts for every part of that set. After the parts of one set were answered, a new number on its own ("4") asks again for every part at that quantity.

Picking a set gives the same answer as typing the set code. A set with a member the dealer may not see is never offered or answered.

A product counts as part of a code's family only through the catalogue: its code starts with that code, its **family code** was set to that family, or it is a member of a registered set headed by that code. The bot does not guess a family from letters inside a code. If a product whose code does not start with its model code (for example a pan coded with an extra letter) does not come up when someone names the model code, set its family code or register a set that holds it.

## Sizes

The bot never assumes a size. A size comes only from the size stored on the product (the size field the Spec Registry gives the product's category, for example the trap outlet length of a water closet) or from a number in the typed code that equals a stored size.

* Offers show each code's stored size on its own line, for example "Trap outlet length: 300 mm", or "not recorded" when the product has none.
* A size that no product in the family stores reads: "Couldn't find SRTWC8152-SH-UF with size 400 mm. Did you mean:" followed by the family's codes and their stored sizes. Nothing is answered.
* These size rules apply when a message names one product code. A message with several codes and a size is answered as before.

To make sizes show, fill the size field on each product. Admins can list the active products with no stored size with the read-only report `scripts/chatbot_products_without_size.sql` (ask the system team to run it).

## Checking what the bot considered

In the Chatbot Console, open a turn's trace: the `code_candidates` entry lists every close code the bot considered for a code it could not find, in the order offered, and whether each was offered or answered. A set answered from a typed code also gets an entry, listing the set and its member products.
