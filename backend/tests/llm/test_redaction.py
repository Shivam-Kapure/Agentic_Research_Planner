from app.llm.redaction import REDACTED, redact


def test_redacts_groq_and_gemini_keys():
    groq = "gsk_" + "Abc123Def456Ghi789"
    gemini = "AIza" + "SyD-abcdefghijklmnopqrstuvwxyz12"

    text = redact(f"groq={groq} gemini={gemini}")

    assert groq not in text
    assert gemini not in text
    assert text.count(REDACTED) == 2


def test_redacts_generic_api_key_assignments_but_keeps_label():
    text = redact('Authorization: Bearer abcdefghijklmnop1234 and "api_key": "zzzzzzzzzzzzzzzz"')

    assert "abcdefghijklmnop1234" not in text
    assert "zzzzzzzzzzzzzzzz" not in text
    assert "Authorization" in text


def test_leaves_ordinary_text_untouched():
    text = "Retrieval-augmented generation reduced hallucination in 7 of 9 studies."

    assert redact(text) == text
