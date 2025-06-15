from django.urls import path
from . import views

app_name = 'dandisets'

urlpatterns = [
    path('', views.search_dandisets, name='search'),
    path('search/', views.search_dandisets, name='search'),
    path('detail/<path:dandi_id>/', views.dandiset_detail, name='detail'),
    path('api/filter-options/', views.api_filter_options, name='api_filter_options'),
]
