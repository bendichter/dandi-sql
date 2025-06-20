"""
Tests for the Django MCP server implementation.

Tests cover:
- MCP protocol methods (initialize, tools/list, tools/call, resources/list, resources/read)
- SQL execution, validation, and schema functionality
- Error handling and security validation
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock


class MCPServerTestCase(TestCase):
    """Test cases for the MCP server endpoint."""
    
    def setUp(self):
        """Set up test client and common test data."""
        self.client = Client()
        self.mcp_url = reverse('dandisets:mcp_server')
    
    def _make_mcp_request(self, method, params=None):
        """Helper to make MCP requests."""
        data = {
            'method': method,
            'params': params or {}
        }
        return self.client.post(
            self.mcp_url,
            data=json.dumps(data),
            content_type='application/json'
        )
    
    def test_initialize_method(self):
        """Test MCP initialize method."""
        response = self._make_mcp_request('initialize')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('result', data)
        result = data['result']
        self.assertEqual(result['name'], 'dandi-sql-server')
        self.assertEqual(result['version'], '1.0.0')
        self.assertEqual(result['protocolVersion'], '2024-11-05')
        self.assertIn('capabilities', result)
        self.assertIn('tools', result['capabilities'])
        self.assertIn('resources', result['capabilities'])
    
    def test_tools_list_method(self):
        """Test MCP tools/list method."""
        response = self._make_mcp_request('tools/list')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('result', data)
        result = data['result']
        self.assertIn('tools', result)
        
        tools = result['tools']
        self.assertEqual(len(tools), 4)
        
        tool_names = [tool['name'] for tool in tools]
        expected_tools = ['execute_sql', 'validate_sql', 'get_schema', 'get_full_schema']
        for expected_tool in expected_tools:
            self.assertIn(expected_tool, tool_names)
        
        # Check that each tool has required fields
        for tool in tools:
            self.assertIn('name', tool)
            self.assertIn('description', tool)
            self.assertIn('inputSchema', tool)
    
    def test_resources_list_method(self):
        """Test MCP resources/list method."""
        response = self._make_mcp_request('resources/list')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('result', data)
        result = data['result']
        self.assertIn('resources', result)
        
        resources = result['resources']
        self.assertEqual(len(resources), 3)
        
        resource_uris = [resource['uri'] for resource in resources]
        expected_uris = [
            'dandi://docs/sql-queries',
            'dandi://docs/schema', 
            'dandi://examples/sql'
        ]
        for expected_uri in expected_uris:
            self.assertIn(expected_uri, resource_uris)
        
        # Check that each resource has required fields
        for resource in resources:
            self.assertIn('uri', resource)
            self.assertIn('name', resource)
            self.assertIn('mimeType', resource)
            self.assertIn('description', resource)
    
    def test_resources_read_method(self):
        """Test MCP resources/read method."""
        # Test SQL queries documentation
        response = self._make_mcp_request('resources/read', {
            'uri': 'dandi://docs/sql-queries'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('result', data)
        result = data['result']
        self.assertIn('contents', result)
        
        contents = result['contents']
        self.assertEqual(len(contents), 1)
        
        content = contents[0]
        self.assertEqual(content['uri'], 'dandi://docs/sql-queries')
        self.assertEqual(content['mimeType'], 'text/markdown')
        self.assertIn('text', content)
        self.assertIn('SQL Query Guide', content['text'])
        
        # Test schema documentation
        response = self._make_mcp_request('resources/read', {
            'uri': 'dandi://docs/schema'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        content = data['result']['contents'][0]
        self.assertEqual(content['mimeType'], 'text/markdown')
        self.assertIn('Database Schema Reference', content['text'])
        
        # Test SQL examples
        response = self._make_mcp_request('resources/read', {
            'uri': 'dandi://examples/sql'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        content = data['result']['contents'][0]
        self.assertEqual(content['mimeType'], 'application/json')
        
        # Parse the JSON content
        examples_data = json.loads(content['text'])
        self.assertIn('examples', examples_data)
        self.assertIsInstance(examples_data['examples'], list)
        self.assertGreater(len(examples_data['examples']), 0)
    
    def test_resources_read_invalid_uri(self):
        """Test resources/read with invalid URI."""
        response = self._make_mcp_request('resources/read', {
            'uri': 'dandi://invalid/resource'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        
        self.assertIn('error', data)
        error = data['error']
        self.assertEqual(error['code'], 'InvalidRequest')
        self.assertIn('Unknown resource', error['message'])
    
    @patch('dandisets.views.mcp_views.execute_sql_query')
    def test_tools_call_execute_sql(self, mock_execute_sql):
        """Test MCP tools/call with execute_sql tool."""
        # Mock successful SQL execution
        mock_execute_sql.return_value = {
            'success': True,
            'results': [{'id': 1, 'name': 'Test Dataset'}],
            'metadata': {
                'row_count': 1,
                'column_count': 2,
                'columns': ['id', 'name']
            }
        }
        
        response = self._make_mcp_request('tools/call', {
            'name': 'execute_sql',
            'arguments': {
                'sql': 'SELECT id, name FROM dandisets_dandiset LIMIT 1'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('result', data)
        result = data['result']
        self.assertIn('content', result)
        
        content = result['content']
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]['type'], 'text')
        
        # Parse the returned JSON text
        result_data = json.loads(content[0]['text'])
        self.assertTrue(result_data['success'])
        self.assertEqual(len(result_data['results']), 1)
        self.assertEqual(result_data['results'][0]['name'], 'Test Dataset')
        
        # Verify the SQL query was called
        mock_execute_sql.assert_called_once_with('SELECT id, name FROM dandisets_dandiset LIMIT 1')
    
    @patch('dandisets.views.mcp_views.SQLSecurityValidator.validate_and_secure_sql')
    def test_tools_call_validate_sql(self, mock_validate_sql):
        """Test MCP tools/call with validate_sql tool."""
        # Mock successful validation
        mock_validate_sql.return_value = 'SELECT * FROM dandisets_dandiset LIMIT 1000'
        
        response = self._make_mcp_request('tools/call', {
            'name': 'validate_sql',
            'arguments': {
                'sql': 'SELECT * FROM dandisets_dandiset'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        result = data['result']
        content = result['content'][0]
        result_data = json.loads(content['text'])
        
        self.assertTrue(result_data['valid'])
        self.assertIn('SQL query is valid and safe', result_data['message'])
        self.assertIn('secured_sql', result_data)
        
        mock_validate_sql.assert_called_once_with('SELECT * FROM dandisets_dandiset')
    
    @patch('dandisets.views.mcp_views.SQLSecurityValidator.validate_and_secure_sql')
    def test_tools_call_validate_sql_invalid(self, mock_validate_sql):
        """Test MCP tools/call with validate_sql tool for invalid SQL."""
        # Mock validation error
        mock_validate_sql.side_effect = ValueError('Only SELECT statements are allowed')
        
        response = self._make_mcp_request('tools/call', {
            'name': 'validate_sql',
            'arguments': {
                'sql': 'DROP TABLE dandisets_dandiset'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        result = data['result']
        content = result['content'][0]
        result_data = json.loads(content['text'])
        
        self.assertFalse(result_data['valid'])
        self.assertEqual(result_data['error'], 'Only SELECT statements are allowed')
    
    @patch('django.db.connection')
    def test_tools_call_get_schema(self, mock_connection):
        """Test MCP tools/call with get_schema tool."""
        # Mock database cursor
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('id', 'integer', 'NO', None),
            ('name', 'character varying', 'YES', None),
            ('description', 'text', 'YES', None)
        ]
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        response = self._make_mcp_request('tools/call', {
            'name': 'get_schema',
            'arguments': {
                'table': 'dandisets_dandiset'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        result = data['result']
        content = result['content'][0]
        result_data = json.loads(content['text'])
        
        self.assertEqual(result_data['table'], 'dandisets_dandiset')
        self.assertIn('columns', result_data)
        self.assertEqual(len(result_data['columns']), 3)
        
        # Check column structure
        columns = result_data['columns']
        self.assertEqual(columns[0]['name'], 'id')
        self.assertEqual(columns[0]['type'], 'integer')
        self.assertFalse(columns[0]['nullable'])
    
    @patch('django.db.connection')
    def test_tools_call_get_full_schema(self, mock_connection):
        """Test MCP tools/call with get_full_schema tool."""
        # Mock database cursor that returns no tables (simpler mock)
        mock_cursor = MagicMock()
        
        # Return empty results for all table queries - this simulates no tables found
        mock_cursor.fetchall.return_value = []
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        response = self._make_mcp_request('tools/call', {
            'name': 'get_full_schema',
            'arguments': {}
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        result = data['result']
        content = result['content'][0]
        result_data = json.loads(content['text'])
        
        # With no tables found, it should still succeed but with 0 tables
        self.assertTrue(result_data['success'])
        self.assertIn('schema', result_data)
        self.assertIn('table_count', result_data)
        self.assertEqual(result_data['table_count'], 0)
        self.assertIn('message', result_data)
    
    def test_tools_call_missing_arguments(self):
        """Test tools/call with missing required arguments."""
        response = self._make_mcp_request('tools/call', {
            'name': 'execute_sql',
            'arguments': {}
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        
        self.assertIn('error', data)
        error = data['error']
        self.assertEqual(error['code'], 'InvalidParams')
        self.assertIn('SQL query is required', error['message'])
    
    def test_tools_call_unknown_tool(self):
        """Test tools/call with unknown tool name."""
        response = self._make_mcp_request('tools/call', {
            'name': 'unknown_tool',
            'arguments': {}
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        
        self.assertIn('error', data)
        error = data['error']
        self.assertEqual(error['code'], 'MethodNotFound')
        self.assertIn('Unknown tool: unknown_tool', error['message'])
    
    def test_unknown_method(self):
        """Test unknown MCP method."""
        response = self._make_mcp_request('unknown/method')
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        
        self.assertIn('error', data)
        error = data['error']
        self.assertEqual(error['code'], 'MethodNotFound')
        self.assertIn('Unknown method: unknown/method', error['message'])
    
    def test_invalid_json(self):
        """Test request with invalid JSON."""
        response = self.client.post(
            self.mcp_url,
            data='invalid json',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        
        self.assertIn('error', data)
        error = data['error']
        self.assertEqual(error['code'], 'ParseError')
        self.assertIn('Invalid JSON', error['message'])
    
    def test_get_request_not_allowed(self):
        """Test that GET requests are not allowed."""
        response = self.client.get(self.mcp_url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed


class MCPToolsIntegrationTestCase(TestCase):
    """Integration tests for MCP tools with real database queries."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
        self.mcp_url = reverse('dandisets:mcp_server')
    
    def _make_mcp_request(self, method, params=None):
        """Helper to make MCP requests."""
        data = {
            'method': method,
            'params': params or {}
        }
        return self.client.post(
            self.mcp_url,
            data=json.dumps(data),
            content_type='application/json'
        )
    
    def test_validate_sql_integration(self):
        """Test SQL validation with real validator."""
        # Test valid SQL
        response = self._make_mcp_request('tools/call', {
            'name': 'validate_sql',
            'arguments': {
                'sql': 'SELECT COUNT(*) FROM dandisets_dandiset'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_data = json.loads(data['result']['content'][0]['text'])
        self.assertTrue(result_data['valid'])
        
        # Test invalid SQL (forbidden keyword)
        response = self._make_mcp_request('tools/call', {
            'name': 'validate_sql',
            'arguments': {
                'sql': 'DROP TABLE dandisets_dandiset'
            }
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_data = json.loads(data['result']['content'][0]['text'])
        self.assertFalse(result_data['valid'])
        # The validator returns "Only SELECT statements are allowed" for non-SELECT statements
        self.assertIn('Only SELECT statements are allowed', result_data['error'])
    
    def test_get_schema_integration(self):
        """Test schema retrieval with real database."""
        # Test getting all tables
        response = self._make_mcp_request('tools/call', {
            'name': 'get_schema',
            'arguments': {}
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_data = json.loads(data['result']['content'][0]['text'])
        
        self.assertIn('allowed_tables', result_data)
        self.assertIsInstance(result_data['allowed_tables'], list)
        
        # Verify that DANDI tables are included
        table_names = result_data['allowed_tables']
        dandi_tables = [table for table in table_names if table.startswith('dandisets_')]
        self.assertGreater(len(dandi_tables), 0)
