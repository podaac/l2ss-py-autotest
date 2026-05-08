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

That means:
- For a collection-level custom test, you usually do not need anything in `overrides.json` just to skip the generic tests.
- For a provider-level custom test, add an override only if you want to suppress the generic tests too.

## Common Overrides
These are the main overrides for the default spatial and temporal tests.

- `generic_mode`: controls the generic spatial and temporal tests together. Use `all`, `spatial`, `temporal`, or `none`.
- `spatial_bbox`: overrides the spatial area used to choose the granule and build the spatial Harmony request.
- `granule_concept_id`: forces the test to use a specific granule instead of selecting one from CMR.

## Advanced Tuning
These options are still supported, but most users should not need them.

- `spatial_bbox_scale`: shrinks the spatial box relative to the chosen extent. Use `1.0` to keep the bbox exactly as provided.
- `temporal_fraction`: shrinks the temporal request to the middle portion of the granule time range.
- `members`: the list of collection concept IDs that belong to a collection group.

## Special-Case Overrides
Some collection or provider cases still need policy overrides beyond the default spatial and temporal tuning. Those are supported in the overrides file, but the normal path is to use `generic_mode`, `spatial_bbox`, and `granule_concept_id`.

To keep both generic spatial and temporal tests enabled for a collection, add:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "generic_mode": "all"
    }
  }
}
```

To run only the generic spatial test for a collection, add:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "generic_mode": "spatial"
    }
  }
}
```

To disable the generic tests for a collection, add:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "generic_mode": "none"
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

You can use the same pattern for a provider override:

```
{
  "providers": {
    "GES_DISC": {
      "generic_mode": "none"
    }
  }
}
```

That disables the generic spatial and temporal tests for every collection under that provider.

`also_run_generic` is only used for collection or group custom tests, where generic tests are skipped by default.
For provider overrides, use `generic_mode` or `replace_generic` instead.

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

## Disable Generic Tests
If you want to run only custom tests and skip generic ones:

```
{
  "collections": {
    "C1234567890-GES_DISC": {
      "generic_mode": "none"
    }
  }
}
```
