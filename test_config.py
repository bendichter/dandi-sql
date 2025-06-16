"""
DANDI SQL Test Configuration

This module contains configuration settings and constants for the test suite.
It defines expected data ranges, test datasets, and validation criteria.
"""

# Known published dandisets for testing (these should never change)
PUBLISHED_DANDISETS = {
    'DANDI:000003': {
        'name': 'Physiological Properties and Behavioral Correlates of Hippocampal Granule Cells and Mossy Cells',
        'published_version': '0.230629.1955',
        'expected_assets_min': 1,  # Minimum expected assets
        'expected_subjects_min': 1,  # Minimum expected subjects
        'species': ['Mus musculus'],
        'variable_measured': ['ElectricalSeries'],
    },
    'DANDI:000004': {
        'name': 'A NWB-based dataset and processing pipeline of human single-neuron activity during a declarative memory task',
        'published_version': '0.210812.1142',
        'expected_assets_min': 1,
        'expected_subjects_min': 1,
        'species': ['Homo sapiens'],
        'variable_measured': ['ElectricalSeries'],
    },
    'DANDI:000006': {
        'name': 'Mouse anterior lateral motor cortex (ALM) in delay response task',
        'published_version': '0.230629.1955',
        'expected_assets_min': 1,
        'expected_subjects_min': 1,
        'species': ['Mus musculus'],
        'variable_measured': ['ElectricalSeries'],
    },
}

# Performance test thresholds
PERFORMANCE_LIMITS = {
    'simple_query_max_time': 2.0,  # seconds
    'complex_query_max_time': 10.0,  # seconds
    'pagination_query_max_time': 5.0,  # seconds
    'schema_query_max_time': 1.0,  # seconds
}

# Expected data consistency thresholds
DATA_CONSISTENCY = {
    'min_total_dandisets': 10,  # Minimum expected dandisets in database
    'min_total_assets': 100,    # Minimum expected assets
    'min_electrical_series_assets': 10,  # Minimum assets with ElectricalSeries
    'expected_species': ['Mus musculus', 'Homo sapiens', 'Rattus norvegicus'],
    'max_query_result_size': 1000,  # Maximum results per query
}

# Security test patterns
MALICIOUS_SQL_PATTERNS = [
    "DROP TABLE",
    "DELETE FROM",
    "UPDATE SET",
    "INSERT INTO",
    "ALTER TABLE",
    "CREATE TABLE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
    "xp_cmdshell",
    "sp_executesql",
    "information_schema",
    "pg_class",
    "pg_tables",
    "mysql.user",
]

# Test API endpoints
API_ENDPOINTS = {
    'dataset_search': '/api/search/',
    'asset_search': '/api/assets/search/',
    'sql_execute': '/api/sql/execute/',
    'sql_validate': '/api/sql/validate/',
    'schema_list': '/api/sql/schema/',
    'filter_options': '/api/filter-options/',
}

# Expected schema tables (core tables that should always exist)
EXPECTED_TABLES = [
    'dandisets_dandiset',
    'dandisets_asset',
    'dandisets_participant',
    'dandisets_speciestype',
    'dandisets_assetdandiset',
    'dandisets_assetwasattributedto',
]

# Search test parameters
SEARCH_TEST_PARAMS = {
    'valid_limits': [1, 5, 10, 20, 50, 100],
    'invalid_limits': [0, -1, 1001, 10000],
    'valid_offsets': [0, 5, 10, 100],
    'invalid_offsets': [-1, -10],
    'test_species': ['Mus musculus', 'Homo sapiens', 'mouse', 'human'],
    'test_variable_measured': ['ElectricalSeries', 'TimeSeries', 'SpikeEventSeries'],
    'test_search_terms': ['mouse', 'human', 'brain', 'neuron', 'calcium'],
}

# Expected response fields for API endpoints
EXPECTED_RESPONSE_FIELDS = {
    'dataset_search': ['results', 'count', 'next', 'previous'],
    'asset_search': ['results', 'count', 'next', 'previous'],
    'sql_execute': ['results', 'metadata'],
    'sql_validate': ['valid', 'message'],
    'schema_list': ['allowed_tables'],
}

# Test timeout settings
TEST_TIMEOUTS = {
    'api_request_timeout': 30,  # seconds
    'sql_query_timeout': 60,    # seconds
    'performance_test_timeout': 120,  # seconds
}

# Regression test baseline values
# These values should be updated when the database is significantly changed
REGRESSION_BASELINES = {
    'total_dandisets_min': 10,
    'total_assets_min': 100,
    'electrical_series_count_min': 10,
    'species_count_min': 5,
    'mouse_datasets_min': 5,
    'human_datasets_min': 3,
}

# Test data validation rules
VALIDATION_RULES = {
    'dandiset_id_pattern': r'DANDI:\d{6}',
    'version_pattern': r'\d+\.\d+\.\d+',
    'asset_path_required': True,
    'content_size_min': 0,
    'encoding_format_required': True,
}
