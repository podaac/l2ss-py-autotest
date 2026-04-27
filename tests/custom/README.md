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
- If a collection-level custom test exists, generic spatial/temporal tests are skipped.
- Provider-level custom tests run alongside generic tests unless you explicitly replace them.

## Override Flags
These are the most common flags you can use in `tests/overrides.json` or a custom overrides file.

- `run_generic`: master switch for generic tests for that collection, provider, or group. `false` disables both spatial and temporal generic tests.
- `disable_generic`: stronger master switch. If `true`, generic tests are skipped even if other flags would allow them.
- `run_generic_spatial`: controls only the generic spatial test. `false` skips spatial, but temporal may still run.
- `run_generic_temporal`: controls only the generic temporal test. `false` skips temporal, but spatial may still run.
- `skip_spatial`: explicit opt-out for spatial testing.
- `skip_temporal`: explicit opt-out for temporal testing.
- `force_spatial`: lets a collection run spatial tests even if it appears in the spatial skip list.
- `force_temporal`: lets a collection run temporal tests even if it appears in the temporal skip list.
- `also_run_generic`: when custom collection or group tests exist, keep the generic tests too.
- `replace_generic`: when custom provider tests exist, skip the generic tests.
- `spatial_bbox_scale`: shrinks the spatial box relative to the chosen extent. Use `1.0` to keep the bbox exactly as provided.
- `spatial_bbox`: overrides the spatial area used to choose the granule and build the spatial Harmony request.
- `granule_concept_id`: forces the test to use a specific granule instead of selecting one from CMR.
- `temporal_fraction`: shrinks the temporal request to the middle portion of the granule time range.
- `members`: the list of collection concept IDs that belong to a collection group.

To replace generic tests for a provider, add to your overrides file:

```
{
  "providers": {
    "GES_DISC": {
      "replace_generic": true
    }
  }
}
```

To run both custom and generic for a collection, add:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "also_run_generic": true
    }
  }
}
```

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
      "skip_temporal": true,
      "spatial_bbox_scale": 0.9
    }
  }
}
```

## Disable generic tests
If you want to run only custom tests and skip generic ones:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "run_generic": false
    }
  }
}
```

You can also disable only one generic test type:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "run_generic_spatial": false
    }
  }
}
```
