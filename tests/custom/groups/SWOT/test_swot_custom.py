def test_swot_custom_smoke(collection_concept_id, granule_json):
    if collection_concept_id not in {
        "C1223720291-GES_DISC",
        "C1234567890-GES_DISC"
    }:
        return

    print(granule_json)
    assert granule_json["meta"]["collection-concept-id"] == collection_concept_id
