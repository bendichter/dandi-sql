from django.shortcuts import render, get_object_or_404
from ..models import Dandiset
import requests
from urllib.parse import urlencode
from datetime import datetime


def transform_api_dandiset_for_template(dandiset_data):
    """Transform API response data to match template expectations"""
    class MockDandiset:
        def __init__(self, data):
            self.id = data.get('id')
            self.dandi_id = data.get('dandi_id')
            self.name = data.get('name', '')
            self.description = data.get('description', '')
            self.url = data.get('url', '')
            
            # Handle date_published
            date_pub = data.get('date_published')
            if date_pub:
                try:
                    # Parse ISO format date string
                    if isinstance(date_pub, str):
                        self.date_published = datetime.fromisoformat(date_pub.replace('Z', '+00:00'))
                    else:
                        self.date_published = date_pub
                except:
                    self.date_published = None
            else:
                self.date_published = None
            
            # Create mock assets_summary with the summary data
            summary = data.get('summary', {})
            self.assets_summary = MockAssetsSummary(summary)
            
            # Create empty sets for related data (these would normally be querysets)
            self.dandisetabout_set = MockQuerySet([])
            
    class MockAssetsSummary:
        def __init__(self, summary_data):
            self.number_of_subjects = summary_data.get('subjects')
            self.number_of_files = summary_data.get('files', 0)
            self.number_of_bytes = summary_data.get('size_bytes', 0)
            
            # Create empty sets for related data
            self.assetssummaryspecies_set = MockQuerySet([])
            self.assetssummaryapproach_set = MockQuerySet([])
    
    class MockQuerySet:
        def __init__(self, data):
            self.data = data
            
        def all(self):
            return self.data
    
    return MockDandiset(dandiset_data)


def search_dandisets(request):
    """Main search view for dandisets - uses internal API calls"""
    # Build query parameters for the API call
    query_params = request.GET.copy()
    
    # Add web-specific parameters
    page = query_params.get('page', 1)
    per_page = 6  # Web interface shows 6 dandisets per page
    query_params['per_page'] = per_page
    query_params['format'] = 'summary'
    
    # Check if we should show assets (web-specific feature)
    show_assets = request.GET.get('show_assets')
    if show_assets:
        query_params['include_assets'] = 'true'
        query_params['assets_per_dandiset'] = 5  # Show 5 assets per dandiset
    
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
        
        # Transform API response data to match template expectations
        dandisets_with_counts = []
        for dandiset_data in results:
            total_assets = dandiset_data.get('summary', {}).get('files', 0)
            
            # Check if we have asset info from API
            if 'matching_assets' in dandiset_data:
                filtered_assets = dandiset_data['matching_assets'].get('total_matching_assets', total_assets)
            else:
                filtered_assets = total_assets
            
            # Transform the API response to match what the template expects
            transformed_dandiset = transform_api_dandiset_for_template(dandiset_data)
            
            dandisets_with_counts.append({
                'dandiset': transformed_dandiset,
                'total_assets': total_assets,
                'filtered_assets': filtered_assets,
            })
        
        # Check if any filters are applied
        has_any_filters = bool(filters_applied)
        has_asset_filters = any(key.startswith('asset_') or key in ['file_format'] 
                               for key in filters_applied.keys())
        
        context = {
            'page_obj': page_obj,
            'dandisets': results,
            'dandisets_with_counts': dandisets_with_counts,
            'filter_options': filter_options,
            'current_filters': filters_applied,
            'stats': stats,
            'total_results': pagination.get('total_count', 0),
            'has_asset_filters': has_asset_filters,
            'has_any_filters': has_any_filters,
            'api_error': None,
        }
        
    except requests.RequestException as e:
        # Fallback to empty results on API error
        context = {
            'page_obj': None,
            'dandisets': [],
            'dandisets_with_counts': [],
            'filter_options': {'species': [], 'anatomy': [], 'approaches': [], 'measurement_techniques': [], 'data_standards': [], 'variables_measured': [], 'sex_types': []},
            'current_filters': {},
            'stats': {},
            'total_results': 0,
            'has_asset_filters': False,
            'has_any_filters': False,
            'api_error': f"Search service temporarily unavailable: {str(e)}",
        }
    
    return render(request, 'dandisets/search.html', context)


def dandiset_detail(request, dandi_id):
    """Detail view for a single dandiset"""
    try:
        dandiset = get_object_or_404(Dandiset, dandi_id=dandi_id)
    except:
        # Try finding by base_id if exact dandi_id doesn't work
        try:
            dandiset = Dandiset.objects.filter(base_id=dandi_id).first()
            if not dandiset:
                return render(request, 'dandisets/not_found.html', {'dandi_id': dandi_id})
        except:
            return render(request, 'dandisets/not_found.html', {'dandi_id': dandi_id})
    
    # Get related data (simplified for now)
    species_list = []
    anatomy_list = []
    approaches = []
    measurement_techniques = []
    contributors = []
    related_resources = []
    
    context = {
        'dandiset': dandiset,
        'species_list': species_list,
        'anatomy_list': anatomy_list,
        'approaches': approaches,
        'measurement_techniques': measurement_techniques,
        'contributors': contributors,
        'related_resources': related_resources,
    }
    
    return render(request, 'dandisets/detail.html', context)
