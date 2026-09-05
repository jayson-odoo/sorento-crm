"""Chatbot module bootstrap (D3).

`MODULE_KEY` is what `require_module_enabled_with_api_key` gates the `/external/chat/*`
router on, and what `app_modules_catalog` is seeded with on first run. The module owns
the Postgres schema `chatbot` and the package `app/services/chatbot/`; core never imports
either.
"""

MODULE_KEY = "chatbot"
