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

## Skipping generic tests
By default:
- If a collection-level custom test exists, generic spatial/temporal tests are skipped.
- Provider-level custom tests run alongside generic tests unless you explicitly replace them.

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

## Grouping collections (list override)
You can apply one override block to multiple collections:

```
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
