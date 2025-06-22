from django.urls import path
from .views.sync_views import trigger_sync
from .views.mcp_views import mcp_server
from .views.dandiset_views import search_dandisets, dandiset_detail
from .views.api_views import api_filter_options, api_search, api_asset_search, api_dandiset_assets
from .views.query_views import sql_query_interface, sql_query_ajax, sql_validate_ajax, get_table_schema_ajax
from .sql_api import sql_execute, sql_validate, sql_schema

app_name = 'dandisets'

urlpatterns = [
    # Home page - main search interface
    path('', search_dandisets, name='search'),
    
    # Dandiset detail page
    path('dandiset/<str:dandi_id>/', dandiset_detail, name='detail'),
    
    # API endpoints
    path('api/search/', api_search, name='api_search'),
    path('api/assets/', api_asset_search, name='api_asset_search'),
    path('api/dandisets/<str:dandiset_id>/assets/', api_dandiset_assets, name='api_dandiset_assets'),
    path('api/filter-options/', api_filter_options, name='api_filter_options'),
    
    # MCP server endpoint
    path('mcp/', mcp_server, name='mcp_server'),
    
    # Sync API endpoint
    path('api/sync/trigger/', trigger_sync, name='api_sync_trigger'),
    
    # SQL Query Interface
    path('sql/', sql_query_interface, name='sql_query_interface'),
    path('api/sql/query-ajax/', sql_query_ajax, name='sql_query_ajax'),
    path('api/sql/validate-ajax/', sql_validate_ajax, name='sql_validate_ajax'),
    path('api/sql/table-schema/', get_table_schema_ajax, name='get_table_schema_ajax'),
    
    # Direct SQL API endpoints (kept for backward compatibility)
    path('api/sql/execute/', sql_execute, name='sql_execute'),
    path('api/sql/validate/', sql_validate, name='sql_validate'),
    path('api/sql/schema/', sql_schema, name='sql_schema'),
]
