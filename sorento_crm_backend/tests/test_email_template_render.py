"""Pure-Python tests for the Jinja2 templating helpers and EmailTemplateService.render."""
from __future__ import annotations

from app.services.templating import html_to_text, render_html, render_text


def test_render_html_substitutes_dotted_variables():
    out = render_html(
        "<p>Promo {{ promotion.code }} runs {{ promotion.start_date }} to {{ promotion.end_date }}.</p>",
        {
            "promotion": {
                "code": "PROMO-123",
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
            }
        },
    )
    assert "PROMO-123" in out
    assert "2026-05-01" in out
    assert "2026-05-31" in out


def test_render_html_autoescapes_html_in_user_data():
    out = render_html("<p>Hi {{ recipient.name }}</p>", {"recipient": {"name": "<script>x</script>"}})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_text_does_not_autoescape():
    out = render_text("Hi {{ recipient.name }}", {"recipient": {"name": "Tan & Co."}})
    assert out.startswith("Hi Tan & Co.")


def test_render_unknown_variable_returns_marker_not_500():
    out = render_html("<p>{{ promotion.code }} {{ missing.field }}</p>", {"promotion": {"code": "X"}})
    assert "X" in out
    assert "[unknown:" in out


def test_render_html_decodes_entity_escaped_operator_inside_jinja_tag():
    # HTML editors entity-escape '>' inside {% if %}; must not break the lexer.
    body = (
        "Hi {{ recipient.name }},\n\n"
        "{% if (promotions_count or 1) &gt; 1 %}The following {{ promotions_count }} promotions"
        " are ending soon:{% else %}The following promotion is ending soon:{% endif %}"
    )
    plural = render_html(body, {"recipient": {"name": "CK Lee"}, "promotions_count": 2})
    assert "[template-error:" not in plural
    assert "The following 2 promotions are ending soon:" in plural

    single = render_html(body, {"recipient": {"name": "CK Lee"}, "promotions_count": 1})
    assert "The following promotion is ending soon:" in single


def test_render_html_preserves_real_ampersand_entity_in_output_text():
    # Only entities INSIDE Jinja tags are decoded; literal output entities stay.
    out = render_html("Tom &amp; Jerry {% if x &gt; 1 %}many{% endif %}", {"x": 5})
    assert "Tom &amp; Jerry many" == out


def test_html_to_text_strips_tags():
    text = html_to_text("<p>Hello <strong>world</strong></p>")
    # html2text-formatted output preserves bold markers (**); fallback strips. Either way "Hello" + "world" appear.
    assert "Hello" in text
    assert "world" in text
    assert "<strong>" not in text


def test_html_to_text_empty_safe():
    assert html_to_text("") == ""
