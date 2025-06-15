from django.urls import path
from .views import search_dandisets, dandiset_detail

app_name = 'dandisets'

urlpatterns = [
    path('', search_dandisets, name='search'),
    path('search/', search_dandisets, name='search'),
]
