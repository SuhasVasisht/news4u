from news_collector.collectors.techmeme import TechmemeCollector


def test_text_only_story_uses_headline_not_publisher_homepage():
    description = '''<p><a href="https://www.techmeme.com/260910/p11">Permalink</a>
    <a href="https://www.axios.com/">Axios</a>:
    <span><b><a href="https://www.axios.com/2026/09/10/openai-probe">Senate probe</a></b></span></p>'''
    assert TechmemeCollector._extract_primary_link(description) == (
        "https://www.axios.com/2026/09/10/openai-probe", "Axios")


def test_headline_wins_over_unrelated_thumbnail_and_discussion():
    description = '''<a href="https://other.example/ad"><img src="ad.jpg"></a>
    <a href="https://publisher.example/">Publisher</a>
    <b><a href="https://publisher.example/story">Headline</a></b>
    <a href="https://discussion.example/thread">Discussion</a>'''
    assert TechmemeCollector._extract_primary_link(description) == ("https://publisher.example/story", "Publisher")


def test_missing_headline_never_returns_homepage_or_unsafe_link():
    for description in ['<a href="https://publisher.example/">Publisher</a>',
                        '<a href="https://publisher.example/"><img src="favicon.ico"></a>',
                        '<b><a href="https://publisher.example/">Publisher</a></b>',
                        '<b><a href="javascript:alert(1)">Bad</a></b>',
                        '<b><a href="https://techmeme.com/post">Permalink</a></b>']:
        assert TechmemeCollector._extract_primary_link(description) == (None, None)


def test_unstyled_article_link_is_a_valid_fallback():
    assert TechmemeCollector._extract_primary_link(
        '<a href="https://publisher.example/">Publisher</a><a href="https://publisher.example/story">Story</a>'
    ) == ("https://publisher.example/story", "Publisher")


def test_more_coverage_does_not_override_main_headline():
    assert TechmemeCollector._extract_primary_link('''
      <a href="https://publisher.example/"><img src="favicon.ico"></a>
      <a href="https://publisher.example/">Publisher</a>
      <span><b><a href="https://publisher.example/main">Main headline</a></b></span>
      <b>More coverage:</b><a href="https://other.example/report">Other account</a>
    ''') == ("https://publisher.example/main", "Publisher")
