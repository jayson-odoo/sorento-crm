# UAC: parser max output tokens (PARSER-MAX-TOKENS, 29 Oct 2026)

- AC-1: a stock check of 63 product codes in one message is understood when the model needs
  ~5,500 output tokens for it (Gemini 3.x and OpenAI alike).
- AC-2: with no stored value the parser asks for 8,192 output tokens (Gemini 3.x adds its
  thinking budget and the 2,048 answer headroom on top, as today).
- AC-3: `system_settings.chatbot_parser_max_output_tokens` set to a value in 1,024-32,768 is
  what the next parse asks for, on Gemini and OpenAI.
- AC-4: a stored value outside 1,024-32,768 is clamped to the nearest bound and logged; the
  turn still runs.
- AC-5: a parser call that stops on the output cap still writes its `chatbot_parser` usage
  row, with `was_answered = false` and the tokens the provider billed.
- AC-6: the customer-facing reply wording is unchanged.
