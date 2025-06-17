# LINDI Metadata SQL Query Guide

This guide explains how to query LINDI metadata through the SQL API now that LINDI data has been integrated into the dandi-sql database.

## Overview

LINDI (Linked Data Interface) metadata provides structural information about NWB (Neurodata Without Borders) files, including:
- HDF5 group and dataset structures
- Dataset shapes and data types
- Attribute metadata
- File organization and hierarchy

The LINDI metadata is stored in the `dandisets_lindimetadata` table and can be queried using PostgreSQL JSON operations.

## Table Schema

The `dandisets_lindimetadata` table contains:

```sql
-- Get the schema of the LINDI metadata table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'dandisets_lindimetadata'
ORDER BY ordinal_position;
```

Key columns:
- `id`: Primary key
- `asset_id`: Foreign key to `dandisets_asset`
- `structure_metadata`: JSONB field containing the filtered LINDI structure
- `lindi_url`: URL where the original LINDI file was downloaded from
- `processing_version`: Version of the LINDI processing pipeline used
- `created_at`: When the metadata was first processed
- `updated_at`: When the metadata was last updated

## Basic Queries

### 1. Find NWB assets with LINDI metadata

```sql
SELECT a.path, a.dandi_asset_id, l.lindi_url
FROM dandisets_asset a
JOIN dandisets_lindimetadata l ON a.id = l.asset_id
WHERE a.encoding_format = 'application/x-nwb'
LIMIT 10;
```

### 2. Count NWB files with LINDI metadata by dandiset

```sql
SELECT d.identifier, d.name, COUNT(l.id) as lindi_count
FROM dandisets_dandiset d
JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
JOIN dandisets_asset a ON ad.asset_id = a.id
LEFT JOIN dandisets_lindimetadata l ON a.id = l.asset_id
WHERE a.encoding_format = 'application/x-nwb'
GROUP BY d.identifier, d.name
ORDER BY lindi_count DESC
LIMIT 20;
```

## JSON Querying

The `structure_metadata` field contains the filtered LINDI structure as JSONB. You can query it using PostgreSQL's JSON operators.

### 3. Explore the structure of LINDI metadata

```sql
-- Get the top-level keys in the structure_metadata
SELECT DISTINCT jsonb_object_keys(structure_metadata) as top_level_keys
FROM dandisets_lindimetadata
LIMIT 10;
```

### 4. Query generation metadata

```sql
-- Get LINDI generation metadata
SELECT 
    a.path,
    structure_metadata->'generationMetadata'->>'lindi_version' as lindi_version,
    structure_metadata->'generationMetadata'->>'source_url' as source_url,
    structure_metadata->'generationMetadata'->>'timestamp' as generation_timestamp
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id
WHERE structure_metadata ? 'generationMetadata'
LIMIT 10;
```

### 5. Find files with specific NWB groups

```sql
-- Find files that contain 'acquisition' groups
SELECT 
    a.path,
    a.dandi_asset_id,
    jsonb_object_keys(structure_metadata->'refs') as ref_key
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id
WHERE structure_metadata->'refs' ? 'acquisition'
LIMIT 10;
```

### 6. Query dataset shapes and types

```sql
-- Find datasets with their shapes (datasets are stored as objects with zarr_dtype and shape)
SELECT 
    a.path,
    ref_key,
    ref_value->>'zarr_dtype' as data_type,
    ref_value->>'shape' as shape
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id,
LATERAL jsonb_each(structure_metadata->'refs') as refs(ref_key, ref_value)
WHERE jsonb_typeof(ref_value) = 'object' 
  AND ref_value ? 'zarr_dtype'
  AND ref_value ? 'shape'
LIMIT 20;
```

### 7. Find files with specific data types

```sql
-- Find files containing float64 datasets
SELECT DISTINCT
    a.path,
    a.dandi_asset_id
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id,
LATERAL jsonb_each(structure_metadata->'refs') as refs(ref_key, ref_value)
WHERE ref_value->>'zarr_dtype' = 'float64'
LIMIT 10;
```

### 8. Analyze group structures

```sql
-- Find the most common group names across all NWB files
SELECT 
    split_part(ref_key, '/', 2) as top_level_group,
    COUNT(*) as occurrence_count
FROM dandisets_lindimetadata l,
LATERAL jsonb_object_keys(structure_metadata->'refs') as ref_key
WHERE ref_key LIKE '/%'
  AND split_part(ref_key, '/', 2) != ''
GROUP BY split_part(ref_key, '/', 2)
ORDER BY occurrence_count DESC
LIMIT 20;
```

### 9. Find files with specific attributes

```sql
-- Find files with session_description attributes
SELECT 
    a.path,
    ref_value->>'session_description' as session_description
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id,
LATERAL jsonb_each(structure_metadata->'refs') as refs(ref_key, ref_value)
WHERE jsonb_typeof(ref_value) = 'object' 
  AND ref_value ? 'session_description'
LIMIT 10;
```

### 10. Complex nested queries

```sql
-- Find electrophysiology data by looking for specific paths
SELECT DISTINCT
    a.path,
    a.dandi_asset_id,
    d.identifier as dandiset_id
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id
JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id
JOIN dandisets_dandiset d ON ad.dandiset_id = d.id,
LATERAL jsonb_object_keys(structure_metadata->'refs') as ref_key
WHERE ref_key LIKE '%/acquisition/%'
   OR ref_key LIKE '%/processing/ecephys%'
   OR ref_key LIKE '%ElectricalSeries%'
LIMIT 15;
```

