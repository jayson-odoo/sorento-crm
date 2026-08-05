"""Certificate coverage for the render envelope (MCP-9 / MCP-10 / MCP-11).

`view=render` is the mode the n8n consumer actually uses, and the presenters
WHITELIST fields - a new key on the raw response is invisible until a presenter
emits it. These tests pin that:

  MCP-9  a cert-bearing product-attachment row renders Valid Until and sets the
         envelope's existing flags.expired; a non-cert row is untouched.
  MCP-10 crm_certificates_list renders scheme / number / body / valid-until and
         attaches the CURRENT revision's file.
  MCP-11 a certificate whose current revision has no usable file returns its
         fields with an EMPTY attachments array, never a null or broken url.
"""
import json

from sorento_crm_mcp.presenters import (
    PRESENTER_TOOLS,
    _DEFAULT_INTRO,
    _RESULT_TYPE,
    present_response,
)
from sorento_crm_mcp.server import _sanitize_tool_response

CERT_TOOL = "crm_certificates_list"
PA_TOOL = "crm_master_product_attachments_list"


def env(tool, data):
    return json.loads(present_response(tool, json.dumps(data)))


def fields(item):
    return {f["label"]: f["value"] for f in item["fields"]}


# ------------------------------------------------------------------ MCP-9
def test_product_attachment_cert_row_renders_valid_until_and_expired_flag():
    out = env(PA_TOOL, {
        "data": [{
            "product": {"product_code": "WC8038", "product_name": "Angle valve"},
            "attachment": {
                "original_filename": "PPS - IKRAM 04424FC.pdf",
                "file_path": "https://cdn.example/pps-04424fc.pdf",
                "mime_type": "application/pdf",
                "attachment_type": "Certification",
            },
            "certificate": {
                "id": "c1",
                "scheme": "PPS",
                "certificate_number": "04424FC",
                "valid_until": "2026-12-23",
                "validity_state": "expired",
                "is_expired": True,
            },
        }],
    })
    item = out["items"][0]
    assert fields(item)["Valid Until"] == "2026-12-23"
    assert item["flags"]["expired"] is True
    # The file is still delivered: found-but-expired, not hidden.
    assert out["attachments"][0]["url"] == "https://cdn.example/pps-04424fc.pdf"


def test_product_attachment_live_cert_row_is_not_flagged_expired():
    out = env(PA_TOOL, {
        "data": [{
            "product": {"product_code": "WC8038"},
            "attachment": {"original_filename": "cert.pdf", "file_path": "https://cdn/x.pdf"},
            "certificate": {"valid_until": "2029-04-05", "is_expired": False},
        }],
    })
    item = out["items"][0]
    assert fields(item)["Valid Until"] == "2029-04-05"
    assert item["flags"]["expired"] is False


def test_product_attachment_non_cert_row_unchanged_no_valid_until_no_flag():
    """The 951 Technical Specifications rows carry no `certificate` key at all."""
    out = env(PA_TOOL, {
        "data": [{
            "product": {"product_code": "SRTWB7109", "product_name": "Basin"},
            "attachment": {
                "original_filename": "spec-sheet.pdf",
                "file_path": "https://cdn.example/spec.pdf",
                "attachment_type": "Technical Specifications",
            },
        }],
    })
    item = out["items"][0]
    assert "Valid Until" not in fields(item)
    assert item["flags"]["expired"] is False
    assert fields(item)["File Name"] == "spec-sheet.pdf"


def test_product_attachment_null_certificate_key_is_a_no_op():
    """`certificate: null` is what a non-cert row serializes as once the nested
    key exists on the schema. It must behave exactly like an absent key."""
    out = env(PA_TOOL, {
        "data": [{
            "product": {"product_code": "SRTWB7109"},
            "attachment": {"original_filename": "photo.jpg", "file_path": "https://cdn/p.jpg"},
            "certificate": None,
        }],
    })
    item = out["items"][0]
    assert "Valid Until" not in fields(item)
    assert item["flags"]["expired"] is False


# ------------------------------------------------------------------ MCP-10
def test_certificates_tool_is_wired_into_the_presenter_tables():
    assert CERT_TOOL in PRESENTER_TOOLS
    assert _RESULT_TYPE[CERT_TOOL] == "certificates"
    assert CERT_TOOL in _DEFAULT_INTRO


def test_certificates_render_identity_fields_and_attach_current_revision():
    out = env(CERT_TOOL, {
        "data": [{
            "id": "c1",
            "scheme": "PPS",
            "certificate_number": "04424FC",
            "certifying_body": "IKRAM",
            "valid_from": "2024-12-23",
            "valid_until": "2026-12-23",
            "validity_state": "valid",
            "is_expired": False,
            "covered_product_count": 68,
            "current_revision": {
                "revision_no": 2,
                "is_current": True,
                "attachment": {
                    "original_filename": "PPS - IKRAM 04424FC.pdf",
                    "file_path": "https://cdn.example/rev2.pdf",
                    "mime_type": "application/pdf",
                    "attachment_type": "Certification",
                },
            },
        }],
    })
    assert out["result_type"] == "certificates"
    item = out["items"][0]
    assert item["title"] == "PPS 04424FC"
    f = fields(item)
    assert f["Scheme"] == "PPS"
    assert f["Certificate Number"] == "04424FC"
    assert f["Certifying Body"] == "IKRAM"
    assert f["Valid Until"] == "2026-12-23"
    assert f["Covered Products"] == 68
    assert item["flags"]["expired"] is False
    assert out["attachments"] == [{
        "url": "https://cdn.example/rev2.pdf",
        "filename": "PPS - IKRAM 04424FC.pdf",
        "mimeType": "application/pdf",
        "attachmentType": "Certification",
    }]


