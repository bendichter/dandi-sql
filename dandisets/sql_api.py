"""
Direct SQL Query API with security validation.

Allows executing raw SQL queries with multiple layers of security protection.
"""

import re
import json
import logging
import sqlparse
from typing import Dict, Any
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection

logger = logging.getLogger(__name__)


class SQLSecurityValidator:
    """Validates SQL queries for security and read-only compliance."""
    
    # Allowed table prefixes - only DANDI tables can be queried
    ALLOWED_TABLE_PREFIXES = {
        'dandisets_dandiset',
        'dandisets_asset', 
        'dandisets_participant',
        'dandisets_activity',
        'dandisets_contributor',
        'dandisets_assetdandiset',
        'dandisets_assetwasattributedto',
        'dandisets_assetwasGeneratedby',
        'dandisets_dandisetcontributor',
        'dandisets_species',
        'dandisets_sex',
        'dandisets_strain',
        'dandisets_equipment',
        'dandisets_approach',
        'dandisets_measurementtechnique',
        'dandisets_anatomy',
        'dandisets_disorder',
        'dandisets_assetssummary',
        'dandisets_lindimetadata',
    }
    
    # Forbidden SQL keywords that indicate write operations
    FORBIDDEN_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
        'EXEC', 'EXECUTE', 'CALL', 'DECLARE', 'SET', 'USE', 'SHOW',
        'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT',
        'COPY', 'BULK', 'MERGE', 'REPLACE', 'IMPORT', 'EXPORT'
    }
    
    # Dangerous SQL patterns
    DANGEROUS_PATTERNS = [
        r';\s*\w+',  # Multiple statements
        r'\\x[0-9a-fA-F]+',  # Hex encoding
        r'\bchar\s*\(',  # Character functions
        r'\bascii\s*\(',  # ASCII functions
        r'\bbenchmark\s*\(',  # Benchmark function
        r'\bsleep\s*\(',  # Sleep function
        r'\bpg_sleep\s*\(',  # PostgreSQL sleep
        r'\bwaitfor\s+delay',  # SQL Server delay
        r'\bload_file\s*\(',  # Load file function
        r'\binto\s+outfile',  # File output
        r'\bunion\s+.*\s+select',  # Union injection attempts
    ]
    
    # Limits
    MAX_QUERY_LENGTH = 10000
    MAX_RESULTS = 1000
    
    @classmethod
    def validate_and_secure_sql(cls, sql: str) -> str:
        """
        Validate SQL query and return a secured version.
        
        Args:
            sql: Raw SQL query
            
        Returns:
            Validated and secured SQL query
            
        Raises:
            ValueError: If query is invalid or unsafe
        """
        # Basic validation
        if not sql or not sql.strip():
            raise ValueError("Empty SQL query")
        
        if len(sql) > cls.MAX_QUERY_LENGTH:
            raise ValueError(f"Query too long (max: {cls.MAX_QUERY_LENGTH} chars)")
        
        # Remove comments and normalize
        sql = cls._remove_comments(sql)
        sql = cls._normalize_whitespace(sql)
        
        # Must be SELECT only
        sql_upper = sql.upper().strip()
        if not sql_upper.startswith('SELECT'):
            raise ValueError("Only SELECT statements are allowed")
        
        # Check for forbidden keywords
        for keyword in cls.FORBIDDEN_KEYWORDS:
            if re.search(r'\b' + keyword + r'\b', sql_upper):
                raise ValueError(f"Forbidden keyword: {keyword}")
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                raise ValueError(f"Dangerous pattern detected")
        
        # Validate table references
        cls._validate_table_references(sql)
        
        # Add result limit if not present
        if 'LIMIT' not in sql_upper:
            sql += f' LIMIT {cls.MAX_RESULTS}'
        else:
            # Ensure limit doesn't exceed maximum
            limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
            if limit_match:
                limit_value = int(limit_match.group(1))
                if limit_value > cls.MAX_RESULTS:
                    sql = re.sub(r'LIMIT\s+\d+', f'LIMIT {cls.MAX_RESULTS}', sql, flags=re.IGNORECASE)
        
        return sql
    
    @classmethod
    def _remove_comments(cls, sql: str) -> str:
        """Remove SQL comments."""
        # Remove line comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        # Remove block comments
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        return sql.strip()
    
    @classmethod
    def _normalize_whitespace(cls, sql: str) -> str:
        """Normalize whitespace."""
        return re.sub(r'\s+', ' ', sql).strip()
    
    @classmethod
    def _validate_table_references(cls, sql: str) -> None:
        """Validate that all table references are allowed."""
        try:
            parsed = sqlparse.parse(sql)
            for statement in parsed:
                tokens = [token for token in statement.flatten() if not token.is_whitespace]
                
                # Look for table names after FROM and JOIN keywords
                table_keywords = {'FROM', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'OUTER'}
                
                i = 0
                while i < len(tokens):
                    token = tokens[i]
                    
                    if token.ttype is None and token.value.upper() in table_keywords:
                        # Look for the next identifier (table name)
                        j = i + 1
                        while j < len(tokens) and j < i + 5:  # Look ahead max 5 tokens
                            next_token = tokens[j]
                            if next_token.ttype in (sqlparse.tokens.Name, None) and next_token.value.isalnum():
                                table_name = next_token.value.lower().strip('"\'`')
                                
                                # Check if table is allowed
                                if not cls._is_table_allowed(table_name):
                                    raise ValueError(f"Access to table '{table_name}' is not allowed")
                                break
                            j += 1
                    i += 1
        except Exception as e:
            if "not allowed" in str(e):
                raise
            # If parsing fails, do a simple regex check as fallback
            table_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
            tables = re.findall(table_pattern, sql, re.IGNORECASE)
            for table in tables:
                if not cls._is_table_allowed(table.lower()):
                    raise ValueError(f"Access to table '{table}' is not allowed")
    
    @classmethod
    def _is_table_allowed(cls, table_name: str) -> bool:
        """Check if a table name is allowed."""
        table_name = table_name.split('.')[-1]  # Remove schema prefix
        return any(table_name.startswith(prefix) for prefix in cls.ALLOWED_TABLE_PREFIXES)