## Advanced Use Cases

### 11. Data quality assessment

```sql
-- Find files with unusually large datasets (potential quality issues)
SELECT 
    a.path,
    ref_key,
    ref_value->>'shape' as shape,
    ref_value->>'zarr_dtype' as dtype
FROM dandisets_lindimetadata l
JOIN dandisets_asset a ON l.asset_id = a.id,
LATERAL jsonb_each(structure_metadata->'refs') as refs(ref_key, ref_value)
WHERE jsonb_typeof(ref_value) = 'object' 
  AND ref_value ? 'shape'
  AND (ref_value->>'shape')::text ~ '\[.*[0-9]{6,}.*\]'  -- Look for dimensions > 100k
LIMIT 10;
```

### 12. Cross-dandiset comparisons

```sql
-- Compare NWB structure complexity across dandisets
SELECT 
    d.identifier,
    d.name,
    AVG(jsonb_object_keys_count.key_count) as avg_structure_complexity
FROM dandisets_dandiset d
JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
JOIN dandisets_asset a ON ad.asset_id = a.id
JOIN dandisets_lindimetadata l ON a.id = l.asset_id,
LATERAL (SELECT COUNT(*) as key_count FROM jsonb_object_keys(structure_metadata->'refs')) as jsonb_object_keys_count
GROUP BY d.identifier, d.name
HAVING COUNT(l.id) > 1  -- Only dandisets with multiple NWB files
ORDER BY avg_structure_complexity DESC
LIMIT 15;
```

### 13. Find similar file structures

```sql
-- Find files with similar top-level structure
WITH file_structures AS (
    SELECT 
        l.id,
        a.path,
        array_agg(DISTINCT split_part(ref_key, '/', 2) ORDER BY split_part(ref_key, '/', 2)) as top_level_groups
    FROM dandisets_lindimetadata l
    JOIN dandisets_asset a ON l.asset_id = a.id,
    LATERAL jsonb_object_keys(structure_metadata->'refs') as ref_key
    WHERE ref_key LIKE '/%' AND split_part(ref_key, '/', 2) != ''
    GROUP BY l.id, a.path
)
SELECT 
    f1.path as file1,
    f2.path as file2,
    f1.top_level_groups as shared_structure
FROM file_structures f1
JOIN file_structures f2 ON f1.top_level_groups = f2.top_level_groups AND f1.id < f2.id
LIMIT 10;
```

## Performance Tips

1. **Use indexes**: The `asset_id` field is indexed for fast joins with the assets table.

2. **JSON path queries**: Use specific JSON paths rather than scanning all refs:
   ```sql
   WHERE structure_metadata->'refs' ? 'specific/path'
   ```

3. **Limit results**: Always use LIMIT for exploratory queries since LINDI metadata can be large.

4. **Use CTEs**: For complex queries, break them into Common Table Expressions (CTEs) for better readability and performance.

## Integration with Other Tables

### 14. Combine with asset metadata

```sql
-- Find correlation between file size and structural complexity
SELECT 
    a.content_size,
    COUNT(refs.*) as structure_element_count,
    a.path
FROM dandisets_asset a
JOIN dandisets_lindimetadata l ON a.id = l.asset_id,
LATERAL jsonb_each(structure_metadata->'refs') as refs
WHERE a.encoding_format = 'application/x-nwb'
GROUP BY a.id, a.content_size, a.path
ORDER BY structure_element_count DESC
LIMIT 20;
```

### 15. Combine with species information

```sql
-- Find NWB structure patterns by species
SELECT 
    s.name as species,
    COUNT(DISTINCT l.id) as file_count,
    AVG(struct_count.count) as avg_structure_elements
FROM dandisets_asset a
JOIN dandisets_lindimetadata l ON a.id = l.asset_id
JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id
JOIN dandisets_dandiset d ON ad.dandiset_id = d.id
JOIN dandisets_assetssummaryspecies ass ON d.assets_summary_id = ass.assets_summary_id
JOIN dandisets_speciestype s ON ass.species_id = s.id,
LATERAL (SELECT COUNT(*) as count FROM jsonb_object_keys(structure_metadata->'refs')) as struct_count
GROUP BY s.name
ORDER BY file_count DESC
LIMIT 10;
```

## Error Handling and Data Quality

### 16. Check for processing errors

```sql
-- Find assets that should have LINDI metadata but don't
SELECT 
    a.dandi_asset_id,
    a.path,
    a.encoding_format
FROM dandisets_asset a
LEFT JOIN dandisets_lindimetadata l ON a.id = l.asset_id
WHERE a.encoding_format = 'application/x-nwb'
  AND l.id IS NULL
LIMIT 10;
```

### 17. Validate LINDI processing

```sql
-- Check LINDI processing versions and timestamps
SELECT 
    processing_version,
    COUNT(*) as file_count,
    MIN(created_at) as first_processed,
    MAX(created_at) as last_processed
FROM dandisets_lindimetadata
GROUP BY processing_version
ORDER BY processing_version;
```

## Example Workflow

Here's a typical workflow for exploring LINDI metadata:

1. **Start with overview**: Count files and dandisets with LINDI metadata
2. **Explore structure**: Look at common groups and datasets
3. **Filter by interest**: Find files with specific data types or structures
4. **Cross-reference**: Combine with other metadata (species, techniques, etc.)
5. **Analyze patterns**: Look for trends across dandisets or file types

This integration allows researchers to perform sophisticated queries combining the rich metadata from DANDI with the detailed structural information from LINDI, enabling powerful data discovery and analysis workflows.
