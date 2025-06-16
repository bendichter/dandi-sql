# Direct SQL Query API

A secure REST API for executing raw SQL queries against the DANDI database with comprehensive security protections.

## Overview

This API allows you to execute complex SQL queries directly against the DANDI database while maintaining strict security controls. It provides maximum flexibility for analytical queries while preventing any data modification or security risks.

## Security Features

### ✅ Multiple Protection Layers
- **Read-only enforcement**: Only SELECT statements allowed
- **Table restrictions**: Access limited to DANDI dataset tables only
- **SQL injection prevention**: Advanced pattern detection and SQL parsing
- **Query complexity limits**: Prevents resource exhaustion
- **Automatic result limits**: Maximum 1000 results per query
- **Session-level read-only mode**: Database connection set to read-only

### 🚫 Blocked Operations
- Write operations: `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.
- System functions: `EXEC`, `SET`, `SHOW`, etc.
- Dangerous patterns: Multiple statements, hex encoding, file operations
- Unauthorized tables: Only `dandisets_*` tables accessible

## API Endpoints

### Execute SQL Query
```
POST /api/sql/execute/
Content-Type: application/json

{
  "sql": "SELECT id, name FROM dandisets_dandiset LIMIT 10"
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {"id": 1, "name": "Dataset Name"},
    ...
  ],
  "metadata": {
    "row_count": 10,
    "column_count": 2,
    "columns": ["id", "name"],
    "sql_executed": "SELECT id, name FROM dandisets_dandiset LIMIT 10"
  }
}
```

### Validate SQL Query
```
POST /api/sql/validate/
Content-Type: application/json

{
  "sql": "SELECT * FROM dandisets_dandiset"
}
```

**Response:**
```json
{
  "valid": true,
  "message": "SQL query is valid and safe",
  "secured_sql": "SELECT * FROM dandisets_dandiset LIMIT 1000"
}
```

### Get Schema Information
```
GET /api/sql/schema/
GET /api/sql/schema/?table=dandisets_dandiset
```

**Response:**
```json
{
  "allowed_tables": ["dandisets_dandiset", "dandisets_asset", ...]
}
```

## Available Tables

### Core Tables
- `dandisets_dandiset` - Dataset metadata
- `dandisets_asset` - Individual files/sessions  
- `dandisets_participant` - Subject information
- `dandisets_assetdandiset` - Asset-dataset relationships
- `dandisets_assetwasattributedto` - Asset-participant relationships

### Reference Tables
- `dandisets_species` - Species information
- `dandisets_anatomy` - Anatomical regions
- `dandisets_approach` - Experimental approaches
- `dandisets_measurementtechnique` - Measurement methods

## Example Queries

### Simple Dataset Search
```sql
SELECT id, name, description 
FROM dandisets_dandiset 
WHERE name ILIKE '%mouse%' 
ORDER BY name 
LIMIT 20
```

### Complex Analysis: Datasets with Multiple Subjects Having Multiple Sessions
```sql
SELECT d.id, d.name, qualified_subjects.subject_count 
FROM dandisets_dandiset d 
JOIN (
    SELECT sessions_per_subject.dandiset_id, 
           COUNT(DISTINCT sessions_per_subject.participant_id) as subject_count
    FROM (
        SELECT ad.dandiset_id, awo.participant_id, COUNT(*) as session_count
        FROM dandisets_asset a 
        JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id
        JOIN dandisets_assetwasattributedto awo ON a.id = awo.asset_id
        WHERE UPPER(a.variable_measured::text) LIKE UPPER('%ElectricalSeries%')
        GROUP BY ad.dandiset_id, awo.participant_id
        HAVING COUNT(*) >= 3
    ) sessions_per_subject
    GROUP BY sessions_per_subject.dandiset_id
    HAVING COUNT(DISTINCT sessions_per_subject.participant_id) >= 3
) qualified_subjects ON d.id = qualified_subjects.dandiset_id
ORDER BY qualified_subjects.subject_count DESC
```

### Asset Analysis by Variable Measured
```sql
SELECT 
    a.variable_measured,
    COUNT(*) as asset_count,
    COUNT(DISTINCT ad.dandiset_id) as dataset_count
FROM dandisets_asset a
JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id
WHERE a.variable_measured IS NOT NULL
GROUP BY a.variable_measured
ORDER BY asset_count DESC
```

## Query Limits

- **Maximum query length**: 10,000 characters
- **Maximum results**: 1,000 rows (automatically applied)
- **Maximum JOINs**: 10 per query
- **Maximum subqueries**: 5 levels deep
- **Maximum WHERE conditions**: 50 per query

## Error Handling

The API returns detailed error messages for:
- Invalid SQL syntax
- Security violations
- Unauthorized table access
- Query complexity limits exceeded
- Execution errors

## Best Practices

1. **Use LIMIT clauses** to avoid large result sets
2. **Filter early** with WHERE clauses for better performance  
3. **Use indexes** - filter on `id`, `name`, `created_at` fields when possible
4. **Test with validate endpoint** before executing complex queries
5. **Use JOINs efficiently** - prefer INNER JOIN over subqueries when possible

## Production Deployment Notes

For production deployment, consider:

1. **Database User**: Create a dedicated read-only database user
2. **Connection Pooling**: Configure connection limits
3. **Rate Limiting**: Add API rate limiting middleware
4. **Monitoring**: Log query patterns and performance
5. **Caching**: Cache schema information and common queries

## Example Use Cases

- **Dataset Discovery**: Find datasets matching specific criteria
- **Data Quality Analysis**: Analyze missing fields or data patterns
- **Cross-dataset Studies**: Compare variables across multiple datasets
- **Subject Analysis**: Find subjects with specific characteristics
- **Session Analysis**: Analyze recording sessions and their properties

This API provides the full SQL flexibility you requested while maintaining security through multiple layers of protection.
