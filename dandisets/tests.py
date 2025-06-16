"""
DANDI SQL Testing Suite

This test suite uses published dandisets for repeatable testing since published 
versions are immutable and won't change over time.

Test Strategy:
- Use specific published dandiset versions (e.g., DANDI:000003/0.230629.1955)
- Test both basic search and advanced SQL functionality
- Validate security features and input sanitization
- Test error handling and edge cases
"""

from django.test import TestCase, Client, TransactionTestCase
from django.urls import reverse
from django.db import connection
from django.conf import settings
import json
import re
import os

from .models import Dandiset, Asset, Participant, SpeciesType, AssetDandiset


class PublishedDandisetTestCase(TestCase):
    """Base test case with published dandiset data for repeatable tests"""
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data using known published dandisets"""
        # Use real database - published dandisets that should exist
        cls.published_dandisets = [
            'DANDI:000003/0.230629.1955',  # Physiological Properties and Behavioral Correlates
            'DANDI:000004/0.210812.1142',  # A NWB-based dataset and processing pipeline
            'DANDI:000006/0.230629.1955',  # Mouse anterior lateral motor cortex (ALM)
        ]
        
    def setUp(self):
        """Set up for each test"""
        self.use_real_db = os.environ.get('USE_REAL_DB', 'false').lower() == 'true'
        
    def check_database_populated(self):
        """Check if database has any data"""
        return Dandiset.objects.exists()


class BasicSearchAPITests(PublishedDandisetTestCase):
    """Test the basic search API functionality"""
    
    def setUp(self):
        self.client = Client()
    
    def test_search_datasets_by_name(self):
        """Test dataset search by name"""
        response = self.client.get('/api/search/', {'name': 'mouse'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertIn('pagination', data)
        
        # Should find datasets with 'mouse' in the name
        total_count = data['pagination']['total_count']
        if total_count > 0:
            for result in data['results']:
                self.assertIn('name', result)
                self.assertTrue(
                    'mouse' in result['name'].lower(),
                    f"Expected 'mouse' in dataset name: {result['name']}"
                )
    
    def test_search_datasets_by_species(self):
        """Test dataset search by species"""
        response = self.client.get('/api/search/', {
            'species': ['Mus musculus', 'Mus musculus - House mouse']
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
    
    def test_search_datasets_pagination(self):
        """Test dataset search pagination"""
        # Test limit
        response = self.client.get('/api/search/', {'limit': 5})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data['results']), 5)
        
        # Test offset
        response = self.client.get('/api/search/', {'limit': 5, 'offset': 10})
        self.assertEqual(response.status_code, 200)
    
    def test_search_assets_by_variable_measured(self):
        """Test asset search by variable measured"""
        response = self.client.get('/api/assets/search/', {
            'variable_measured': ['ElectricalSeries']
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
    
    def test_search_assets_by_dandiset_id(self):
        """Test asset search by dandiset ID"""
        # First find a dandiset ID
        dandiset_response = self.client.get('/api/search/', {'limit': 1})
        if dandiset_response.status_code == 200:
            dandisets = dandiset_response.json()['results']
            if dandisets:
                dandiset_id = dandisets[0]['id']
                
                response = self.client.get('/api/assets/search/', {
                    'dandiset_id': dandiset_id,
                    'limit': 10
                })
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn('results', data)
    
    def test_invalid_search_parameters(self):
        """Test error handling for invalid search parameters"""
        # Test very large limit (might be allowed but limited internally)
        response = self.client.get('/api/search/', {'limit': 10000})
        self.assertIn(response.status_code, [200, 400])
        if response.status_code == 200:
            # If allowed, should be internally limited
            data = response.json()
            self.assertLessEqual(len(data['results']), 1000)
        
        # Test negative offset
        response = self.client.get('/api/search/', {'offset': -1})
        self.assertIn(response.status_code, [200, 400])


class SqlQueryAPITests(PublishedDandisetTestCase):
    """Test the SQL query API functionality"""
    
    def setUp(self):
        self.client = Client()
    
    def test_simple_sql_query(self):
        """Test a simple SQL query"""
        sql = "SELECT COUNT(*) as total FROM dandisets_dandiset WHERE is_latest = true"
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertIn('metadata', data)
        self.assertEqual(len(data['results']), 1)
        self.assertIn('total', data['results'][0])
    
    def test_complex_join_query(self):
        """Test a complex query with joins"""
        sql = """
        SELECT d.name, COUNT(a.id) as asset_count
        FROM dandisets_dandiset d
        LEFT JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
        LEFT JOIN dandisets_asset a ON ad.asset_id = a.id
        WHERE d.is_latest = true
        GROUP BY d.id, d.name
        ORDER BY asset_count DESC
        LIMIT 5
        """
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertLessEqual(len(data['results']), 5)
    
    def test_published_dandiset_query(self):
        """Test query for specific published dandisets"""
        sql = """
        SELECT base_id, name, version, date_published
        FROM dandisets_dandiset 
        WHERE base_id IN ('DANDI:000003', 'DANDI:000004', 'DANDI:000006')
        AND version IS NOT NULL
        ORDER BY base_id, version_order
        """
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        
        # Verify we get published versions
        for result in data['results']:
            self.assertIsNotNone(result['version'])
            self.assertIsNotNone(result['date_published'])
    
    def test_species_analysis_query(self):
        """Test species analysis query"""
        sql = """
        SELECT s.name as species, COUNT(DISTINCT d.id) as datasets
        FROM dandisets_speciestype s
        JOIN dandisets_participant p ON s.id = p.species_id
        JOIN dandisets_assetwasattributedto awo ON p.id = awo.participant_id
        JOIN dandisets_assetdandiset ad ON awo.asset_id = ad.asset_id
        JOIN dandisets_dandiset d ON ad.dandiset_id = d.id
        WHERE d.is_latest = true
        GROUP BY s.id, s.name
        ORDER BY datasets DESC
        LIMIT 10
        """
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
    
    def test_sql_validation_success(self):
        """Test SQL validation for valid queries"""
        sql = "SELECT id, name FROM dandisets_dandiset LIMIT 10"
        response = self.client.post(
            '/api/sql/validate/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['valid'])
        self.assertIn('message', data)
    
    def test_sql_security_validation(self):
        """Test SQL security validation"""
        # Test INSERT (should fail)
        sql = "INSERT INTO dandisets_dandiset (name) VALUES ('test')"
        response = self.client.post(
            '/api/sql/validate/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        
        # Test DELETE (should fail)
        sql = "DELETE FROM dandisets_dandiset WHERE id = 1"
        response = self.client.post(
            '/api/sql/validate/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        
        # Test UPDATE (should fail)
        sql = "UPDATE dandisets_dandiset SET name = 'hacked' WHERE id = 1"
        response = self.client.post(
            '/api/sql/validate/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        
        # Test DROP (should fail)
        sql = "DROP TABLE dandisets_dandiset"
        response = self.client.post(
            '/api/sql/validate/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
    
    def test_sql_injection_protection(self):
        """Test SQL injection protection"""
        malicious_queries = [
            "SELECT * FROM dandisets_dandiset; DROP TABLE dandisets_asset;",
            "SELECT * FROM dandisets_dandiset WHERE id = 1; DELETE FROM dandisets_dandiset;",
            "SELECT * FROM dandisets_dandiset UNION SELECT password FROM users",
            "SELECT * FROM information_schema.tables",
        ]
        
        for sql in malicious_queries:
            response = self.client.post(
                '/api/sql/validate/',
                {'sql': sql},
                content_type='application/json'
            )
            # Should either reject the query or sanitize it
            self.assertIn(response.status_code, [400, 200])
            if response.status_code == 200:
                # If validated, should be sanitized
                data = response.json()
                self.assertNotIn('DROP', data.get('secured_sql', '').upper())
                self.assertNotIn('DELETE', data.get('secured_sql', '').upper())
    
    def test_query_result_limits(self):
        """Test that query results are properly limited"""
        sql = "SELECT * FROM dandisets_dandiset"  # No LIMIT clause
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data['results']), 1000)  # Should be limited to 1000


class SchemaAPITests(PublishedDandisetTestCase):
    """Test the schema discovery API"""
    
    def setUp(self):
        self.client = Client()
    
    def test_get_all_tables(self):
        """Test getting all available tables"""
        response = self.client.get('/api/sql/schema/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('allowed_tables', data)
        
        # Check for key tables
        allowed_tables = data['allowed_tables']
        self.assertIn('dandisets_dandiset', allowed_tables)
        self.assertIn('dandisets_asset', allowed_tables)
        self.assertIn('dandisets_participant', allowed_tables)
    
    def test_get_specific_table_schema(self):
        """Test getting schema for a specific table"""
        response = self.client.get('/api/sql/schema/?table=dandisets_dandiset')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('table', data)
        self.assertIn('columns', data)
        self.assertEqual(data['table'], 'dandisets_dandiset')
        
        # Check for key columns
        column_names = [col['name'] for col in data['columns']]
        self.assertIn('id', column_names)
        self.assertIn('name', column_names)
        self.assertIn('dandi_id', column_names)
    
    def test_filter_options(self):
        """Test getting filter options"""
        response = self.client.get('/api/filter-options/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should contain filter options for common fields
        expected_keys = ['species', 'approaches', 'measurement_techniques', 'anatomies']
        for key in expected_keys:
            if key in data:
                self.assertIsInstance(data[key], list)


class ModelTests(PublishedDandisetTestCase):
    """Test model functionality and data integrity"""
    
    def test_dandiset_version_handling(self):
        """Test dandiset version management"""
        # Test base_id extraction
        dandiset = Dandiset.objects.create(
            dandi_id="DANDI:000999/0.230101.1234",
            identifier="DANDI:000999",
            name="Test Dataset",
            description="Test description",
            version="0.230101.1234",
            is_latest=True
        )
        
        self.assertEqual(dandiset.base_id, "DANDI:000999")
        self.assertFalse(dandiset.is_draft)
    
    def test_dandiset_draft_handling(self):
        """Test draft version handling"""
        dandiset = Dandiset.objects.create(
            dandi_id="DANDI:000999/draft",
            identifier="DANDI:000999",
            name="Test Dataset Draft",
            description="Test description",
            is_draft=True,
            is_latest=True
        )
        
        self.assertEqual(dandiset.base_id, "DANDI:000999")
        self.assertTrue(dandiset.is_draft)
        self.assertIsNone(dandiset.version)
    
    def test_asset_relationships(self):
        """Test asset-dandiset relationships"""
        dandiset = Dandiset.objects.create(
            dandi_id="DANDI:000999/0.230101.1234",
            identifier="DANDI:000999",
            name="Test Dataset",
            description="Test description"
        )
        
        asset = Asset.objects.create(
            dandi_asset_id="test_asset_id",
            identifier="test_asset",
            path="test/path.nwb",
            content_size=1024,
            encoding_format="application/x-nwb",
            digest={"sha256": "abc123"}
        )
        
        # Test many-to-many relationship through AssetDandiset
        asset_dandiset = AssetDandiset.objects.create(asset=asset, dandiset=dandiset)
        
        # Verify the relationship exists
        self.assertEqual(asset_dandiset.asset, asset)
        self.assertEqual(asset_dandiset.dandiset, dandiset)
        
        # Test that we can query through the relationship
        self.assertEqual(AssetDandiset.objects.filter(asset=asset, dandiset=dandiset).count(), 1)


class PerformanceTests(PublishedDandisetTestCase):
    """Test query performance with realistic data"""
    
    def test_large_dataset_query_performance(self):
        """Test performance of queries on large datasets"""
        import time
        
        # Complex query that should still perform reasonably
        sql = """
        SELECT 
            d.base_id,
            d.name,
            COUNT(DISTINCT a.id) as asset_count,
            COUNT(DISTINCT p.id) as participant_count,
            SUM(a.content_size) as total_size
        FROM dandisets_dandiset d
        LEFT JOIN dandisets_assetdandiset ad ON d.id = ad.dandiset_id
        LEFT JOIN dandisets_asset a ON ad.asset_id = a.id
        LEFT JOIN dandisets_assetwasattributedto awo ON a.id = awo.asset_id
        LEFT JOIN dandisets_participant p ON awo.participant_id = p.id
        WHERE d.is_latest = true
        GROUP BY d.id, d.base_id, d.name
        HAVING COUNT(DISTINCT a.id) > 0
        ORDER BY asset_count DESC
        LIMIT 20
        """
        
        start_time = time.time()
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        end_time = time.time()
        
        self.assertEqual(response.status_code, 200)
        
        # Query should complete within reasonable time (10 seconds)
        query_time = end_time - start_time
        self.assertLess(query_time, 10.0, 
                       f"Query took {query_time:.2f} seconds, which is too slow")
    
    def test_pagination_performance(self):
        """Test that pagination doesn't degrade performance significantly"""
        import time
        
        sql = "SELECT * FROM dandisets_dandiset WHERE is_latest = true ORDER BY id"
        
        # Test different limits
        for limit in [10, 50, 100, 500]:
            limited_sql = f"{sql} LIMIT {limit}"
            
            start_time = time.time()
            response = self.client.post(
                '/api/sql/execute/',
                {'sql': limited_sql},
                content_type='application/json'
            )
            end_time = time.time()
            
            self.assertEqual(response.status_code, 200)
            
            query_time = end_time - start_time
            self.assertLess(query_time, 5.0,
                           f"Query with LIMIT {limit} took {query_time:.2f} seconds")


