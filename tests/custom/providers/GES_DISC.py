import pytest

# Provider-level custom tests for GES_DISC
# These run for any collection concept-id that ends with "-GES_DISC".

@pytest.mark.timeout(1200)
def test_ges_disc_custom_smoke(collection_concept_id, env, granule_json, harmony_env, tmp_path, bearer_token_manager):
    """Example provider-level test. Replace with real assertions."""
    assert collection_concept_id.endswith("-GES_DISC")
    assert granule_json.get("meta", {}).get("collection-concept-id")
