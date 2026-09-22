# Chatbot - photos and voice notes

Use this when a WhatsApp contact sends a photo of a stock list or product codes, or a voice
note, instead of typing. The bot reads the photo or listens to the voice note as part of the
same reply, no separate step and no separate message from the automation team.

## Sending a photo with no words

Send a photo on its own, with no caption and nothing already asked. The bot reads every
product code it can make out and opens its reply with one line naming all of them, then asks
what to do with them:

> I read M486-75-BL, M483-BL and MBF 9902 from that photo. What would you like me to do with
> it?

Reply with what you want, for example "check stock", and the bot answers for exactly those
codes, the same as if you had typed them.

**A code the bot could not find is named, never dropped.** If one of the codes you sent a
photo of does not match anything, the bot still lists everything it read, then says which one
it could not find:

> I read M486-75-BL and M483-BL from that photo. Couldn't find MBF 9902. What would you like
> me to do with it?

**The "I read ..." line always lists every code, never a count or "and more".** If a photo
holds more codes than the bot is allowed to take in one go, it takes the first ones (the
number is set in **Settings > Chatbot Media > Maximum entities per image**) and says so:

> I read A, B, C, D, E, F, G, H, I and J from that photo. There was more than I can handle in
> one go, so I have taken the first 10.

## Asking first, then sending the photo

If you already asked something (for example "check stock") before sending the photo, the bot
does not ask again what to do with the photo - it answers straight away, using the codes it
just read. The reply still opens with the "I read ..." line so you know exactly what was
recognised:

> I read M486-75-BL and M483-BL from that photo.
>
> [stock answer follows]

## Sending a photo with a caption

A caption on the photo works in one turn - no need to send a follow-up message. Sending a
photo captioned "Check stock" is answered exactly the same as sending "check stock" and the
photo together, in the same turn as if you had typed "Check stock: M486-75-BL, M483-BL".

## Voice notes

Send a voice note the same way you would type a message. The bot transcribes it and opens its
reply with what it heard:

> I heard: stock for SRTWB1455
>
> [stock answer follows]

If the voice note could not be made out at all, the bot says so and asks you to try again or
type instead:

> I could not make out that voice note. Please send it again or type your message and I will
> help straight away.

## When a photo or voice note is refused

A photo or voice note is sometimes refused before the bot even tries to read it. The bot
always says why, and always names something that still works:

* **Photos or voice notes are not turned on yet for your number.** "I cannot read photos on
  this number yet. Type the codes instead and I will look them up straight away." (voice note:
  "I cannot listen to voice notes on this number yet. Type your message instead and I will
  help straight away.")
* **This month's allowance is used up.** "You have used all &lt;N&gt; of this month's photo
  reads, so I have not read this one. The allowance resets on &lt;date&gt;. Type the codes and
  I will look them up straight away." The photo and voice note allowances are separate, so
  using up one does not affect the other. The monthly limits themselves are set in
  **Settings > Chatbot Media** (**Photos per contact per month**, **Voice notes per contact per
  month**).
* **Too many sent in a short time.** "That is a lot at once - give me a moment to catch up,
  then send the rest." (the **Items per burst window** / **Burst window seconds** settings.)
* **A voice note is too long.** "That voice note is longer than &lt;N&gt; seconds. Please send
  a shorter one and I will listen to it." (the **Maximum clip seconds** setting.)

If a photo or voice note could not be read at all, or took too long, the bot also says so
plainly rather than staying silent:

* "I could not read anything from that photo. Type the codes and I will look them up straight
  away."
* "I could not read that photo in time. Please send it again or type the codes."
* "I could not listen to that voice note in time. Please send it again or type your message."

## Staff view: Chat History

See **[Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)**
for how a photo or voice note message looks inside Chat History, including the thumbnail,
the audio player, and the "Read N items" chip.

## See also

* [Chatbot settings](../user-management/chatbot-settings.md) - the Switches, Memory, Tier
  order and Cross-domain ladder cards.
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [Chatbot Domains](chatbot-domains.md) and [Entity kinds](chatbot-entity-kinds.md)
