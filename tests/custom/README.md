# Custom Tests

This folder lets you create provider- or collection-specific test cases.

## Provider-level custom tests
Place a file here:

`tests/custom/providers/<PROVIDER>.py`

Example:

`tests/custom/providers/GES_DISC.py`

## Collection-level custom tests
You can add a single file:

`tests/custom/collections/<CONCEPT_ID>.py`

Or a folder with multiple tests:

`tests/custom/collections/<CONCEPT_ID>/test_*.py`

### Environment-specific collections
If you need UAT/OPS separation, you can use env-specific folders:

`tests/custom/collections/uat/<CONCEPT_ID>.py`
`tests/custom/collections/ops/<CONCEPT_ID>.py`

Or folders with multiple tests:

`tests/custom/collections/uat/<CONCEPT_ID>/test_*.py`
`tests/custom/collections/ops/<CONCEPT_ID>/test_*.py`

## Skipping generic tests
By default:
- If a collection-level custom test exists, generic spatial/temporal tests are skipped by default.
- Provider-level custom tests run alongside generic tests.

## Override Flags
These are the most common flags you can use in `tests/overrides.json` or a custom overrides file.

When a provider, group, or collection override exists, generic spatial and temporal tests are
off by default. Turn them back on explicitly with:

- `run_generic_spatial`: enables only the generic spatial test.
- `run_generic_temporal`: enables only the generic temporal test.
- `spatial_bbox_scale`: shrinks the spatial box relative to the chosen extent. Use `1.0` to keep the bbox exactly as provided.
- `spatial_bbox`: overrides the spatial area used to choose the granule and build the spatial Harmony request.
- `granule_concept_id`: forces the test to use a specific granule instead of selecting one from CMR.
- `temporal_fraction`: shrinks the temporal request to the middle portion of the granule time range.
- `members`: the list of collection concept IDs that belong to a collection group.

To force the spatial test to use a specific bbox for a collection, add `spatial_bbox`
to that collection's override block:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "spatial_bbox": [-10, 20, 10, 40]
    }
  }
}
```

You can also do the same for a provider or a collection group. For example:

```
{
  "providers": {
    "GES_DISC": {
      "spatial_bbox": [-10, 20, 10, 40]
    }
  }
}
```

You can also pass a bbox on the command line with `--bbox west,south,east,north`.
The test still applies `spatial_bbox_scale` when shrinking the requested area, so
set that to `1.0` if you want to use the exact bbox you provided.

To force the test to use a specific granule instead of letting CMR pick one, add:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "granule_concept_id": "G1234567890-GES_DISC"
    }
  }
}
```

You can also pass `--granule_concept_id <GRANULE_ID>` on the command line.
When this is set, the test uses that exact granule and skips the normal "pick the
latest granule for the collection" lookup.

## Grouping collections (list override)
You can apply one override block to multiple collections:

```

### Environment-specific groups
You can separate groups by environment:

`tests/custom/groups/uat/<GROUP_NAME>/concept_ids.json`
`tests/custom/groups/uat/<GROUP_NAME>/test_*.py`

`tests/custom/groups/ops/<GROUP_NAME>/concept_ids.json`
`tests/custom/groups/ops/<GROUP_NAME>/test_*.py`
{
  "collection_groups": {
    "GES_DISC_SPECIAL": {
      "members": [
        "C1234567890-GES_DISC",
        "C1111111111-GES_DISC"
      ],
      "spatial_bbox_scale": 0.9
    }
  }
}
```

## Enable Generic Tests
If a matching provider, group, or collection override exists, the generic tests are off
unless you explicitly turn them on:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "run_generic_spatial": true
    }
  }
}
```

You can enable temporal instead:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "run_generic_temporal": true
    }
  }
}
```
