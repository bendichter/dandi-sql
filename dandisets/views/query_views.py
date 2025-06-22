"""
Custom SQL query interface views.

Provides a web interface for executing custom SQL queries with the same
validation and security as the MCP server.
"""

import json
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from ..sql_api import execute_sql_query, SQLSecurityValidator

logger = logging.getLogger(__name__)


def sql_query_interface(request):
    """
    Display the custom SQL query interface.
    
    GET: Show the query form
    POST: Execute the SQL query and show results
    """
    context = {
        'query': '',
        'results': None,
        'error': None,
        'execution_time': None,
        'example_queries': get_example_queries(),
        'allowed_tables': get_allowed_tables(),
    }
    
    if request.method == 'POST':
        sql_query = request.POST.get('sql', '').strip()
        page = int(request.POST.get('page', 1))
        
        if sql_query:
            try:
                # Execute the query using the same function as MCP
                result = execute_sql_query(sql_query)
                
                if result['success']:
                    # Pagination logic
                    per_page = 20
                    total_results = len(result['results'])
                    total_pages = max(1, (total_results + per_page - 1) // per_page)
                    
                    # Ensure page is within bounds
                    page = max(1, min(page, total_pages))
                    
                    # Calculate pagination slice
                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    paginated_results = result['results'][start_idx:end_idx]
                    
                    context.update({
                        'results': paginated_results,
                        'metadata': result['metadata'],
                        'query': sql_query,
                        'pagination': {
                            'current_page': page,
                            'total_pages': total_pages,
                            'total_results': total_results,
                            'per_page': per_page,
                            'has_previous': page > 1,
                            'has_next': page < total_pages,
                            'previous_page': page - 1 if page > 1 else None,
                            'next_page': page + 1 if page < total_pages else None,
                            'start_result': start_idx + 1,
                            'end_result': min(end_idx, total_results),
                        },
                        'all_results': result['results'],  # For export functionality
                        # JSON-encoded data for JavaScript
                        'results_json': json.dumps(paginated_results),
                        'columns_json': json.dumps(result['metadata']['columns']),
                        'all_results_json': json.dumps(result['results']),
                    })
                    
                    # Add success message
                    messages.success(request, f"Query executed successfully. {total_results} rows returned, showing page {page} of {total_pages}.")
                else:
                    context['error'] = result['error']
                    context['query'] = sql_query
                    messages.error(request, f"Query failed: {result['error']}")
                    
            except Exception as e:
                context['error'] = str(e)
                context['query'] = sql_query
                messages.error(request, f"Unexpected error: {str(e)}")
        else:
            context['error'] = "Please enter a SQL query."
            messages.error(request, "Please enter a SQL query.")
    
    return render(request, 'dandisets/sql_query.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def sql_query_ajax(request):
    """
    AJAX endpoint for executing SQL queries.
    
    Returns JSON response with results or error.
    """
    try:
        # Parse request body
        try:
            body = json.loads(request.body)
            sql = body.get('sql', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        if not sql:
            return JsonResponse({
                'success': False,
                'error': 'No SQL query provided'
            }, status=400)
        
        # Execute the query
        result = execute_sql_query(sql)
        
        status_code = 200 if result['success'] else 400
        return JsonResponse(result, status=status_code)
        
    except Exception as e:
        logger.error(f"SQL AJAX error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def sql_validate_ajax(request):
    """
    AJAX endpoint for validating SQL queries without executing them.
    
    Returns JSON response with validation result.
    """
    try:
        # Parse request body
        try:
            body = json.loads(request.body)
            sql = body.get('sql', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'valid': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        if not sql:
            return JsonResponse({
                'valid': False,
                'error': 'No SQL query provided'
            }, status=400)
        
        # Validate the query
        try:
            safe_sql = SQLSecurityValidator.validate_and_secure_sql(sql)
            return JsonResponse({
                'valid': True,
                'message': 'SQL query is valid and safe',
                'secured_sql': safe_sql
            })
        except ValueError as e:
            return JsonResponse({
                'valid': False,
                'error': str(e)
            }, status=400)
        
    except Exception as e:
        logger.error(f"SQL validation AJAX error: {str(e)}")
        return JsonResponse({
            'valid': False,
            'error': f'Validation error: {str(e)}'
        }, status=500)


def get_example_queries():
    """Get example SQL queries for the interface."""
    return [
        {
            'name': 'Simple dataset search',
            'description': 'Find datasets containing "mouse" in the name',
            'sql': "SELECT base_id, name, description FROM dandisets_dandiset WHERE name ILIKE '%mouse%' ORDER BY name LIMIT 20"
        },
        {
            'name': 'Count datasets by species',
            'description': 'Count how many datasets exist for each species',
            'sql': """SELECT s.name, COUNT(DISTINCT d.base_id) as dataset_count 
FROM dandisets_dandiset d 
JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id 
JOIN dandisets_asset a ON ad.asset_id = a.id 
JOIN dandisets_asset_participants ap ON a.id = ap.asset_id 
JOIN dandisets_participant p ON ap.participant_id = p.id 
JOIN dandisets_speciestype s ON p.species_id = s.id 
GROUP BY s.name 
ORDER BY dataset_count DESC
LIMIT 20"""
        },
        {
            'name': 'Find datasets with many files',
            'description': 'Find datasets with the most files',
            'sql': """SELECT d.base_id, d.name, COUNT(a.id) as file_count
FROM dandisets_dandiset d
JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
JOIN dandisets_asset a ON ad.asset_id = a.id
GROUP BY d.base_id, d.name
ORDER BY file_count DESC
LIMIT 20"""
        },
        {
            'name': 'Dataset summary statistics',
            'description': 'Get basic statistics for all datasets',
            'sql': """SELECT 
    d.base_id,
    d.name,
    d.date_created,
    d.date_published,
    COUNT(a.id) as total_files
FROM dandisets_dandiset d
LEFT JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
LEFT JOIN dandisets_asset a ON ad.asset_id = a.id
GROUP BY d.base_id, d.name, d.date_created, d.date_published
ORDER BY d.date_published DESC NULLS LAST
LIMIT 20"""
        },
        {
            'name': 'Recent datasets with contributors',
            'description': 'Find recently published datasets with contributor information',
            'sql': """SELECT 
    d.name as dataset_name,
    d.date_published,
    c.name as contributor_name,
    c.email
FROM dandisets_dandiset d
JOIN dandisets_dandisetcontributor dc ON d.id = dc.dandiset_id
JOIN dandisets_contributor c ON dc.contributor_id = c.id
WHERE d.date_published IS NOT NULL
ORDER BY d.date_published DESC
LIMIT 20"""
        }
    ]


def get_allowed_tables():
    """Get list of allowed tables for documentation with display names."""
    from django.db import connection
    
    allowed_tables = []
    try:
        with connection.cursor() as cursor:
            # Get all existing table names first
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            # Filter to only allowed tables that actually exist
            for table_name in SQLSecurityValidator.ALLOWED_TABLE_PREFIXES:
                if table_name in existing_tables:
                    # Remove "dandisets_" prefix for display
                    display_name = table_name.replace('dandisets_', '') if table_name.startswith('dandisets_') else table_name
                    allowed_tables.append({
                        'full_name': table_name,
                        'display_name': display_name
                    })
    except Exception as e:
        logger.error(f"Error getting allowed tables: {e}")
    
    return sorted(allowed_tables, key=lambda x: x['display_name'])


@csrf_exempt
@require_http_methods(["POST"])
def get_table_schema_ajax(request):
    """
    AJAX endpoint for getting table schema information.
    
    Returns JSON response with table schema details.
    """
    try:
        # Parse request body
        try:
            body = json.loads(request.body)
            table_name = body.get('table_name', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        if not table_name:
            return JsonResponse({
                'success': False,
                'error': 'No table name provided'
            }, status=400)
        
        # Validate table access
        if not SQLSecurityValidator._is_table_allowed(table_name):
            return JsonResponse({
                'success': False,
                'error': f'Access to table "{table_name}" is not allowed'
            }, status=403)
        
        # Get table schema
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                # Get columns for the table
                cursor.execute("""
                    SELECT 
                        column_name, 
                        data_type, 
                        is_nullable, 
                        column_default,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, [table_name])
                
                columns = []
                for row in cursor.fetchall():
                    column_info = {
                        'name': row[0],
                        'type': row[1],
                        'nullable': row[2] == 'YES',
                        'default': row[3],
                    }
                    
                    # Add length/precision info for relevant types
                    if row[4]:  # character_maximum_length
                        column_info['max_length'] = row[4]
                    if row[5]:  # numeric_precision
                        column_info['precision'] = row[5]
                    if row[6]:  # numeric_scale
                        column_info['scale'] = row[6]
                    
                    columns.append(column_info)
                
                # Get table comment if available
                cursor.execute("""
                    SELECT obj_description(oid) 
                    FROM pg_class 
                    WHERE relname = %s
                """, [table_name])
                
                table_comment = None
                comment_row = cursor.fetchone()
                if comment_row and comment_row[0]:
                    table_comment = comment_row[0]
                
                result = {
                    'success': True,
                    'table_name': table_name,
                    'display_name': table_name.replace('dandisets_', '') if table_name.startswith('dandisets_') else table_name,
                    'columns': columns,
                    'column_count': len(columns),
                    'description': table_comment
                }
                
                return JsonResponse(result)
                
        except Exception as db_error:
            logger.error(f"Database error getting schema for {table_name}: {db_error}")
            return JsonResponse({
                'success': False,
                'error': f'Database error: {str(db_error)}'
            }, status=500)
        
    except Exception as e:
        logger.error(f"Table schema AJAX error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)
