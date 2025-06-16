# DANDI Search API Documentation

## Overview

The DANDI Search API provides a REST endpoint for searching dandisets programmatically. It supports all the same filters and functionality as the web search interface.

## Endpoint

```
GET /api/search/
```

## Query Parameters

### Basic Search
- `search`: Text search in dandiset name and description
- `page`: Page number for pagination (default: 1)
- `per_page`: Results per page (default: 10, max: 100)
- `format`: Response format - 'summary' or 'detailed' (default: 'summary')

### Asset Inclusion Options
- `include_assets`: Include matching assets in dandiset results ('true' or 'false', default: 'false')
- `assets_per_dandiset`: Number of assets to include per dandiset (default: 5, max: 20)
- `include_asset_pagination`: Include paginated asset results across all dandisets ('true' or 'false', default: 'false')
- `assets_page`: Page number for asset pagination (default: 1)
- `assets_per_page`: Assets per page in asset pagination (default: 20, max: 100)

### Filtering Options
- `species`: Species filter (ID or name) - supports multiple values
- `anatomy`: Anatomy filter (ID or name) - supports multiple values
- `approach`: Approach filter (ID or name) - supports multiple values
- `measurement_technique`: Measurement technique filter (ID or name) - supports multiple values
- `sex`: Subject sex filter (ID or name) - supports multiple values
- `data_standards`: Data standards filter (ID or name) - supports multiple values
- `file_format`: File format filter - supports multiple values
- `variables_measured`: Variables measured filter - supports multiple values

### Numeric Range Filters
- `min_subjects`, `max_subjects`: Number of subjects range
- `min_files`, `max_files`: Number of files range
- `min_size`, `max_size`: Size range in GB
- `asset_min_size`, `asset_max_size`: Asset size range in MB

### Date Range Filters
- `pub_date_start`, `pub_date_end`: Publication date range (YYYY-MM-DD format)
- `created_date_start`, `created_date_end`: Creation date range (YYYY-MM-DD format)

### Asset-Specific Filters
- `asset_path`: Asset path search
- `asset_dandiset_id`: Asset dandiset ID filter
- `asset_sex`: Asset subject sex filter (ID or name) - supports multiple values

## Example Requests

### Basic Search
```bash
curl "http://localhost:8000/api/search/?search=mouse&per_page=5"
```

### Filter by Species and Approach
```bash
curl "http://localhost:8000/api/search/?species=Mus%20musculus&approach=electrophysiology&format=detailed"
```

### Complex Filtering
```bash
curl "http://localhost:8000/api/search/?min_subjects=10&max_subjects=100&file_format=application/x-nwb&pub_date_start=2023-01-01"
```

### Pagination
```bash
curl "http://localhost:8000/api/search/?page=2&per_page=20"
```

## Response Format

### Summary Format (default)
```json
{
  "results": [
    {
      "id": 1,
      "dandi_id": "DANDI:000001/0.230301.1234",
      "name": "Example Dataset",
      "description": "Short description...",
      "date_published": "2023-03-01T12:00:00Z",
      "url": "https://dandiarchive.org/dandiset/000001",
      "summary": {
        "subjects": 25,
        "files": 150,
        "size_bytes": 1234567890
      }
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total_pages": 5,
    "total_count": 42,
    "has_previous": false,
    "has_next": true,
    "start_index": 1,
    "end_index": 10
  },
  "filters_applied": {
    "search": "mouse",
    "species": ["Mus musculus"]
  },
  "statistics": {
    "total_dandisets": 42,
    "total_subjects": 1250,
    "total_files": 8500,
    "total_bytes": 25000000000,
    "total_assets": 8500
  },
  "meta": {
    "query_time": null,
    "api_version": "1.0",
    "format": "summary"
  }
}
```

### Detailed Format
```json
{
  "results": [
    {
      "id": 1,
      "dandi_id": "DANDI:000001/0.230301.1234",
      "base_id": "DANDI:000001",
      "name": "Example Dataset",
      "description": "Full description of the dataset...",
      "date_created": "2023-01-15T10:30:00Z",
      "date_published": "2023-03-01T12:00:00Z",
      "date_modified": "2023-02-28T15:45:00Z",
      "url": "https://dandiarchive.org/dandiset/000001",
      "assets_summary": {
        "number_of_subjects": 25,
        "number_of_files": 150,
        "number_of_bytes": 1234567890,
        "variable_measured": ["membrane potential", "spike times"]
      }
    }
  ],
  "pagination": { ... },
  "filters_applied": { ... },
  "statistics": { ... },
  "meta": { ... }
}
```

## Error Responses

### 500 Internal Server Error
```json
{
  "error": "Search API error: Detailed error message",
  "status": "error"
}
```

## Asset Search API

A dedicated endpoint for searching assets across all dandisets:

```
GET /api/assets/search/
```

### Asset-Specific Query Parameters
- `asset_path`: Asset path search
- `file_format`: File format filter
- `encoding_format`: Encoding format filter (alias for file_format)
- `asset_min_size`, `asset_max_size`: Asset size range in MB
- `asset_dandiset_id`: Asset dandiset ID filter
- `asset_sex`: Asset subject sex filter (ID or name)
- `date_created_start`, `date_created_end`: Asset creation date range
- `page`: Page number for pagination (default: 1)
- `per_page`: Results per page (default: 20, max: 100)
- `format`: Response format ('summary' or 'detailed', default: 'summary')
- `order_by`: Order results by field (default: 'path')

### Example Asset Search Requests

```bash
# Search for NWB files
curl "http://localhost:8000/api/assets/search/?file_format=application/x-nwb"

# Search for large assets (>100MB)
curl "http://localhost:8000/api/assets/search/?asset_min_size=100&order_by=-content_size"

# Search assets by path
curl "http://localhost:8000/api/assets/search/?asset_path=sub-001&format=detailed"
```

### Asset Search Response Format

```json
{
  "results": [
    {
      "id": 123,
      "path": "sub-001/ses-001/ephys/sub-001_ses-001_ecephys.nwb",
      "encoding_format": "application/x-nwb",
      "content_size_mb": 45.6,
      "date_created": "2023-03-01T12:00:00Z",
      "dandiset": {
        "id": 1,
        "dandi_id": "DANDI:000001/0.230301.1234",
        "name": "Example Dataset"
      }
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_pages": 5,
    "total_count": 89,
    "has_previous": false,
    "has_next": true,
    "start_index": 1,
    "end_index": 20
  },
  "filters_applied": {
    "file_format": ["application/x-nwb"]
  },
  "meta": {
    "query_time": null,
    "api_version": "1.0",
    "format": "summary",
    "order_by": "path"
  }
}
```

## Filter Options API

Get available filter options:
```bash
curl "http://localhost:8000/api/filter-options/"
```

Returns lists of available species, anatomy, approaches, measurement techniques, and data standards.

## Notes

- The API uses the same search logic as the web interface, ensuring consistency
- All filters can be combined for complex queries
- Multiple values for the same parameter should be sent as separate query parameters
- Date parameters should be in ISO format (YYYY-MM-DD)
- Size parameters are in GB for dandiset-level filters and MB for asset-level filters
- The API supports both numeric IDs and text names for most categorical filters

## Integration with Web Interface

The web search interface now uses the same underlying search function as the API, ensuring that search results are consistent between the web UI and programmatic access.
