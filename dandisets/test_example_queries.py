"""
Tests for all example queries from the SQL query webpage.

This test suite validates that all example queries provided in the web interface:
1. Pass SQL validation
2. Execute without errors
3. Return expected data structure
4. Are secure and safe to run
"""

import json
from django.test import TestCase
from django.db import connection
from unittest.mock import patch

from .sql_api import execute_sql_query, SQLSecurityValidator
from .views.query_views import get_example_queries


class ExampleQueriesTestCase(TestCase):
    """Test case for all example queries from the SQL interface."""
    
    def setUp(self):
        """Set up test data."""
        self.example_queries = get_example_queries()
        self.maxDiff = None  # Show full diff on assertion errors
    
    def test_all_example_queries_count(self):
        """Test that we have the expected number of example queries."""
        self.assertEqual(len(self.example_queries), 5, 
                        "Expected 5 example queries")
    
    def test_all_example_queries_structure(self):
        """Test that all example queries have the required structure."""
        required_fields = ['name', 'description', 'sql']
        
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query.get('name', 'Unknown')):
                for field in required_fields:
                    self.assertIn(field, query, 
                                f"Query {i} missing required field: {field}")
                    self.assertIsInstance(query[field], str,
                                        f"Query {i} field {field} should be string")
                    self.assertTrue(query[field].strip(),
                                  f"Query {i} field {field} should not be empty")
    
    def test_all_example_queries_validation(self):
        """Test that all example queries pass SQL validation."""
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                try:
                    secured_sql = SQLSecurityValidator.validate_and_secure_sql(query['sql'])
                    self.assertIsInstance(secured_sql, str)
                    self.assertTrue(secured_sql.strip())
                except ValueError as e:
                    self.fail(f"Query '{query['name']}' failed validation: {str(e)}")
    
    def test_example_query_1_simple_dataset_search(self):
        """Test the 'Simple dataset search' example query."""
        query = self.example_queries[0]
        self.assertEqual(query['name'], 'Simple dataset search')
        
        expected_sql = "SELECT base_id, name, description FROM dandisets_dandiset WHERE name ILIKE '%mouse%' ORDER BY name LIMIT 20"
        self.assertEqual(query['sql'], expected_sql)
        
        # Test execution (may return empty results if no data)
        result = execute_sql_query(query['sql'])
        self.assertTrue(result['success'], f"Query failed: {result.get('error', 'Unknown error')}")
        self.assertIn('results', result)
        self.assertIn('metadata', result)
        self.assertEqual(len(result['metadata']['columns']), 3)
        self.assertEqual(result['metadata']['columns'], ['base_id', 'name', 'description'])
    
    def test_example_query_2_count_datasets_by_species(self):
        """Test the 'Count datasets by species' example query."""
        query = self.example_queries[1]
        self.assertEqual(query['name'], 'Count datasets by species')
        
        # Test execution
        result = execute_sql_query(query['sql'])
        self.assertTrue(result['success'], f"Query failed: {result.get('error', 'Unknown error')}")
        self.assertIn('results', result)
        self.assertIn('metadata', result)
        
        # Check expected columns
        expected_columns = ['name', 'dataset_count']
        self.assertEqual(result['metadata']['columns'], expected_columns)
        
        # Results should be ordered by dataset_count DESC
        results = result['results']
        if len(results) > 1:
            for i in range(len(results) - 1):
                current_count = results[i]['dataset_count']
                next_count = results[i + 1]['dataset_count']
                self.assertGreaterEqual(current_count, next_count,
                                      "Results should be ordered by dataset_count DESC")
    
    def test_example_query_3_find_datasets_with_many_files(self):
        """Test the 'Find datasets with many files' example query."""
        query = self.example_queries[2]
        self.assertEqual(query['name'], 'Find datasets with many files')
        
        # Test execution
        result = execute_sql_query(query['sql'])
        self.assertTrue(result['success'], f"Query failed: {result.get('error', 'Unknown error')}")
        self.assertIn('results', result)
        self.assertIn('metadata', result)
        
        # Check expected columns
        expected_columns = ['base_id', 'name', 'file_count']
        self.assertEqual(result['metadata']['columns'], expected_columns)
        
        # Results should be ordered by file_count DESC
        results = result['results']
        if len(results) > 1:
            for i in range(len(results) - 1):
                current_count = results[i]['file_count']
                next_count = results[i + 1]['file_count']
                self.assertGreaterEqual(current_count, next_count,
                                      "Results should be ordered by file_count DESC")
        
        # Should be limited to 20 results
        self.assertLessEqual(len(results), 20)
    
    def test_example_query_4_dataset_summary_statistics(self):
        """Test the 'Dataset summary statistics' example query."""
        query = self.example_queries[3]
        self.assertEqual(query['name'], 'Dataset summary statistics')
        
        # Test execution
        result = execute_sql_query(query['sql'])
        self.assertTrue(result['success'], f"Query failed: {result.get('error', 'Unknown error')}")
        self.assertIn('results', result)
        self.assertIn('metadata', result)
        
        # Check expected columns
        expected_columns = ['base_id', 'name', 'date_created', 'date_published', 'total_files']
        self.assertEqual(result['metadata']['columns'], expected_columns)
        
        # Should be limited to 20 results
        results = result['results']
        self.assertLessEqual(len(results), 20)
        
        # Results should be ordered by date_published DESC NULLS LAST
        # We can't easily test the NULLS LAST part, but can check that non-null dates are descending
        non_null_dates = [r['date_published'] for r in results if r['date_published'] is not None]
        if len(non_null_dates) > 1:
            for i in range(len(non_null_dates) - 1):
                current_date = non_null_dates[i]
                next_date = non_null_dates[i + 1]
                self.assertGreaterEqual(current_date, next_date,
                                      "Non-null dates should be ordered DESC")
    
    def test_example_query_5_recent_datasets_with_contributors(self):
        """Test the 'Recent datasets with contributors' example query."""
        query = self.example_queries[4]
        self.assertEqual(query['name'], 'Recent datasets with contributors')
        
        # Test execution
        result = execute_sql_query(query['sql'])
        self.assertTrue(result['success'], f"Query failed: {result.get('error', 'Unknown error')}")
        self.assertIn('results', result)
        self.assertIn('metadata', result)
        
        # Check expected columns
        expected_columns = ['dataset_name', 'date_published', 'contributor_name', 'email']
        self.assertEqual(result['metadata']['columns'], expected_columns)
        
        # Should be limited to 20 results
        results = result['results']
        self.assertLessEqual(len(results), 20)
        
        # Results should be ordered by date_published DESC
        if len(results) > 1:
            for i in range(len(results) - 1):
                current_date = results[i]['date_published']
                next_date = results[i + 1]['date_published']
                # Both should not be None since we filter WHERE date_published IS NOT NULL
                self.assertIsNotNone(current_date)
                self.assertIsNotNone(next_date)
                self.assertGreaterEqual(current_date, next_date,
                                      "Results should be ordered by date_published DESC")
    
    def test_all_queries_have_limit(self):
        """Test that all example queries have appropriate LIMIT clauses."""
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                sql_upper = query['sql'].upper()
                self.assertIn('LIMIT', sql_upper, 
                            f"Query '{query['name']}' should have a LIMIT clause")
                
                # Extract limit value
                import re
                limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
                self.assertIsNotNone(limit_match, 
                                   f"Query '{query['name']}' should have a numeric LIMIT")
                
                if limit_match:  # Additional safety check for type checker
                    limit_value = int(limit_match.group(1))
                    self.assertLessEqual(limit_value, 1000,
                                       f"Query '{query['name']}' LIMIT should not exceed 1000")
    
    def test_all_queries_use_allowed_tables(self):
        """Test that all example queries only reference allowed tables."""
        allowed_prefixes = SQLSecurityValidator.ALLOWED_TABLE_PREFIXES
        
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                # Extract table names from SQL using regex
                import re
                table_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                tables = re.findall(table_pattern, query['sql'], re.IGNORECASE)
                
                for table in tables:
                    table_lower = table.lower()
                    is_allowed = any(table_lower.startswith(prefix) 
                                   for prefix in allowed_prefixes)
                    self.assertTrue(is_allowed, 
                                  f"Query '{query['name']}' references disallowed table: {table}")
    
    def test_all_queries_are_readonly(self):
        """Test that all example queries are read-only (SELECT only)."""
        forbidden_keywords = SQLSecurityValidator.FORBIDDEN_KEYWORDS
        
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                sql_upper = query['sql'].upper()
                
                # Should start with SELECT
                self.assertTrue(sql_upper.strip().startswith('SELECT'),
                              f"Query '{query['name']}' should start with SELECT")
                
                # Should not contain forbidden keywords
                for keyword in forbidden_keywords:
                    self.assertNotRegex(sql_upper, r'\b' + keyword + r'\b',
                                       f"Query '{query['name']}' contains forbidden keyword: {keyword}")
    
    @patch('django.db.connection')
    def test_queries_with_mocked_empty_database(self, mock_connection):
        """Test that queries handle empty database gracefully."""
        # Mock empty database responses
        mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = []
        
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                # Should not raise exceptions even with empty database
                try:
                    result = execute_sql_query(query['sql'])
                    # Should succeed even with no data
                    self.assertTrue(result['success'])
                    self.assertEqual(result['results'], [])
                except Exception as e:
                    self.fail(f"Query '{query['name']}' raised exception with empty database: {str(e)}")
    
    def test_query_performance_considerations(self):
        """Test that queries have reasonable performance characteristics."""
        performance_issues = []
        
        for i, query in enumerate(self.example_queries):
            sql_upper = query['sql'].upper()
            query_name = query['name']
            
            # Check for potentially expensive operations
            if 'SELECT *' in sql_upper:
                performance_issues.append(f"Query '{query_name}' uses SELECT * which may be inefficient")
            
            # Check for reasonable ORDER BY usage
            if 'ORDER BY' in sql_upper and 'LIMIT' not in sql_upper:
                performance_issues.append(f"Query '{query_name}' has ORDER BY without LIMIT")
            
            # Check for reasonable GROUP BY usage
            if 'GROUP BY' in sql_upper:
                # This is okay, but let's make sure it's not overly complex
                group_by_count = sql_upper.count('GROUP BY')
                if group_by_count > 1:
                    performance_issues.append(f"Query '{query_name}' has multiple GROUP BY clauses")
        
        # Report any performance issues as warnings (not failures)
        if performance_issues:
            print(f"\nPerformance considerations found:")
            for issue in performance_issues:
                print(f"  - {issue}")
    
    def test_query_descriptions_are_accurate(self):
        """Test that query descriptions accurately describe what the query does."""
        # This is more of a documentation test
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                name = query['name'].lower()
                description = query['description'].lower()
                sql = query['sql'].lower()
                
                # Check that description keywords match SQL content
                if 'count' in name or 'count' in description:
                    self.assertIn('count', sql, 
                                f"Query '{query['name']}' description mentions count but SQL doesn't")
                
                if 'recent' in name or 'recent' in description:
                    self.assertTrue('order by' in sql and 'desc' in sql,
                                  f"Query '{query['name']}' should order by date DESC for recent results")
                
                if 'most' in description or 'many' in description:
                    self.assertTrue('order by' in sql and 'desc' in sql,
                                  f"Query '{query['name']}' should order DESC for 'most/many' results")


