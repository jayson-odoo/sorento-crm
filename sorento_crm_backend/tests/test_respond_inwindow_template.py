"""In-window template uniformity (PLAN-whatsapp-inwindow-template-uniformity).

Inside the 24h WhatsApp window the choke point now renders the SAME use-case
default template (variables filled) instead of the caller's ad-hoc text, so the
message reads identically whether it ships as free text (in-window) or an
approved template (out-of-window). With no configured default it falls back to
the raw text — uniformity rolls out per use-case, never breaks an unconfigured one.
"""
from app.services import respond_messaging_service as rms


class _Tmpl:
    def __init__(self, body_text, param_count):
        self.body_text = body_text
        self.param_count = param_count


class _Row:
    def __init__(self, template, param_mapping):
        self.template = template
        self.param_mapping = param_mapping


def _patch_default(monkeypatch, *, row, is_valid):
    """Stub the lazily-imported default-template lookup used by render_in_window_text."""
    monkeypatch.setattr(
        "app.services.respond_template_service.get_default_row",
        lambda db, use_case: row,
        raising=True,
    )
    monkeypatch.setattr(
        "app.services.respond_template_service.serialize_default",
        lambda use_case, r: {
            "is_valid": is_valid,
            "template_removed": False,
            "template_id": "t-1" if r else None,
            "template_status": "approved",
        },
        raising=True,
    )


def _capture_send(monkeypatch):
    sent = {}

    class _FakeClient:
        def send_message(self, identifier, text):
            sent["identifier"] = identifier
            sent["text"] = text
            return {"id": "msg-1"}

    monkeypatch.setattr(
        "app.services.integration_service.RespondClient", lambda *a, **k: _FakeClient()
    )
    return sent


# ---- render_in_window_text ----------------------------------------------------

def test_render_uses_template_body_when_default_configured(monkeypatch):
    row = _Row(
        _Tmpl("Hi {{1}}, your {{2}} is {{3}}.", 3),
        {"1": "contact_name", "2": "entity_number", "3": "status"},
    )
    _patch_default(monkeypatch, row=row, is_valid=True)
    out = rms.render_in_window_text(
        None,
        use_case="complaint",
        context_vars={"contact_name": "Aisha", "entity_number": "CMP-42", "status": "Resolved"},
        fallback_text="raw ad-hoc text",
    )
    assert out == "Hi Aisha, your CMP-42 is Resolved."


def test_render_falls_back_to_raw_text_without_default(monkeypatch):
    _patch_default(monkeypatch, row=None, is_valid=False)
    out = rms.render_in_window_text(
        None,
        use_case="complaint",
        context_vars={"contact_name": "Aisha"},
        fallback_text="raw ad-hoc text",
    )
    assert out == "raw ad-hoc text"


def test_render_preserves_newlines_in_window(monkeypatch):
    # Richer-multiline decision: in-window (flatten=False) keeps newlines in values.
    row = _Row(_Tmpl("Update:\n{{1}}", 1), {"1": "message"})
    _patch_default(monkeypatch, row=row, is_valid=True)
    out = rms.render_in_window_text(
        None,
        use_case="complaint",
        context_vars={"message": "line one\nline two"},
        fallback_text="x",
    )
    assert out == "Update:\nline one\nline two"


def test_out_of_window_param_flattens_newlines():
    # Same value, template branch (flatten=True default) → newline becomes " | ".
    assert rms.sanitize_param("line one\nline two") == "line one | line two"
    assert rms.sanitize_param("line one\nline two", flatten=False) == "line one\nline two"


# ---- send_text_or_template integration ---------------------------------------

def test_in_window_send_uses_rendered_template(monkeypatch):
    monkeypatch.setattr(
        rms, "get_window_state", lambda *a, **k: {"open": True, "source": "respond_api"}
    )
    row = _Row(_Tmpl("Hi {{1}}: {{2}}", 2), {"1": "contact_name", "2": "message"})
    _patch_default(monkeypatch, row=row, is_valid=True)
    sent = _capture_send(monkeypatch)

    result = rms.send_text_or_template(
        None,
        identifier="60123",
        text="your complaint was resolved",
        use_case="complaint",
        context_vars={"contact_name": "Aisha"},
    )
    assert result["sent_as"] == "text"
    # message var defaults to the raw text → rendered uniformly via the template.
    assert sent["text"] == "Hi Aisha: your complaint was resolved"
    assert result["request_payload"]["message"]["text"] == sent["text"]


def test_in_window_send_falls_back_to_raw_text(monkeypatch):
    monkeypatch.setattr(
        rms, "get_window_state", lambda *a, **k: {"open": True, "source": "respond_api"}
    )
    _patch_default(monkeypatch, row=None, is_valid=False)
    sent = _capture_send(monkeypatch)

    rms.send_text_or_template(
        None,
        identifier="60123",
        text="plain unconfigured message",
        use_case="complaint",
        context_vars={},
    )
    assert sent["text"] == "plain unconfigured message"
