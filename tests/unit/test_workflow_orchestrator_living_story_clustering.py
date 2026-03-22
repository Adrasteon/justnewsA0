from agents.workflow_orchestrator.policies import (
    IncrementalClusteringPolicy,
    _token_overlap_score,
    _vector_cosine_similarity,
)


def test_vector_cosine_similarity_identical_vectors() -> None:
    score = _vector_cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert round(score, 6) == 1.0


def test_vector_cosine_similarity_orthogonal_vectors() -> None:
    score = _vector_cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert round(score, 6) == 0.0


def test_token_overlap_score_reasonable_overlap() -> None:
    left = 'Prime minister meets union leaders over transport strike'
    right = 'Transport strike talks continue as minister meets union officials'
    score = _token_overlap_score(left, right)
    assert 0.15 <= score <= 0.8


def test_merge_candidates_prefers_story_first_and_blends_neighbor_score() -> None:
    policy = object.__new__(IncrementalClusteringPolicy)

    story_candidates = {
        'CL-story': {
            'cluster_id': 'CL-story',
            'source': 'story_first',
            'score': 0.8,
        }
    }
    neighbor_candidates = {
        'CL-story': {
            'cluster_id': 'CL-story',
            'source': 'neighbor',
            'score': 0.6,
            'neighbor_support': 4,
        },
        'CL-neighbor-only': {
            'cluster_id': 'CL-neighbor-only',
            'source': 'neighbor',
            'score': 0.5,
            'neighbor_support': 2,
        },
    }

    ranked = policy._merge_candidates(story_candidates, neighbor_candidates)

    assert len(ranked) >= 2
    assert ranked[0]['cluster_id'] == 'CL-story'
    assert ranked[0]['source'] == 'hybrid'
    assert ranked[0]['score'] > 0.7
