# Hand test: AGENTIC-KNOWLEDGE P2 W1 (agent answers contacts, product knowledge)

## URL
crew test copy

## Setup
1. The test copy has a Gemini key (AI settings) and a running worker (the `knowledge` queue reads files).
2. Resources > Attachment Types > "Direct Access": set "AI can read" to "Everyone". Save.
3. Resources: open any Warranty Policy PDF of type "Direct Access" (or upload one, access levels left at the
   default, which includes every code). Wait until the file shows "Read by AI: done".
4. Resources > Attachment Types > "Technical Specifications": set "AI can read" to "Dealers". Save. Wait for one
   product tech-spec PDF to show "Read by AI: done".
5. Pick contact A: a dealer contact with NO linked CRM user, a dealer access code (dealer / mocha_dealer /
   cabana_dealer), AI replies on, Escalation unticked. On its page tick "Agent mode (auto)".
6. Pick contact B: an end-user-only contact (access code end_user only), no linked user, AI replies on, Escalation
   ticked, "Agent mode (auto)" ticked.
7. Make sure an HR / staff-only document type ("AI can read" = "Staff only") has a read file (from P1).

## Steps
1. Open the Chatbot console from the sidebar and select contact A.
2. Send: "what is the warranty for a sorento water closet?"
3. Send: "how many days of annual leave do staff get?" (a staff handbook question)
4. Send: "does the SRTWT51012 come with an installation guide?" (or a question the tech spec PDF answers)
5. Send: "can the basin mixer be used with a solar water heater?" (a question no document answers)
6. Select contact B.
7. Send: "what is the warranty for a sorento water closet?"
8. Send the tech-spec question from step 4.
9. Send the question from step 5.
10. Reply "yes".
11. On contact A's page untick "Agent mode (auto)", then send step 2's question again for contact A in the console.

## Expected
- Step 2: the agent answers from the Warranty Policy with a citation like "(Warranty Policy_Sorento, p.N)". No
  "sorry", no "busy", no team name.
- Step 3: no handbook passage; the reply says "I couldn't find that in our product documents." followed by
  "Please refer to your salesman." (contact A is barred from escalation). No HR wording, no staff team name.
- Step 4: the agent answers from the tech-spec PDF with its page citation (contact A has a dealer code).
- Step 5: "I couldn't find that in our product documents." + "Please refer to your salesman."; no marketing offer.
- Step 7: answered from the Warranty Policy (Everyone reaches end users).
- Step 8: no tech-spec passage (Dealers documents do not reach an end-user-only contact): "I couldn't find that
  in our product documents." + "Would you like me to pass this to our marketing product team?"
- Step 9: "I couldn't find that in our product documents." + "Would you like me to pass this to our marketing
  product team?"
- Step 10: NO escalation task is created. Console turns are test turns and never write the real contact's session,
  so the offer from step 9 is shown but not armed (by design). The live "yes" -> marketing product hand-off is proved
  by `test_fr1_f7_a_live_turn_ends_with_the_say_text_and_arms_the_offer` and is checked on WhatsApp after deploy
  with one pilot contact.
- Step 11: the bot answers (today's reply), not the agent.
- In the console trace of every agent turn: the passage text is not stored, only document, page and heading.
