# Django MCP Server for DANDI SQL Queries

This document describes the Django-based MCP (Model Context Protocol) server that provides SQL query capabilities for the DANDI Archive database.

## Overview

Instead of running a separate Node.js MCP server, we've implemented the MCP protocol directly within the Django application. This provides:

- **Simplified deployment**: No need for separate Node.js service
- **Direct database access**: Uses existing Django ORM and database connections
- **Integrated security**: Leverages existing SQL security validation
- **Better performance**: Eliminates HTTP calls between services

## Features

The MCP server focuses exclusively on SQL functionality and provides:

### Tools
- `execute_sql` - Execute SQL queries with security validation
- `validate_sql` - Validate SQL queries without execution
- `get_schema` - Get database schema information for specific tables
- `get_full_schema` - Get complete database schema for all allowed tables

### Resources
- `dandi://docs/sql-queries` - SQL query guide and best practices
- `dandi://docs/schema` - Database schema reference documentation
- `dandi://examples/sql` - Collection of example SQL queries

## MCP Server Endpoint

The MCP server is available at:
```
POST /mcp/
```

## Security Features

- Only SELECT statements allowed
- Access restricted to DANDI-specific tables only
- Query complexity limits enforced
- Automatic result limits (max 1000 rows)
- SQL injection protection through validation
- Read-only database transactions

## Configuration for MCP Clients

### HTTP Transport Configuration

To connect to this MCP server using HTTP transport, configure your MCP client with:

```json
{
  "mcpServers": {
    "dandi-sql-server": {
      "command": "npx",
      "args": [
        "@modelcontextprotocol/server-fetch",
        "http://your-domain.com/mcp/"
      ]
    }
  }
}
```

For local development:
```json
{
  "mcpServers": {
    "dandi-sql-server": {
      "command": "npx",
      "args": [
        "@modelcontextprotocol/server-fetch",
        "http://localhost:8000/mcp/"
      ]
    }
  }
}
```

### Environment Variables

The server uses the same Django settings as the main application. Key environment variables:

- `DATABASE_URL` - PostgreSQL database connection
- `DEBUG` - Django debug mode
- `ALLOWED_HOSTS` - Allowed hostnames

## Example Usage

### Using the execute_sql tool

```json
{
  "method": "tools/call",
  "params": {
    "name": "execute_sql",
    "arguments": {
      "sql": "SELECT id, name, description FROM dandisets_dandiset WHERE name ILIKE '%mouse%' LIMIT 10"
    }
  }
}
```

### Using the validate_sql tool

```json
{
  "method": "tools/call", 
  "params": {
    "name": "validate_sql",
    "arguments": {
      "sql": "SELECT * FROM dandisets_dandiset"
    }
  }
}
```

### Getting schema information

```json
{
  "method": "tools/call",
  "params": {
    "name": "get_schema", 
    "arguments": {
      "table": "dandisets_dandiset"
    }
  }
}
```

### Accessing documentation resources

```json
{
  "method": "resources/read",
  "params": {
    "uri": "dandi://docs/sql-queries"
  }
}
```

## Available Tables

The server provides access to these DANDI-specific tables:

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
- `dandisets_disorder` - Disorder classifications

### Summary Tables
- `dandisets_assetssummary` - Pre-computed dataset summaries
- `dandisets_lindimetadata` - LINDI metadata cache

## Deployment

### Production Deployment

The MCP server is automatically available when the Django application is deployed. No additional services needed.

### Local Development

1. Start the Django development server:
```bash
python manage.py runserver
```

2. The MCP server will be available at `http://localhost:8000/mcp/`

### Testing the MCP Server

You can test the server directly with curl:

```bash
# List available tools
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/list",
    "params": {}
  }'

# Execute a SQL query
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "execute_sql", 
      "arguments": {
        "sql": "SELECT COUNT(*) as total_datasets FROM dandisets_dandiset"
      }
    }
  }'
```

## Migration from Node.js MCP Server

If you were previously using the Node.js MCP server:

1. Remove the Node.js MCP server configuration from your MCP client
2. Add the HTTP transport configuration pointing to the Django endpoint
3. Install the MCP fetch server if not already available:
   ```bash
   npm install -g @modelcontextprotocol/server-fetch
   ```

The tools and functionality are identical, so existing queries and workflows will work without changes.

## Advantages Over Node.js MCP Server

1. **Simplified Architecture**: One less service to deploy and maintain
2. **Better Performance**: Direct database access without HTTP overhead
3. **Shared Security**: Uses the same security validation as the main application
4. **Easier Debugging**: All logs and errors in one place
5. **Unified Configuration**: Same environment variables and settings
6. **Better Error Handling**: Integrated with Django's error handling and logging

## Troubleshooting

### Common Issues

1. **CORS Errors**: Ensure proper CORS configuration in Django settings if accessing from browser-based MCP clients

2. **Database Connection**: Verify DATABASE_URL is properly configured

3. **Authentication**: The MCP endpoint currently doesn't require authentication, but this can be added if needed

### Logging

MCP server errors are logged using Django's logging system. Enable debug logging:

```python
# In settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'dandisets.views.mcp_views': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## Future Enhancements

Potential improvements for the Django MCP server:

1. **Authentication**: Add API key or OAuth authentication
2. **Rate Limiting**: Implement request rate limiting
3. **Query Caching**: Cache frequently-used query results
4. **Async Support**: Use Django async views for better performance
5. **Websocket Transport**: Add websocket support for real-time queries
6. **Query History**: Track and log executed queries for auditing
