# DANDI Incremental Sync System

This document explains how to use the new incremental sync system for DANDI metadata.

## Overview

The `sync_dandi_incremental` management command provides an efficient way to keep your local DANDI metadata up-to-date by only syncing data that has changed since the last update.

## Features

- **Incremental Updates**: Only syncs dandisets and assets that have been modified since the last update
- **Smart Asset Filtering**: Skips asset checking for unchanged dandisets (major performance boost)
- **Progress Tracking**: Comprehensive progress bars with tqdm to monitor sync progress
- **Flexible Options**: Sync specific dandisets, date ranges, or different data types
- **Dry Run Mode**: Preview what would be updated without making changes
- **Detailed Logging**: Verbose mode shows exactly what's being processed
- **Sync History**: Tracks sync history and performance metrics

## Installation

Make sure you have the required dependencies:

```bash
pip install -r requirements.txt
```

## Basic Usage

### Full Incremental Sync
```bash
python manage.py sync_dandi_incremental
```

This will:
1. Check when the last sync occurred
2. Find all dandisets modified since then
3. Update only the changed dandisets and their assets
4. Show progress bars for each step

### Dry Run (Preview Changes)
```bash
python manage.py sync_dandi_incremental --dry-run
```

See what would be updated without making any changes.

### Force Full Sync
```bash
python manage.py sync_dandi_incremental --force-full-sync
```

Ignore the last sync timestamp and update everything.

## Advanced Options

### Sync Specific Dandiset
```bash
python manage.py sync_dandi_incremental --dandiset-id DANDI:000003
```

### Sync Since Specific Date
```bash
python manage.py sync_dandi_incremental --since 2024-01-01
python manage.py sync_dandi_incremental --since 2024-01-01T12:00:00Z
```

### Sync Only Dandisets (Skip Assets)
```bash
python manage.py sync_dandi_incremental --dandisets-only
```

### Sync Only Assets (Skip Dandiset Metadata)
```bash
python manage.py sync_dandi_incremental --assets-only
```

### Verbose Output
```bash
python manage.py sync_dandi_incremental --verbose
```

Shows detailed information about what's being processed and any errors.

### Disable Progress Bars (for Logging)
```bash
python manage.py sync_dandi_incremental --no-progress
```

Useful when running in automated scripts or logging to files.

### Limit Assets per Dandiset
```bash
python manage.py sync_dandi_incremental --max-assets 1000
```

Limits the number of assets processed per dandiset (default: 2000). This is useful for managing performance when dealing with dandisets that have very large numbers of assets.

## Progress Tracking

The command shows multiple levels of progress:

1. **Dandiset Filtering**: "Checking dandisets for updates"
2. **Dandiset Updates**: "Updating dandisets" 
3. **Asset Filtering**: "Checking assets for DANDI:000XXX"
4. **Asset Updates**: "Updating assets for DANDI:000XXX"

Each progress bar shows:
- Current item being processed
- Processing rate (items/second)
- Estimated time remaining
- Total progress

## Example Output

```
Initializing DANDI client...
Last sync: 2024-06-14 15:30:45+00:00
Fetching dandisets from DANDI API...
Checking dandisets for updates: 100%|██████████| 500/500 [02:15<00:00,  3.70dandiset/s]
Found 12 dandisets to update
Updating dandisets: 100%|██████████| 12/12 [01:30<00:00,  7.50s/dandiset]
Syncing assets...
Processing dandisets for asset updates: 100%|██████████| 12/12 [15:45<00:00, 78.75s/dandiset]

==================================================
SYNC SUMMARY
==================================================
Duration: 1125.50 seconds
Dandisets checked: 500
Dandisets updated: 12
Assets checked: 45670
Assets updated: 1203
Errors: 0
Sync completed successfully
```

## Sync Tracking

The system automatically tracks sync history in the `SyncTracker` model:

- When each sync occurred
- How long it took
- How many items were checked vs updated
- Type of sync performed

## Performance Tips

1. **Regular Incremental Syncs**: Run incremental syncs frequently (daily/weekly) to minimize data transfer
2. **Use Specific Dandisets**: When working on specific datasets, use `--dandiset-id` to focus on just what you need
3. **Separate Dandisets and Assets**: Use `--dandisets-only` for quick metadata updates, then `--assets-only` for asset details
4. **Monitor Progress**: Use `--verbose` to identify bottlenecks

## Error Handling

The command is designed to be robust:
- Individual errors don't stop the entire sync
- Errors are counted and reported in the summary
- Use `--verbose` to see detailed error messages
- Failed items are skipped and logged

## Automation

For automated syncing, consider:

```bash
# Cron job example (daily at 2 AM)
0 2 * * * cd /path/to/dandi-sql && python manage.py sync_dandi_incremental --no-progress >> /var/log/dandi-sync.log 2>&1
```

## Comparison with Original Method

### Original Method (load_sample_data.py)
- Always downloads ALL dandisets and assets
- No progress tracking
- No incremental updates
- Slower for regular updates

### New Incremental Sync
- Only downloads changed data
- Comprehensive progress tracking  
- Tracks sync history
- Much faster for regular updates
- Flexible filtering options

## Troubleshooting

### No Progress Bars Showing
Try `--verbose` to see if the command is running properly.

### Sync Takes Too Long
- Use `--dandisets-only` first for quick metadata updates
- Use `--dandiset-id` to focus on specific datasets
- Check network connectivity to DANDI API

### Out of Date Dependencies
```bash
pip install --upgrade dandi tqdm
```

### Database Connection Issues
Check your database settings in `settings.py` and ensure the database is accessible.
