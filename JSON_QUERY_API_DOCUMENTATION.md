# JSON Query Builder API Documentation

The JSON Query Builder provides a powerful, SQL-like API for querying DANDI datasets with full flexibility while maintaining security through read-only access and validation.

## Overview

This API allows you to construct complex queries using JSON syntax that translates to Django ORM operations. You can perform sophisticated analyses like:

- Finding dandisets with specific subject counts and measurement types
- Aggregating data across multiple related models
- Filtering with complex conditions and relationships
- Combining multiple criteria with annotations and subqueries

## API Endpoints

### Base URL: `/api/query/`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `execute/` | POST | Execute a JSON query and return results |
| `validate/` | POST | Validate a query without executing it |
| `explain/` | POST | Get the SQL execution plan for a query |
| `schema/` | GET | Get schema information and available fields |
| `examples/` | GET | Get example queries for common use cases |

## Query Structure

### Basic Query Format

```json
{
  "model": "ModelName",
  "fields": ["field1", "field2", "related__field"],
  "filters": {
    "field__operation": "value"
  },
  "annotations": {
    "computed_field": {
      "expression": "Count",
      "field": "related_field",
      "filter": {...}
    }
  },
  "order_by": ["field", "-another_field"],
  "limit": 100,
  "offset": 0,
  "distinct": false
}
```

### Available Models

- **Dandiset**: DANDI dataset metadata and information
- **Asset**: Individual files and data assets within dandisets
- **Participant**: Subjects/participants in experiments
- **Activity**: Research activities and experimental sessions
- **Contributor**: People and organizations who contributed to datasets

## Complex Query Examples

### 1. Basic Search - Dandisets with "mouse" in the name

```json
{
  "model": "Dandiset",
  "fields": ["id", "name", "description", "date_published"],
  "filters": {
    "name__icontains": "mouse"
  },
  "order_by": ["name"],
  "limit": 10
}
```

### 2. Your Use Case: Dandisets with ≥3 subjects having ≥2 ElectricalSeries assets

This solves your exact requirement: "all dandisets where there are at least 3 subjects that have at least 2 assets that contain the ElectricalSeries variable measured."

```json
{
  "model": "Dandiset",
  "fields": ["id", "name", "description", "date_published"],
  "annotations": {
    "subjects_with_electrical_series": {
      "expression": "Count",
      "field": "assets__attributed_to__participant",
      "distinct": true,
      "filter": {
        "assets__variable_measured__icontains": "ElectricalSeries"
      }
    },
    "electrical_series_asset_count": {
      "expression": "Count",
      "field": "assets",
      "filter": {
        "assets__variable_measured__icontains": "ElectricalSeries"
      }
    }
  },
  "filters": {
    "subjects_with_electrical_series__gte": 3,
    "electrical_series_asset_count__gte": 2
  },
  "order_by": ["-subjects_with_electrical_series", "-electrical_series_asset_count"]
}
```

### 3. More Complex Subject Analysis

Find dandisets with at least 3 mouse subjects where each subject has at least 2 ElectricalSeries assets:

```json
{
  "model": "Dandiset",
  "fields": ["id", "name", "description"],
  "annotations": {
    "mouse_subjects_with_sufficient_data": {
      "expression": "Count",
      "field": "assets__attributed_to__participant",
      "distinct": true,
      "filter": {
        "assets__attributed_to__participant__species__name__icontains": "mouse",
        "assets__variable_measured__icontains": "ElectricalSeries"
      }
    },
    "total_mouse_electrical_assets": {
      "expression": "Count",
      "field": "assets",
      "filter": {
        "assets__attributed_to__participant__species__name__icontains": "mouse",
        "assets__variable_measured__icontains": "ElectricalSeries"
      }
    }
  },
  "filters": {
    "mouse_subjects_with_sufficient_data__gte": 3,
    "total_mouse_electrical_assets__gte": 6
  },
  "order_by": ["-total_mouse_electrical_assets"]
}
```

### 4. Large NWB Files with Specific Measurements

```json
{
  "model": "Asset",
  "fields": ["id", "path", "content_size", "dandisets__name", "variable_measured"],
  "filters": {
    "encoding_format": "application/x-nwb",
    "content_size__gt": 1073741824,
    "variable_measured__icontains": "ElectricalSeries"
  },
  "order_by": ["-content_size"],
  "limit": 20
}
```

### 5. Multi-Species Analysis

Find dandisets containing both mouse and rat data with ElectricalSeries:

```json
{
  "model": "Dandiset",
  "fields": ["id", "name", "description"],
  "annotations": {
    "mouse_count": {
      "expression": "Count",
      "field": "assets__attributed_to__participant",
      "distinct": true,
      "filter": {
        "assets__attributed_to__participant__species__name__icontains": "mouse"
      }
    },
    "rat_count": {
      "expression": "Count",
      "field": "assets__attributed_to__participant",
      "distinct": true,
      "filter": {
        "assets__attributed_to__participant__species__name__icontains": "rat"
      }
    },
    "electrical_series_count": {
      "expression": "Count",
      "field": "assets",
      "filter": {
        "assets__variable_measured__icontains": "ElectricalSeries"
      }
    }
  },
  "filters": {
    "mouse_count__gte": 1,
    "rat_count__gte": 1,
    "electrical_series_count__gte": 1
  },
  "order_by": ["-electrical_series_count"]
}
```

