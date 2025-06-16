from django.urls import path
from .views import search_dandisets, dandiset_detail
from .views.api_views import api_filter_options, api_dandiset_assets

app_name = 'dandisets'

urlpatterns = [
    path('', search_dandisets, name='search'),
    path('search/', search_dandisets, name='search'),
    path('api/filter-options/', api_filter_options, name='api_filter_options'),
    path('api/dandiset/<int:dandiset_id>/assets/', api_dandiset_assets, name='api_dandiset_assets'),
]
