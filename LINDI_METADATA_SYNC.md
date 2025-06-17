# LINDI Metadata Sync

This document describes how to sync LINDI metadata for NWB assets in the DANDI database.

## Overview

LINDI (Linked Data for NWB) files contain metadata about NWB (Neurodata Without Borders) files that describe the structure and organization of neuroscience data. The LINDI metadata sync command downloads these files from `lindi.neurosift.org` and stores filtered metadata in the database.

## What is LINDI?

LINDI files are JSON representations that contain:
- **Generation metadata**: Information about how the LINDI file was created
- **Structure metadata**: Hierarchical organization of groups, datasets, and attributes from the NWB file
- **Data references**: Pointers to actual data (which we filter out to save space)

## Database Schema

The `LindiMetadata` model stores:
- `asset`: One-to-one relationship with Asset model
- `structure_metadata`: Complete filtered LINDI structure (JSON field)
- `lindi_url`: URL to the original LINDI file
- `processed_at`: When the metadata was processed
- `processing_version`: Version of processing logic used
- `sync_tracker`: Reference to the sync operation that processed this metadata

## Management Command

### Basic Usage

```bash
# Sync LINDI metadata for all NWB assets without existing metadata
python manage.py sync_lindi_metadata

# Dry run to see what would be processed
python manage.py sync_lindi_metadata --dry-run

# Process specific dandiset
python manage.py sync_lindi_metadata --dandiset-id 000409

# Process specific asset
python manage.py sync_lindi_metadata --asset-id 37ca1798-b14c-4224-b8f0-037e27725336

# Force refresh of existing metadata
python manage.py sync_lindi_metadata --force-refresh

# Verbose output for debugging
python manage.py sync_lindi_metadata --verbose
```

### Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Show what would be processed without making changes | False |
| `--force-refresh` | Force refresh of all LINDI metadata, ignoring existing records | False |
| `--dandiset-id` | Process only assets from a specific dandiset (e.g., 000409) | None |
| `--asset-id` | Process only a specific asset by its dandi_asset_id | None |
| `--verbose` | Show detailed progress and debug information | False |
| `--no-progress` | Disable progress bars (useful for logging) | False |
| `--max-assets` | Maximum number of assets to process | 1000 |
| `--timeout` | HTTP timeout in seconds | 30 |

### Examples

#### Process a specific dandiset
```bash
python manage.py sync_lindi_metadata --dandiset-id 000409 --verbose
```

#### Process all assets with no limit
```bash
python manage.py sync_lindi_metadata --max-assets 999999
```

#### Run in production with logging
```bash
python manage.py sync_lindi_metadata --no-progress --max-assets 5000 > lindi_sync.log 2>&1
```

## Data Filtering

The command filters LINDI data to exclude:

1. **Base64-encoded data**: Large binary data encoded as base64 strings
2. **Array chunks**: Data arrays in the format `[chunks, dtype, shape]`

This filtering significantly reduces database storage while preserving the structural metadata that describes the organization and schema of the NWB files.

### Example of what gets filtered out:
```json
{
  "acquisition/ElectricalSeries/data": ["base64:SGVsbG8gV29ybGQ="],
  "processing/units/spike_times": [[[0, 1000]], "float64", [2, 1000]]
}
```

### Example of what gets kept:
```json
{
  "acquisition/.zattrs": {"neurodata_type": "ElectricalSeries"},
  "acquisition/.zgroup": {"zarr_format": 2},
  "processing/units/.zattrs": {"neurodata_type": "Units"}
}
```

## Monitoring and Tracking

### Sync Tracker
Each sync operation creates a `SyncTracker` record with:
- Sync type: `'lindi'`
- Status: `'running'`, `'completed'`, `'failed'`, or `'cancelled'`
- Statistics: Number of assets processed, errors encountered, duration
- Error messages for failed operations

### Checking Status
```python
from dandisets.models import SyncTracker, LindiMetadata

# Get latest LINDI sync
latest_sync = SyncTracker.objects.filter(sync_type='lindi').first()
print(f"Status: {latest_sync.status}")
print(f"Processed: {latest_sync.lindi_metadata_processed}")

# Count total LINDI metadata records
total_lindi = LindiMetadata.objects.count()
print(f"Total LINDI metadata records: {total_lindi}")
```

## Querying LINDI Metadata

### Basic Queries
```python
from dandisets.models import Asset, LindiMetadata

# Get all assets with LINDI metadata
assets_with_lindi = Asset.objects.filter(lindi_metadata__isnull=False)

# Get LINDI metadata for a specific asset
asset = Asset.objects.get(dandi_asset_id='37ca1798-b14c-4224-b8f0-037e27725336')
lindi = asset.lindi_metadata
structure = lindi.structure_metadata

# Access generation metadata
generation_info = structure.get('generationMetadata', {})

# Access NWB structure
refs = structure.get('refs', {})
```

### Advanced Queries
```python
# Find assets with specific NWB structures
from django.db.models import Q

# Assets with ElectricalSeries data
electrical_series_assets = LindiMetadata.objects.filter(
    structure_metadata__refs__has_key='acquisition/ElectricalSeries'
).select_related('asset')

# Assets with Units processing module
units_assets = LindiMetadata.objects.filter(
    structure_metadata__refs__has_key='processing/units'
).select_related('asset')
```

## Error Handling

The command handles various error conditions:

1. **Network timeouts**: Configurable timeout for HTTP requests
2. **Missing LINDI files**: 404 errors are logged but don't stop processing
3. **Invalid JSON**: Malformed LINDI files are skipped with error logging
4. **Database errors**: Transactional safety ensures partial updates don't corrupt data

## Performance Considerations

- **Batch processing**: Processes assets in configurable batches (default: 1000)
- **Progress tracking**: Visual progress bars for interactive use
- **Memory management**: Streams JSON data to avoid loading large files into memory
- **Database optimization**: Uses `select_related` and `prefetch_related` for efficient queries

## URL Construction

LINDI URLs follow the pattern:
```
https://lindi.neurosift.org/dandi/dandisets/{dandiset_id}/assets/{asset_id}/nwb.lindi.json
```

Where:
- `dandiset_id`: Zero-padded 6-digit dandiset ID (e.g., `000409`)
- `asset_id`: Full DANDI asset ID (e.g., `37ca1798-b14c-4224-b8f0-037e27725336`)

## Integration with Existing Sync Commands

The LINDI sync is independent of the main DANDI sync (`sync_dandi_incremental`) but can be run as part of a complete sync workflow:

```bash
# Full sync workflow
python manage.py sync_dandi_incremental --sync-type full
python manage.py sync_lindi_metadata --max-assets 5000
```

## Troubleshooting

### Common Issues

1. **No LINDI files found**: Some assets may not have LINDI files available yet
2. **Timeout errors**: Increase `--timeout` for slow network connections
3. **Memory issues**: Reduce `--max-assets` for large datasets

### Debug Mode
```bash
python manage.py sync_lindi_metadata --verbose --dandiset-id 000409 --max-assets 10
```

### Checking Migration Status
```bash
python manage.py showmigrations dandisets
```

Look for:
- `[X] 0007_add_lindi_metadata`
- `[X] 0008_update_lindi_metadata_fields`
