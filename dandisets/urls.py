from django.urls import path
from .views.sync_views import trigger_sync
from .views.mcp_views import mcp_server
from .sql_api import sql_execute, sql_validate, sql_schema

app_name = 'dandisets'

urlpatterns = [
    # MCP server endpoint
    path('mcp/', mcp_server, name='mcp_server'),
    
    # Sync API endpoint
    path('api/sync/trigger/', trigger_sync, name='api_sync_trigger'),
    
    # Direct SQL API endpoints (kept for backward compatibility)
    path('api/sql/execute/', sql_execute, name='sql_execute'),
    path('api/sql/validate/', sql_validate, name='sql_validate'),
    path('api/sql/schema/', sql_schema, name='sql_schema'),
]