## Filter Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `eq`, `exact` | Exact match | `"name": "value"` |
| `iexact` | Case-insensitive exact | `"name__iexact": "VALUE"` |
| `gt`, `gte`, `lt`, `lte` | Numeric comparisons | `"count__gte": 5` |
| `contains`, `icontains` | String containment | `"name__icontains": "mouse"` |
| `startswith`, `endswith` | String prefix/suffix | `"path__endswith": ".nwb"` |
| `in` | List membership | `"id__in": [1, 2, 3]` |
| `isnull` | Null checks | `"field__isnull": false` |
| `range` | Range queries | `"date__range": ["2023-01-01", "2023-12-31"]` |
| `year`, `month`, `day` | Date components | `"date_published__year": 2023` |

## Aggregation Functions

| Function | Description | Use Case |
|----------|-------------|----------|
| `Count` | Count records/values | Subject counts, asset counts |
| `Sum` | Sum numeric values | Total file sizes |
| `Avg` | Average values | Average file size |
| `Max`, `Min` | Maximum/minimum | Largest file, oldest date |
| `ArrayAgg` | Aggregate into array | Collect all species names |
| `StringAgg` | Concatenate strings | Join measurement types |

## Making API Calls

### Execute Query

```bash
curl -X POST http://localhost:8000/api/query/execute/ \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Dandiset",
    "fields": ["id", "name"],
    "filters": {"name__icontains": "mouse"},
    "limit": 5
  }'
```

### Validate Query

```bash
curl -X POST http://localhost:8000/api/query/validate/ \
  -H "Content-Type: application/json" \
  -d '{"model": "Dandiset", "fields": ["id", "name"]}'
```

### Get Schema Information

```bash
curl http://localhost:8000/api/query/schema/
curl http://localhost:8000/api/query/schema/?model=Dandiset
```

### Get Examples

```bash
curl http://localhost:8000/api/query/examples/
curl http://localhost:8000/api/query/examples/?model=Asset
```

## Response Format

### Successful Query Response

```json
{
  "success": true,
  "results": [
    {
      "id": 1,
      "name": "Mouse Dataset",
      "description": "...",
      "subjects_with_electrical_series": 5
    }
  ],
  "metadata": {
    "count": 1,
    "model": "Dandiset",
    "query_complexity": 15,
    "sql": "SELECT ..."
  },
  "query": {...}
}
```

### Error Response

```json
{
  "success": false,
  "error": "Field 'invalid_field' is not allowed for model 'Dandiset'",
  "results": []
}
```

## Security and Limitations

### Read-Only Access
- No write operations allowed
- All queries are validated before execution
- Only whitelisted models and fields accessible

### Query Limits
- Maximum 50 filters per query
- Maximum 20 annotations per query
- Maximum 10,000 result limit
- Maximum join depth of 5 levels
- Complexity scoring prevents resource abuse

### Allowed Field Patterns

**Dandiset Fields:**
- Basic: `id`, `name`, `description`, `date_published`, etc.
- Asset relationships: `assets__*`
- Participant data: `assets__attributed_to__participant__*`
- Summary data: `assets_summary__*`

**Asset Fields:**
- Basic: `id`, `path`, `content_size`, `encoding_format`, etc.
- Dandiset relationships: `dandisets__*`
- Participant relationships: `attributed_to__participant__*`

## Advanced Patterns

### Subqueries

```json
{
  "model": "Dandiset",
  "filters": {
    "id__in": {
      "subquery": {
        "model": "Asset",
        "filters": {"variable_measured__icontains": "ElectricalSeries"},
        "values": "dandisets__id"
      }
    }
  }
}
```

### Complex Annotations with Filtering

```json
{
  "annotations": {
    "large_electrical_assets": {
      "expression": "Count",
      "field": "assets",
      "filter": {
        "assets__variable_measured__icontains": "ElectricalSeries",
        "assets__content_size__gt": 1000000000
      }
    }
  }
}
```

### Date Range Queries

```json
{
  "filters": {
    "date_published__range": ["2023-01-01", "2023-12-31"],
    "date_published__year__gte": 2020
  }
}
```

## Common Use Cases and Solutions

### 1. Quality Analysis
Find dandisets with good data coverage:

```json
{
  "model": "Dandiset",
  "annotations": {
    "subject_count": {"expression": "Count", "field": "assets__attributed_to__participant", "distinct": true},
    "asset_count": {"expression": "Count", "field": "assets"},
    "total_size": {"expression": "Sum", "field": "assets__content_size"}
  },
  "filters": {
    "subject_count__gte": 5,
    "asset_count__gte": 10,
    "total_size__gte": 1000000000
  }
}
```

### 2. Cross-Dataset Analysis
Compare datasets by measurement types:

```json
{
  "model": "Dandiset",
  "annotations": {
    "measurement_types": {"expression": "ArrayAgg", "field": "assets__variable_measured", "distinct": true}
  },
  "filters": {
    "assets__variable_measured__isnull": false
  }
}
```

### 3. Temporal Analysis
Find recent datasets with specific criteria:

```json
{
  "model": "Dandiset",
  "filters": {
    "date_published__year": 2023,
    "assets__variable_measured__icontains": "ElectricalSeries"
  },
  "order_by": ["-date_published"]
}
```

This API gives you full SQL-like flexibility while maintaining security through validation and read-only access, perfectly suited for your complex analytical needs.