def execute_sql_query(sql: str) -> Dict[str, Any]:
    """
    Execute a validated SQL query and return results.
    
    Args:
        sql: The SQL query to execute
        
    Returns:
        Dictionary with results and metadata
    """
    try:
        # Validate and secure the SQL
        safe_sql = SQLSecurityValidator.validate_and_secure_sql(sql)
        
        # Execute the query
        with connection.cursor() as cursor:
            # Set read-only mode for this session
            cursor.execute("SET default_transaction_read_only = on;")
            
            # Execute the main query
            cursor.execute(safe_sql)
            
            # Fetch results
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                row_dict = {}
                for i, value in enumerate(row):
                    # Convert special types to JSON-serializable format
                    if hasattr(value, 'isoformat'):  # datetime objects
                        row_dict[columns[i]] = value.isoformat()
                    elif hasattr(value, 'hex'):  # UUID objects
                        row_dict[columns[i]] = str(value)
                    else:
                        row_dict[columns[i]] = value
                results.append(row_dict)
        
        return {
            'success': True,
            'results': results,
            'metadata': {
                'row_count': len(results),
                'column_count': len(columns),
                'columns': columns,
                'sql_executed': safe_sql
            }
        }
        
    except Exception as e:
        logger.error(f"SQL execution error: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'results': [],
            'metadata': {}
        }


@csrf_exempt
@require_http_methods(["POST"])
def sql_execute(request):
    """
    Execute a raw SQL query.
    
    POST /api/sql/execute/
    Body: {"sql": "SELECT * FROM dandisets_dandiset LIMIT 10"}
    """
    try:
        # Parse request body
        try:
            body = json.loads(request.body)
            sql = body.get('sql', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body',
                'results': []
            }, status=400)
        
        if not sql:
            return JsonResponse({
                'success': False,
                'error': 'No SQL query provided',
                'results': []
            }, status=400)
        
        # Execute the query
        result = execute_sql_query(sql)
        
        status_code = 200 if result['success'] else 400
        return JsonResponse(result, status=status_code)
        
    except Exception as e:
        logger.error(f"SQL API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'results': []
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def sql_validate(request):
    """
    Validate a SQL query without executing it.
    
    POST /api/sql/validate/
    Body: {"sql": "SELECT * FROM dandisets_dandiset"}
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
        logger.error(f"SQL validation error: {str(e)}")
        return JsonResponse({
            'valid': False,
            'error': f'Validation error: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def sql_schema(request):
    """
    Get database schema information for query building.
    
    GET /api/sql/schema/
    GET /api/sql/schema/?table=dandisets_dandiset
    """
    try:
        table_name = request.GET.get('table')
        
        with connection.cursor() as cursor:
            if table_name:
                # Get columns for specific table
                if not SQLSecurityValidator._is_table_allowed(table_name):
                    return JsonResponse({
                        'error': f"Access to table '{table_name}' is not allowed"
                    }, status=403)
                
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
                
                return JsonResponse({
                    'table': table_name,
                    'columns': columns
                })
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
                
                return JsonResponse({
                    'allowed_tables': sorted(allowed_tables)
                })
                
    except Exception as e:
        logger.error(f"Schema API error: {str(e)}")
        return JsonResponse({
            'error': f'Schema error: {str(e)}'
        }, status=500)