class ExampleQueriesIntegrationTestCase(TestCase):
    """Integration tests that execute queries against the actual database."""
    
    def setUp(self):
        """Set up test data."""
        self.example_queries = get_example_queries()
    
    def test_all_queries_execute_successfully(self):
        """Integration test: execute all queries against the real database."""
        for i, query in enumerate(self.example_queries):
            with self.subTest(query_index=i, query_name=query['name']):
                result = execute_sql_query(query['sql'])
                
                # Query should execute successfully
                self.assertTrue(result['success'], 
                              f"Query '{query['name']}' failed: {result.get('error', 'Unknown error')}")
                
                # Result should have expected structure
                self.assertIn('results', result)
                self.assertIn('metadata', result)
                self.assertIsInstance(result['results'], list)
                self.assertIsInstance(result['metadata'], dict)
                
                # Metadata should have expected fields
                metadata = result['metadata']
                self.assertIn('row_count', metadata)
                self.assertIn('column_count', metadata)
                self.assertIn('columns', metadata)
                self.assertIn('sql_executed', metadata)
                
                # Row count should match actual results
                self.assertEqual(metadata['row_count'], len(result['results']))
                
                # Column count should match column list
                self.assertEqual(metadata['column_count'], len(metadata['columns']))
                
                # If there are results, check structure
                if result['results']:
                    first_row = result['results'][0]
                    self.assertIsInstance(first_row, dict)
                    
                    # All columns should be present in each row
                    for column in metadata['columns']:
                        self.assertIn(column, first_row)
    
    def test_query_result_consistency(self):
        """Test that running the same query multiple times gives consistent results."""
        # Test first query only to avoid excessive database hits
        if self.example_queries:
            query = self.example_queries[0]
            
            # Execute twice
            result1 = execute_sql_query(query['sql'])
            result2 = execute_sql_query(query['sql'])
            
            # Both should succeed
            self.assertTrue(result1['success'])
            self.assertTrue(result2['success'])
            
            # Results should be identical (assuming no data changes)
            self.assertEqual(result1['metadata']['row_count'], result2['metadata']['row_count'])
            self.assertEqual(result1['metadata']['columns'], result2['metadata']['columns'])
            self.assertEqual(len(result1['results']), len(result2['results']))
