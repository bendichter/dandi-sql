from django.urls import path
from .views import search_dandisets, dandiset_detail
from .views.api_views import api_filter_options, api_dandiset_assets, api_search, api_asset_search
from .views.sync_views import trigger_sync
from .sql_api import sql_execute, sql_validate, sql_schema

app_name = 'dandisets'

urlpatterns = [
    path('', search_dandisets, name='search'),
    path('search/', search_dandisets, name='search'),
    path('api/search/', api_search, name='api_search'),
    path('api/assets/search/', api_asset_search, name='api_asset_search'),
    path('api/filter-options/', api_filter_options, name='api_filter_options'),
    path('api/dandiset/<int:dandiset_id>/assets/', api_dandiset_assets, name='api_dandiset_assets'),
    
    # Sync API endpoint
    path('api/sync/trigger/', trigger_sync, name='api_sync_trigger'),
    
    # Direct SQL API endpoints
    path('api/sql/execute/', sql_execute, name='sql_execute'),
    path('api/sql/validate/', sql_validate, name='sql_validate'),
    path('api/sql/schema/', sql_schema, name='sql_schema'),
]
