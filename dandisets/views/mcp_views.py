"""
MCP (Model Context Protocol) server implementation for DANDI SQL queries.

This Django view implements an HTTP-based MCP server that provides tools for:
- SQL query execution with security validation
- SQL query validation
- Database schema discovery

Focus is purely on SQL functionality, removing basic search capabilities.
"""

import json
import logging
from typing import Dict, Any, List
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views import View
from django.utils.decorators import method_decorator
from django.conf import settings

from ..sql_api import execute_sql_query, SQLSecurityValidator

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP-specific error."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@method_decorator(csrf_exempt, name='dispatch')
class MCPServerView(View):
    """
    MCP HTTP server implementation for DANDI SQL queries.
    
    Implements the MCP protocol endpoints:
    - POST /mcp/tools/list - List available tools
    - POST /mcp/tools/call - Execute a tool
    - POST /mcp/resources/list - List available resources  
    - POST /mcp/resources/read - Read a resource
    """
    
    def get_server_info(self) -> Dict[str, Any]:
        """Get MCP server information."""
        return {
            "name": "dandi-sql-server",
            "version": "1.0.0",
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            }
        }
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools."""
        return [
            {
                "name": "execute_sql",
                "description": "Execute advanced SQL queries against the DANDI database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query to execute (SELECT statements only, max 10,000 chars)"
                        }
                    },
                    "required": ["sql"]
                }
            },
            {
                "name": "validate_sql",
                "description": "Validate SQL query without executing it",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query to validate"
                        }
                    },
                    "required": ["sql"]
                }
            },
            {
                "name": "get_schema",
                "description": "Get database schema information",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": "Specific table name to get details for (optional)"
                        }
                    }
                }
            },
            {
                "name": "get_full_schema",
                "description": "Get complete database schema with all tables and their columns",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    def get_available_resources(self) -> List[Dict[str, Any]]:
        """Get list of available MCP resources."""
        return [
            {
                "uri": "dandi://docs/sql-queries",
                "name": "SQL Query Guide",
                "mimeType": "text/markdown",
                "description": "Guide to writing advanced SQL queries with examples"
            },
            {
                "uri": "dandi://docs/schema",
                "name": "Database Schema Reference",
                "mimeType": "text/markdown",
                "description": "Complete reference of available tables and fields"
            },
            {
                "uri": "dandi://examples/sql",
                "name": "SQL Query Examples",
                "mimeType": "application/json",
                "description": "Collection of example SQL queries for common use cases"
            }
        ]
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP tool calls."""
        if tool_name == "execute_sql":
            return self._handle_execute_sql(arguments)
        elif tool_name == "validate_sql":
            return self._handle_validate_sql(arguments)
        elif tool_name == "get_schema":
            return self._handle_get_schema(arguments)
        elif tool_name == "get_full_schema":
            return self._handle_get_full_schema(arguments)
        else:
            raise MCPError("MethodNotFound", f"Unknown tool: {tool_name}")
    
    def _handle_execute_sql(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SQL execution."""
        sql = arguments.get('sql')
        if not sql:
            raise MCPError("InvalidParams", "SQL query is required")
        
        result = execute_sql_query(sql)
        
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, indent=2)
            }]
        }
    
    def _handle_validate_sql(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SQL validation."""
        sql = arguments.get('sql')
        if not sql:
            raise MCPError("InvalidParams", "SQL query is required")
        
        try:
            safe_sql = SQLSecurityValidator.validate_and_secure_sql(sql)
            result = {
                "valid": True,
                "message": "SQL query is valid and safe",
                "secured_sql": safe_sql
            }
        except ValueError as e:
            result = {
                "valid": False,
                "error": str(e)
            }
        
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, indent=2)
            }]
        }
    
    def _handle_get_schema(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle schema requests."""
        from django.db import connection
        
        table_name = arguments.get('table')
        
        try:
            with connection.cursor() as cursor:
                if table_name:
                    # Get columns for specific table
                    if not SQLSecurityValidator._is_table_allowed(table_name):
                        result = {
                            "error": f"Access to table '{table_name}' is not allowed"
                        }
                    else:
                        cursor.execute("""
                            SELECT column_name, data_type, is_nullable, column_default
                            FROM information_schema.columns 
                            WHERE table_name = %s 
                            ORDER BY ordinal_position
                        """, [table_name])
                        
                        columns = []
                        for row in cursor.fetchall():
                            columns.append({
                                'name': row[0],
                                'type': row[1],
                                'nullable': row[2] == 'YES',
                                'default': row[3]
                            })
                        
                        result = {
                            'table': table_name,
                            'columns': columns
                        }
                else:
                    # Get list of allowed tables
                    allowed_tables = []
                    for prefix in SQLSecurityValidator.ALLOWED_TABLE_PREFIXES:
                        cursor.execute("""
                            SELECT table_name 
                            FROM information_schema.tables 
                            WHERE table_name LIKE %s
                            AND table_schema = 'public'
                        """, [f"{prefix}%"])
                        
                        for row in cursor.fetchall():
                            allowed_tables.append(row[0])
                    
                    result = {
                        'allowed_tables': sorted(allowed_tables)
                    }
        except Exception as e:
            result = {
                'error': f'Schema error: {str(e)}'
            }
        
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, indent=2)
            }]
        }
    
    def _handle_get_full_schema(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle full schema requests."""
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                # First, get the list of all allowed tables
                allowed_tables = []
                for prefix in SQLSecurityValidator.ALLOWED_TABLE_PREFIXES:
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_name LIKE %s
                        AND table_schema = 'public'
                    """, [f"{prefix}%"])
                    
                    for row in cursor.fetchall():
                        allowed_tables.append(row[0])
                
                full_schema = {}
                
                # Get schema for each table
                for table_name in allowed_tables:
                    try:
                        cursor.execute("""
                            SELECT column_name, data_type, is_nullable, column_default
                            FROM information_schema.columns 
                            WHERE table_name = %s 
                            ORDER BY ordinal_position
                        """, [table_name])
                        
                        columns = []
                        for row in cursor.fetchall():
                            columns.append({
                                'name': row[0],
                                'type': row[1],
                                'nullable': row[2] == 'YES',
                                'default': row[3]
                            })
                        
                        full_schema[table_name] = {
                            'table': table_name,
                            'columns': columns
                        }
                    except Exception as table_error:
                        logger.warning(f"Failed to get schema for table {table_name}: {table_error}")
                        full_schema[table_name] = {'error': f'Failed to fetch schema for {table_name}'}
                
                result = {
                    'success': True,
                    'schema': full_schema,
                    'table_count': len(full_schema),
                    'message': f'Retrieved schema for {len(full_schema)} tables'
                }
                
        except Exception as e:
            result = {
                'success': False,
                'error': f'Full schema query failed: {str(e)}'
            }
        
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, indent=2)
            }]
        }
    
    def handle_resource_read(self, uri: str) -> Dict[str, Any]:
        """Handle MCP resource reading."""
        if uri == "dandi://docs/sql-queries":
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": self._get_sql_query_guide()
                }]
            }
        elif uri == "dandi://docs/schema":
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": self._get_schema_guide()
                }]
            }
        elif uri == "dandi://examples/sql":
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(self._get_sql_examples(), indent=2)
                }]
            }
        else:
            raise MCPError("InvalidRequest", f"Unknown resource: {uri}")
    
    def _get_sql_query_guide(self) -> str:
        """Get SQL query guide documentation."""
        return """# SQL Query Guide

The SQL query functionality provides maximum flexibility for complex data analysis.

## Security Features

- Only SELECT statements allowed
- Access limited to DANDI tables only
- Query complexity limits enforced
- Automatic result limits (max 1000 rows)
- SQL injection prevention

## Available Tables

### Core Tables:
- `dandisets_dandiset` - Dataset metadata
- `dandisets_asset` - Individual files/sessions
- `dandisets_participant` - Subject information
- `dandisets_assetdandiset` - Asset-dataset relationships
- `dandisets_assetwasattributedto` - Asset-participant relationships

### Reference Tables:
- `dandisets_species` - Species information
- `dandisets_anatomy` - Anatomical regions
- `dandisets_approach` - Experimental approaches
- `dandisets_measurementtechnique` - Measurement methods

## Query Tools

### execute_sql
Execute SQL queries directly:
```
{
  "sql": "SELECT id, name FROM dandisets_dandiset WHERE name ILIKE '%mouse%' LIMIT 10"
}
```

### validate_sql
Check query validity without execution:
```
{
  "sql": "SELECT * FROM dandisets_dandiset"
}
```

### get_schema
Get table structure information:
```
{
  "table": "dandisets_dandiset"
}
```

## Best Practices

1. Use LIMIT clauses to avoid large result sets
2. Filter early with WHERE clauses
3. Test complex queries with validate_sql first
4. Use JOINs efficiently
5. Leverage indexes on id, name, created_at fields
"""

    def _get_schema_guide(self) -> str:
        """Get schema guide documentation."""
        return """# Database Schema Reference

## Core Tables

### dandisets_dandiset
Main dataset table containing metadata about each DANDI dataset.

**Key Fields:**
- `id` (integer) - Unique dataset identifier
- `name` (text) - Dataset name
- `description` (text) - Dataset description
- `created_at` (timestamp) - Creation date
- `modified_at` (timestamp) - Last modification date

### dandisets_asset  
Individual files/sessions within datasets.

**Key Fields:**
- `id` (integer) - Unique asset identifier
- `dandi_asset_id` (text) - DANDI asset identifier
- `content_size` (bigint) - File size in bytes
- `encoding_format` (text) - File format/media type
- `variable_measured` (jsonb) - Array of measured variables
- `date_modified` (timestamp) - Asset modification date
- `date_published` (timestamp) - Asset publication date

**Note:** Asset paths are stored in the `dandisets_assetdandiset` relationship table since the same asset content can have different paths in different datasets.

### dandisets_participant
Subject/participant information.

**Key Fields:**
- `id` (integer) - Unique participant identifier
- `participant_id` (text) - Participant identifier within dataset
- `species_id` (integer) - Foreign key to species table
- `sex_id` (integer) - Foreign key to sex table
- `age` (text) - Subject age information

## Relationship Tables

### dandisets_assetdandiset
Links assets to datasets (many-to-many) and stores the asset path within each dataset.

**Fields:**
- `asset_id` (integer) - Foreign key to asset
- `dandiset_id` (integer) - Foreign key to dataset
- `path` (text) - Path to the asset within this specific dataset
- `date_added` (timestamp) - When asset was added to this dataset
- `is_primary` (boolean) - Whether this is the primary dataset for this asset

### dandisets_assetwasattributedto
Links assets to participants (many-to-many).

**Fields:**
- `asset_id` (integer) - Foreign key to asset  
- `participant_id` (integer) - Foreign key to participant

## Reference Tables

### dandisets_species
Species taxonomy information.

### dandisets_anatomy
Anatomical region ontology.

### dandisets_approach
Experimental approach classifications.

### dandisets_measurementtechnique
Measurement technique classifications.

Use `get_schema` tool with a table name to get detailed column information.
"""

    def _get_sql_examples(self) -> Dict[str, Any]:
        """Get SQL query examples."""
        return {
            "examples": [
                {
                    "name": "Simple dataset search",
                    "sql": "SELECT id, name, description FROM dandisets_dandiset WHERE name ILIKE '%mouse%' ORDER BY name LIMIT 20"
                },
                {
                    "name": "Count datasets by species",
                    "sql": "SELECT s.name, COUNT(DISTINCT d.base_id) as dataset_count FROM dandisets_dandiset d JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id JOIN dandisets_asset a ON ad.asset_id = a.id JOIN dandisets_assetwasattributedto awo ON a.id = awo.asset_id JOIN dandisets_participant p ON awo.participant_id = p.id JOIN dandisets_speciestype s ON p.species_id = s.id GROUP BY s.name ORDER BY dataset_count DESC"
                },
                {
                    "name": "Browse asset paths by dataset",
                    "sql": "SELECT d.base_id, d.name as dataset_name, ad.path, a.encoding_format, a.content_size FROM dandisets_dandiset d JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id JOIN dandisets_asset a ON ad.asset_id = a.id WHERE d.base_id = 'DANDI:000003' ORDER BY ad.path LIMIT 20"
                },
                {
                    "name": "Find datasets with multiple subjects having multiple sessions",
                    "sql": "SELECT d.id, d.name, qualified_subjects.subject_count FROM dandisets_dandiset d JOIN (SELECT sessions_per_subject.dandiset_id, COUNT(DISTINCT sessions_per_subject.participant_id) as subject_count FROM (SELECT ad.dandiset_id, awo.participant_id, COUNT(*) as session_count FROM dandisets_asset a JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id JOIN dandisets_assetwasattributedto awo ON a.id = awo.asset_id WHERE UPPER(a.variable_measured::text) LIKE UPPER('%ElectricalSeries%') GROUP BY ad.dandiset_id, awo.participant_id HAVING COUNT(*) >= 3) sessions_per_subject GROUP BY sessions_per_subject.dandiset_id HAVING COUNT(DISTINCT sessions_per_subject.participant_id) >= 3) qualified_subjects ON d.id = qualified_subjects.dandiset_id ORDER BY qualified_subjects.subject_count DESC"
                },
                {
                    "name": "Analyze variable measurements",
                    "sql": "SELECT a.variable_measured, COUNT(*) as asset_count, COUNT(DISTINCT ad.dandiset_id) as dataset_count FROM dandisets_asset a JOIN dandisets_assetdandiset ad ON a.id = ad.asset_id WHERE a.variable_measured IS NOT NULL GROUP BY a.variable_measured ORDER BY asset_count DESC LIMIT 20"
                }
            ]
        }
    
    def post(self, request: HttpRequest) -> JsonResponse:
        """Handle MCP HTTP requests."""
        try:
            # Parse JSON body
            try:
                body = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError as e:
                return JsonResponse({
                    "error": {
                        "code": "ParseError", 
                        "message": f"Invalid JSON: {str(e)}"
                    }
                }, status=400)
            
            # Get method from request
            method = body.get('method')
            params = body.get('params', {})
            
            # Handle different MCP methods
            if method == "initialize":
                return JsonResponse({
                    "result": self.get_server_info()
                })
            
            elif method == "tools/list":
                return JsonResponse({
                    "result": {
                        "tools": self.get_available_tools()
                    }
                })
            
            elif method == "tools/call":
                tool_name = params.get('name')
                arguments = params.get('arguments', {})
                
                try:
                    result = self.handle_tool_call(tool_name, arguments)
                    return JsonResponse({"result": result})
                except MCPError as e:
                    return JsonResponse({
                        "error": {
                            "code": e.code,
                            "message": e.message
                        }
                    }, status=400)
            
            elif method == "resources/list":
                return JsonResponse({
                    "result": {
                        "resources": self.get_available_resources()
                    }
                })
            
            elif method == "resources/read":
                uri = params.get('uri')
                try:
                    result = self.handle_resource_read(uri)
                    return JsonResponse({"result": result})
                except MCPError as e:
                    return JsonResponse({
                        "error": {
                            "code": e.code,
                            "message": e.message
                        }
                    }, status=400)
            
            else:
                return JsonResponse({
                    "error": {
                        "code": "MethodNotFound",
                        "message": f"Unknown method: {method}"
                    }
                }, status=404)
        
        except Exception as e:
            logger.error(f"MCP server error: {str(e)}")
            return JsonResponse({
                "error": {
                    "code": "InternalError",
                    "message": f"Internal server error: {str(e)}"
                }
            }, status=500)


# Function-based view for easier URL routing
@csrf_exempt
@require_http_methods(["POST"])
def mcp_server(request):
    """MCP server endpoint."""
    view = MCPServerView()
    return view.post(request)
