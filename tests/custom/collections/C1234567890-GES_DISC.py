import pytest

# Collection-level custom tests for C1234567890-GES_DISC
# Generic spatial/temporal tests are skipped for this collection by default.

@pytest.mark.timeout(1200)
def test_c1234567890_custom_smoke(collection_concept_id, env, granule_json, harmony_env, tmp_path, bearer_token_manager):
    """Example collection-level test. Replace with real assertions."""
    assert collection_concept_id == "C1234567890-GES_DISC"
    assert granule_json.get("meta", {}).get("concept-id")
