"""A source that cannot pass admission must never strand the daily sports desk."""
import json

import pytest

from news_collector.jobs import sports
from test_editorial import packet, decision


@pytest.mark.parametrize('damage', ['75_words', '79_words', 'truncated', 'no_chunks'])
def test_ineligible_sports_source_is_held_before_model_and_preserved_on_resume(tmp_path, monkeypatch, damage, capsys):
    candidate = {**packet(), 'id': 'thin', 'sportsGroup': 'Elsewhere'}
    if damage.endswith('_words'):
        candidate['wordCount'] = int(damage.split('_')[0])
    elif damage == 'truncated':
        candidate['truncated'] = True
    else:
        candidate['chunks'] = []
    good = {**packet(), 'id': 'complete', 'sportsGroup': 'NFL'}
    calls = []
    def review(payload, *_):
        calls.append([p['id'] for p in payload['packets']])
        # The old code sent the ineligible packet here and retried its impossible
        # admission. Today’s real 75-word championship result hit that path twice.
        return sports.SportsReview(decisions=[decision(id=p['id']) for p in payload['packets']])
    monkeypatch.setattr(sports, 'codex_review', review)
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Do not admit incomplete evidence')
    request = {'packets': [candidate, good], 'previouslyPublished': []}
    first = sports.review_candidates(request, prompt, tmp_path)
    resumed = sports.review_candidates(json.loads(json.dumps(request)), prompt, tmp_path)
    for result in [first, resumed]:
        assert {d.id for d in result.decisions} == {'thin', 'complete'}
        held = next(d for d in result.decisions if d.id == 'thin')
        assert held.decision == 'hold' and not held.summary and not held.evidence
        assert next(d for d in result.decisions if d.id == 'complete').decision == 'admit'
        sports.validate_decisions(result, request['packets'])
    assert calls == [['complete']]
    assert 'sports_candidate_held' in capsys.readouterr().out


def test_no_eligible_sports_articles_needs_no_model_and_returns_complete_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(sports, 'codex_review', lambda *_: pytest.fail('Ineligible evidence reached model'))
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Review')
    result = sports.review_candidates({'packets': [{**packet(), 'sportsGroup': 'NBA', 'wordCount': 75}],
                                      'previouslyPublished': []}, prompt, tmp_path)
    assert len(result.decisions) == 1
    assert result.decisions[0].decision == 'hold'
    assert not list(tmp_path.glob('review-*.json'))


@pytest.mark.parametrize('words', [80, 81])
def test_source_gate_keeps_boundary_eligible_packets_for_full_editorial_review(tmp_path, monkeypatch, words):
    candidate = {**packet(), 'sportsGroup': 'NBA', 'wordCount': words}
    calls = []
    monkeypatch.setattr(sports, 'codex_review', lambda payload, *_: calls.append(payload) or
                        sports.SportsReview(decisions=[decision()]))
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Review')
    result = sports.review_candidates({'packets': [candidate], 'previouslyPublished': []}, prompt, tmp_path)
    assert calls and result.decisions[0].decision == 'admit'


def test_eligible_but_malformed_editorial_output_still_blocks(tmp_path, monkeypatch):
    candidate = {**packet(), 'sportsGroup': 'NFL'}
    monkeypatch.setattr(sports, 'codex_review', lambda *_: sports.SportsReview(decisions=[decision(evidence=[])]))
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('Review')
    with pytest.raises(ValueError, match='lacks evidence'):
        sports.review_candidates({'packets': [candidate], 'previouslyPublished': []}, prompt, tmp_path)
    assert not list(tmp_path.glob('review-*.json'))
