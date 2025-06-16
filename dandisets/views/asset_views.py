from django.shortcuts import render
import requests
from urllib.parse import urlencode


def search_assets(request):
    """Search view for assets - uses internal API calls"""
    # Build query parameters for the API call
    query_params = request.GET.copy()
    
    # Add web-specific parameters
    page = query_params.get('page', 1)
    per_page = 10  # Web interface shows 10 dandisets per page (fewer since we show assets)
    query_params['per_page'] = per_page
    query_params['format'] = 'summary'
    query_params['include_assets'] = 'true'
    query_params['assets_per_dandiset'] = 10  # Show more assets per dandiset for asset search
    
    try:
        # Make internal API call to search endpoint
        api_url = f"{request.build_absolute_uri('/').rstrip('/')}/api/search/"
        query_string = urlencode(query_params, doseq=True)
        response = requests.get(f"{api_url}?{query_string}", timeout=30)
        response.raise_for_status()
        api_data = response.json()
        
        # Make API call to get filter options
        filter_api_url = f"{request.build_absolute_uri('/').rstrip('/')}/api/filter-options/"
        filter_response = requests.get(filter_api_url, timeout=10)
        filter_response.raise_for_status()
        filter_options = filter_response.json()
        
        # Process the API response for web template
        results = api_data.get('results', [])
        pagination = api_data.get('pagination', {})
        filters_applied = api_data.get('filters_applied', {})
        stats = api_data.get('statistics', {})
        
        # Create pagination object-like structure for template compatibility
        class MockPageObj:
            def __init__(self, results, pagination):
                self.object_list = results
                self.number = pagination.get('page', 1)
                self.num_pages = pagination.get('total_pages', 1)
                self.count = pagination.get('total_count', 0)
                self.pagination = pagination
                
            def has_previous(self):
                return self.pagination.get('has_previous', False)
                
            def has_next(self):
                return self.pagination.get('has_next', False)
                
            def __iter__(self):
                return iter(self.object_list)
        
        page_obj = MockPageObj(results, pagination)
        
        # Check if any asset filters are applied
        has_asset_filters = any(key.startswith('asset_') or key in ['file_format'] 
                               for key in filters_applied.keys())
        
        # Calculate asset statistics from the API results
        total_assets = 0
        total_filtered_assets = 0
        for dandiset_data in results:
            dandiset_assets = dandiset_data.get('summary', {}).get('files', 0)
            total_assets += dandiset_assets
            
            if 'matching_assets' in dandiset_data:
                filtered_assets = dandiset_data['matching_assets'].get('total_matching_assets', dandiset_assets)
            else:
                filtered_assets = dandiset_assets
            total_filtered_assets += filtered_assets
        
        asset_stats = {
            'total_assets': total_filtered_assets if has_asset_filters else total_assets,
            'total_dandisets_with_assets': len([d for d in results if d.get('summary', {}).get('files', 0) > 0])
        }
        
        context = {
            'page_obj': page_obj,
            'dandisets': results,
            'filter_options': filter_options,
            'current_filters': filters_applied,
            'asset_stats': asset_stats,
            'total_results': pagination.get('total_count', 0),
            'has_asset_filters': has_asset_filters,
            'api_error': None,
        }
        
    except requests.RequestException as e:
        # Fallback to empty results on API error
        context = {
            'page_obj': None,
            'dandisets': [],
            'filter_options': {'species': [], 'anatomy': [], 'approaches': [], 'measurement_techniques': [], 'data_standards': [], 'variables_measured': [], 'sex_types': []},
            'current_filters': {},
            'asset_stats': {'total_assets': 0, 'total_dandisets_with_assets': 0},
            'total_results': 0,
            'has_asset_filters': False,
            'api_error': f"Search service temporarily unavailable: {str(e)}",
        }
    
    return render(request, 'dandisets/asset_search.html', context)