class RegressionTests(PublishedDandisetTestCase):
    """Regression tests using known published dandisets"""
    
    def test_known_published_dandisets_exist(self):
        """Test that known published dandisets exist in the database"""
        # Skip if database is empty (test environment)
        if not self.check_database_populated():
            self.skipTest("Database is empty - skipping regression test")
            
        # These are well-known published dandisets that should exist
        known_base_ids = ['DANDI:000003', 'DANDI:000004', 'DANDI:000006']
        
        for base_id in known_base_ids:
            sql = f"SELECT COUNT(*) as count FROM dandisets_dandiset WHERE base_id = '{base_id}'"
            response = self.client.post(
                '/api/sql/execute/',
                {'sql': sql},
                content_type='application/json'
            )
            
            if response.status_code == 200:
                data = response.json()
                count = data['results'][0]['count']
                # In a real database with data, should have at least one version
                if self.use_real_db:
                    self.assertGreaterEqual(count, 1, 
                                          f"Expected at least 1 version of {base_id}")
    
    def test_electrical_series_data_consistency(self):
        """Test that ElectricalSeries data queries return consistent results"""
        # Skip if database is empty (test environment)
        if not self.check_database_populated():
            self.skipTest("Database is empty - skipping regression test")
            
        sql = """
        SELECT COUNT(*) as count
        FROM dandisets_asset 
        WHERE variable_measured::text ILIKE '%ElectricalSeries%'
        """
        
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        electrical_series_count = data['results'][0]['count']
        
        # In a real database with data, should have some ElectricalSeries data
        if self.use_real_db and electrical_series_count == 0:
            self.fail("Expected some assets with ElectricalSeries data in real database")
    
    def test_species_data_consistency(self):
        """Test that species data is consistent"""
        # Skip if database is empty (test environment)
        if not self.check_database_populated():
            self.skipTest("Database is empty - skipping regression test")
            
        sql = """
        SELECT name, COUNT(*) as count
        FROM dandisets_speciestype 
        WHERE name IS NOT NULL
        GROUP BY name
        ORDER BY count DESC
        LIMIT 10
        """
        
        response = self.client.post(
            '/api/sql/execute/',
            {'sql': sql},
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have common species like mouse and human
        species_names = [result['name'] for result in data['results']]
        has_mouse = any('mus musculus' in name.lower() for name in species_names)
        has_human = any('homo sapiens' in name.lower() for name in species_names)
        
        # At least one of these should be present in a real dataset
        if self.use_real_db and not (has_mouse or has_human):
            self.fail("Expected to find mouse or human species data in real database")


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    if not settings.configured:
        settings.configure()
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["dandisets.tests"])
