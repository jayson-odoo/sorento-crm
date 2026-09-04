"""The chatbot turn engine (module `chatbot`, D3).

ONE public entry point. Core never imports this package; the package imports core
services freely. `tests/chatbot/test_import_boundary.py` enforces the asymmetry, which
is the whole "liftable later" story: when the named trigger in the plan fires, the
package moves behind an HTTP boundary with these same contracts.
"""
from app.services.chatbot.engine import run_turn

__all__ = ["run_turn"]