def test_certificates_expired_row_sets_the_expired_flag():
    out = env(CERT_TOOL, {
        "data": [{
            "scheme": "SPAN",
            "certificate_number": "04124FC",
            "valid_until": "2020-04-05",
            "validity_state": "expired",
            "is_expired": True,
        }],
    })
    assert out["items"][0]["flags"]["expired"] is True


def test_certificates_only_the_current_revision_is_attached():
    """MCP-8: a superseded revision's PDF must never reach the consumer."""
    out = env(CERT_TOOL, {
        "data": [{
            "scheme": "PPS",
            "certificate_number": "0119",
            "valid_until": "2027-01-07",
            "is_expired": False,
            "revisions": [
                {
                    "revision_no": 2,
                    "is_current": True,
                    "attachment": {
                        "original_filename": "rev2.pdf",
                        "file_path": "https://cdn.example/rev2.pdf",
                    },
                },
                {
                    "revision_no": 1,
                    "is_current": False,
                    "attachment": {
                        "original_filename": "rev1.pdf",
                        "file_path": "https://cdn.example/rev1.pdf",
                    },
                },
            ],
        }],
    })
    assert [a["url"] for a in out["attachments"]] == ["https://cdn.example/rev2.pdf"]


def test_certificates_signed_url_shape_is_attached():
    """`resolve_signed_urls=true` returns the pair on the row itself."""
    out = env(CERT_TOOL, {
        "data": [{
            "scheme": "PPS",
            "certificate_number": "04324FC",
            "valid_until": "2026-12-23",
            "is_expired": False,
            "attachment_filename": "PPS - IKRAM 04324FC.pdf",
            "mime_type": "application/pdf",
            "preview_url": "https://cdn.example/preview.pdf",
            "download_url": "https://cdn.example/download.pdf",
        }],
    })
    assert out["attachments"] == [{
        "url": "https://cdn.example/download.pdf",
        "filename": "PPS - IKRAM 04324FC.pdf",
        "mimeType": "application/pdf",
        "attachmentType": None,
    }]


# ------------------------------------------------------------------ MCP-11
def test_certificate_with_no_usable_file_returns_empty_attachments():
    out = env(CERT_TOOL, {
        "data": [{
            "scheme": "PPS",
            "certificate_number": "04224FC",
            "certifying_body": "IKRAM",
            "valid_until": "2026-12-23",
            "validity_state": "valid",
            "is_expired": False,
            "covered_product_count": 0,
            "current_revision": {"revision_no": 1, "is_current": True, "attachment": None},
        }],
    })
    assert out["attachments"] == []
    assert out["has_result"] is True
    f = fields(out["items"][0])
    assert f["Certificate Number"] == "04224FC"
    assert f["Valid Until"] == "2026-12-23"


def test_certificate_with_trashed_file_and_null_urls_returns_empty_attachments():
    out = env(CERT_TOOL, {
        "data": [{
            "scheme": "SPAN",
            "certificate_number": "04124FC",
            "valid_until": "2029-04-05",
            "is_expired": False,
            "current_revision": {
                "is_current": True,
                "attachment": {"original_filename": "gone.pdf", "file_path": None},
            },
            "preview_url": None,
            "download_url": None,
        }],
    })
    assert out["attachments"] == []
    assert out["items"][0]["fields"]


# ------------------------------------------------------------------ MCP-3
def test_certificate_updated_at_is_naive_malaysia_wall_clock():
    """The generic sanitizer already owns this; assert it reaches THIS tool."""
    out = json.loads(
        _sanitize_tool_response(
            CERT_TOOL,
            json.dumps({
                "data": [{
                    "scheme": "PPS",
                    "certificate_number": "04424FC",
                    "updated_at": "2026-06-12T01:28:56",
                    "created_at": "2026-06-12T01:28:56",
                }],
            }),
        )
    )
    row = out["data"][0]
    assert row["updated_at"] == "2026-06-12T09:28:56"
    assert "+" not in row["updated_at"] and not row["updated_at"].endswith("Z")
    assert row["created_at"] == "2026-06-12T01:28:56"


def test_certificates_empty_page_is_a_clean_no_result_envelope():
    out = env(CERT_TOOL, {"data": []})
    assert out["items"] == []
    assert out["attachments"] == []
    assert out["has_result"] is False
    assert out["intro"] == "No matching results found."
