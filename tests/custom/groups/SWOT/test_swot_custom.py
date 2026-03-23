def test_swot_custom_smoke(collection_concept_id, granule_json):
    if collection_concept_id not in {
        "C1223720291-GES_DISC",
        "C1234567890-GES_DISC",
    }:
        return

    assert granule_json["meta"]["concept-id"] == collection_concept_id
