import json
import pytest
from news_collector.jobs import sports
from test_editorial import packet, decision


def prior():
    return {'date': '2026-10-06', 'id': 'old', 'title': 'Duren returns on five-year $200m deal',
            'url': 'https://example.org/old', 'coverage': []}


def test_novelty_uses_published_summaries_and_does_not_treat_new_urls_as_new_events(tmp_path, monkeypatch):
    directory = tmp_path / 'data/cloudflare-published/editions/2026-10-06'
    directory.mkdir(parents=True)
    (directory / 'edition.json').write_text(json.dumps({'date': '2026-10-06', 'stories': [
        {**prior(), 'sector': 'Sports', 'summary': 'Duren signed a five-year $200 million contract after months of negotiations.',
         'points': []}]}))
    output = tmp_path / 'data/sports'
    output.mkdir(parents=True)
    request = {'packets': [{**packet(), 'sportsGroup': 'NBA'}], 'previouslyPublished': [prior()]}
    calls = []
    def review(payload, *args, **kwargs):
        calls.append(payload)
        assert 'five-year' in payload['previouslyPublished'][0]['summary']
        result = sports.SportsNoveltyReview(stories=[{'id': 'one', 'status': 'repeat', 'prior_story_ids': ['old'],
            'material_update': None, 'evidence': [], 'reason': 'Same signed contract; only new analysis of playoff pressure.'}])
        kwargs['validate_result'](result)
        return result
    monkeypatch.setattr(sports, 'codex_review', review)
    repeats, updates = sports.review_sports_novelty(request, [decision()], output, tmp_path)
    assert repeats[0]['id'] == 'one' and updates == []
    sports.review_sports_novelty(request, [decision()], output, tmp_path)
    assert len(calls) == 1
    assert (output / 'novelty-latest.json').exists()


@pytest.mark.parametrize('damage', ['no_update', 'no_evidence', 'unknown_evidence', 'unknown_prior', 'missing_story'])
def test_material_update_requires_complete_bound_proof(tmp_path, monkeypatch, damage):
    item = {'id': 'one', 'status': 'material_update', 'prior_story_ids': ['old'],
            'material_update': 'A newly confirmed injury rules the player out for six weeks.',
            'evidence': ['p1'], 'reason': 'The injury is a confirmed development after the prior report.'}
    if damage == 'no_update': item['material_update'] = None
    if damage == 'no_evidence': item['evidence'] = []
    if damage == 'unknown_evidence': item['evidence'] = ['not-supplied']
    if damage == 'unknown_prior': item['prior_story_ids'] = ['not-published']
    result = sports.SportsNoveltyReview(stories=[] if damage == 'missing_story' else [item])
    monkeypatch.setattr(sports, 'codex_review', lambda *_args, **_kwargs: result)
    with pytest.raises(ValueError):
        sports.review_sports_novelty({'packets': [packet()], 'previouslyPublished': [prior()]}, [decision()], tmp_path)


def test_real_new_development_is_retained_with_inspectable_evidence(tmp_path, monkeypatch):
    result = sports.SportsNoveltyReview(stories=[{'id': 'one', 'status': 'material_update', 'prior_story_ids': ['old'],
        'material_update': 'The player has now undergone season-ending surgery.', 'evidence': ['p1'],
        'reason': 'Confirmed surgery was not established in the prior story.'}])
    monkeypatch.setattr(sports, 'codex_review', lambda *_args, **_kwargs: result)
    repeats, updates = sports.review_sports_novelty({'packets': [packet()], 'previouslyPublished': [prior()]},
        [decision()], tmp_path)
    assert repeats == [] and updates[0]['evidence'] == ['p1']


def test_final_selection_excludes_a_previous_event_with_a_different_url(tmp_path, monkeypatch):
    from news_collector.pipeline.editorial import EditionSelection
    def review(payload, prompt, output, result_type, **kwargs):
        if result_type is sports.SportsNoveltyReview:
            return sports.SportsNoveltyReview(stories=[{'id': 'one', 'status': 'repeat',
                'prior_story_ids': ['old'], 'material_update': None, 'evidence': [],
                'reason': 'New analysis describes the same previously published contract.'}])
        return EditionSelection(selected_ids=['one'], excluded=[])
    monkeypatch.setattr(sports, 'codex_review', review)
    prompt = tmp_path / 'events.md'
    prompt.write_text('One sports event per story')
    request = {'packets': [{**packet(), 'sportsGroup': 'NBA'}], 'previouslyPublished': [prior()]}
    result = sports.reconcile_sports_events(request, [decision()], prompt, tmp_path)
    assert result['selected_ids'] == []
    assert result['excluded'][0]['id'] == 'one'
