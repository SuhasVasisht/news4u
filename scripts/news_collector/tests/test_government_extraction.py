from news_collector.pipeline.extract import extract_text_from_html


def test_doj_release_preserves_consent_conditions_and_excludes_navigation():
    html = '<nav>Unrelated news</nav><div class="field_body"><p>The proposed decree would:</p><ul><li>Ban sharing sensitive pricing data.</li><li>Require an independent monitor.</li></ul><p>Subject to court approval.</p></div>'
    text = extract_text_from_html(html, "https://www.justice.gov/opa/pr/example")
    assert "Ban sharing sensitive pricing data." in text
    assert "Require an independent monitor." in text
    assert "Subject to court approval." in text
    assert "Unrelated news" not in text
