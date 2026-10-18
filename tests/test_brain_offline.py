"""Offline checks for the Company Brain schema, search terms and incident embeddings."""
import pytest
from maelin.brain import search_terms
from maelin.schema import validate_dataset
from maelin.seed import dataset
from maelin.store import incident_embedding, EMBED_KINDS


def test_demo_brain_layer_validates():
    data = validate_dataset(dataset())
    assert len(data['people']) >= 6 and len(data['documents']) >= 6 and len(data['decisions']) >= 3


@pytest.mark.parametrize('mutate,message', [
    (lambda d: d['documents'][0].update(kind='email'), 'kind'),
    (lambda d: d['documents'][0].update(about=['ghost']), 'assets'),
    (lambda d: d['decisions'][0].update(source='missing'), 'source'),
    (lambda d: d['people'][0].update(team='nobody'), 'team'),
    (lambda d: d['team_ownership'].append({'team': 'secops', 'asset': 'ghost'}), 'Ownership'),
])
def test_brain_layer_rejects_dangling_references(mutate, message):
    data = dataset()
    mutate(data)
    with pytest.raises(ValueError, match=message):
        validate_dataset(data)


def test_search_terms_drop_stopwords_and_injection_characters():
    assert search_terms('Who owns the auth-service?') == ['auth', 'service']
    assert search_terms("x') RETURN 1 //") == ['return']
    assert search_terms('') == []


def test_incident_embedding_is_structural_and_bounded():
    vec = incident_embedding('ingress|service|database')
    assert len(vec) == 3 * len(EMBED_KINDS) and sum(vec) == 3
    assert incident_embedding('bad-key') is None
    assert incident_embedding('') is None
