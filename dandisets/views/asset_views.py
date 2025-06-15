from django.shortcuts import render
from django.db.models import Q, Prefetch, Count, Min, Max
from django.core.paginator import Paginator
from ..models import Dandiset, Asset
from .utils import get_filter_options


def search_assets(request):
    """Search view for assets grouped by dandisets"""
    # Start with dandisets and apply existing filters
    dandisets = Dandiset.objects.select_related('assets_summary')
    
    # Apply filters based on request parameters
    filters = {}
    
    # Apply all existing dandiset filters first
    dandisets, filters = apply_dandiset_filters(dandisets, request, filters)
    
    # Asset-specific filters
    # Asset path/name search
    asset_path_search = request.GET.get('asset_path', '').strip()
    if asset_path_search:
        filters['asset_path'] = asset_path_search
    
    # Asset file format filter
    asset_file_formats = request.GET.getlist('asset_file_format')
    if asset_file_formats:
        filters['asset_file_format'] = asset_file_formats
    
    # Asset file size filter (individual file size in MB)
    asset_min_size = request.GET.get('asset_min_size')
    asset_max_size = request.GET.get('asset_max_size')
    if asset_min_size:
        try:
            filters['asset_min_size'] = asset_min_size
        except (ValueError, TypeError):
            pass
    if asset_max_size:
        try:
            filters['asset_max_size'] = asset_max_size
        except (ValueError, TypeError):
            pass
    
    # Asset variables measured filter
    asset_variables_measured = request.GET.getlist('asset_variables_measured')
    if asset_variables_measured:
        filters['asset_variables_measured'] = asset_variables_measured
    
    # Asset date modified filter
    asset_date_start = request.GET.get('asset_date_start')
    asset_date_end = request.GET.get('asset_date_end')
    if asset_date_start:
        try:
            from datetime import datetime
            datetime.strptime(asset_date_start, '%Y-%m-%d').date()
            filters['asset_date_start'] = asset_date_start
        except (ValueError, TypeError):
            pass
    if asset_date_end:
        try:
            from datetime import datetime
            datetime.strptime(asset_date_end, '%Y-%m-%d').date()
            filters['asset_date_end'] = asset_date_end
        except (ValueError, TypeError):
            pass
    
    # Build asset query
    asset_query = Q()
    
    if asset_path_search:
        asset_query &= Q(path__icontains=asset_path_search)
    
    if asset_file_formats:
        asset_query &= Q(encoding_format__in=asset_file_formats)
    
    if asset_min_size:
        try:
            # Convert MB to bytes
            min_size_bytes = float(asset_min_size) * 1024 * 1024
            asset_query &= Q(content_size__gte=min_size_bytes)
        except (ValueError, TypeError):
            pass
    
    if asset_max_size:
        try:
            # Convert MB to bytes
            max_size_bytes = float(asset_max_size) * 1024 * 1024
            asset_query &= Q(content_size__lte=max_size_bytes)
        except (ValueError, TypeError):
            pass
    
    if asset_variables_measured:
        variable_queries = Q()
        for variable in asset_variables_measured:
            variable_queries |= Q(variable_measured__icontains=variable)
        asset_query &= variable_queries
    
    if asset_date_start:
        try:
            from datetime import datetime
            start_date = datetime.strptime(asset_date_start, '%Y-%m-%d').date()
            asset_query &= Q(date_modified__date__gte=start_date)
        except (ValueError, TypeError):
            pass
    
    if asset_date_end:
        try:
            from datetime import datetime
            end_date = datetime.strptime(asset_date_end, '%Y-%m-%d').date()
            asset_query &= Q(date_modified__date__lte=end_date)
        except (ValueError, TypeError):
            pass
    
    # Create a Prefetch object to get only matching assets
    if asset_query != Q():
        matching_assets_prefetch = Prefetch(
            'assets',
            queryset=Asset.objects.filter(asset_query).order_by('path'),
            to_attr='matching_assets'
        )
        # Filter to only include dandisets that have matching assets
        dandisets = dandisets.filter(assets__in=Asset.objects.filter(asset_query)).distinct()
    else:
        # If no asset filters, get all assets
        matching_assets_prefetch = Prefetch(
            'assets',
            queryset=Asset.objects.order_by('path'),
            to_attr='matching_assets'
        )
    
    # Apply the prefetch to get the matching assets
    dandisets = dandisets.prefetch_related(matching_assets_prefetch)
    
    # Order by name
    dandisets = dandisets.order_by('name')
    
    # Pagination
    paginator = Paginator(dandisets, 10)  # Show 10 dandisets per page (fewer since we show assets)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get filter options for the form
    filter_options = get_asset_filter_options()
    
    # Get statistics for the current filtered results
    asset_stats = get_asset_stats(dandisets, asset_query)
    
    context = {
        'page_obj': page_obj,
        'dandisets': page_obj,
        'filter_options': filter_options,
        'current_filters': filters,
        'asset_stats': asset_stats,
        'total_results': paginator.count,
    }
    
    return render(request, 'dandisets/asset_search.html', context)


def apply_dandiset_filters(dandisets, request, filters):
    """Apply all existing dandiset filters - extracted from search_dandisets"""
    # Text search in name and description
    search_query = request.GET.get('search', '').strip()
    if search_query:
        dandisets = dandisets.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
        filters['search'] = search_query
    
    # Species filter
    species_ids = request.GET.getlist('species')
    if species_ids:
        from ..models import AssetsSummarySpecies
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummarySpecies.objects.filter(
                species__id__in=species_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['species'] = species_ids
    
    # Anatomy filter
    anatomy_ids = request.GET.getlist('anatomy')
    if anatomy_ids:
        dandisets = dandisets.filter(
            about__anatomy__id__in=anatomy_ids
        ).distinct()
        filters['anatomy'] = anatomy_ids
    
    # Approach filter
    approach_ids = request.GET.getlist('approach')
    if approach_ids:
        from ..models import AssetsSummaryApproach
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryApproach.objects.filter(
                approach__id__in=approach_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['approach'] = approach_ids
    
    # Measurement technique filter
    technique_ids = request.GET.getlist('measurement_technique')
    if technique_ids:
        from ..models import AssetsSummaryMeasurementTechnique
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryMeasurementTechnique.objects.filter(
                measurement_technique__id__in=technique_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['measurement_technique'] = technique_ids
    
    # Number of subjects filter
    min_subjects = request.GET.get('min_subjects')
    max_subjects = request.GET.get('max_subjects')
    if min_subjects:
        try:
            dandisets = dandisets.filter(assets_summary__number_of_subjects__gte=int(min_subjects))
            filters['min_subjects'] = min_subjects
        except (ValueError, TypeError):
            pass
    if max_subjects:
        try:
            dandisets = dandisets.filter(assets_summary__number_of_subjects__lte=int(max_subjects))
            filters['max_subjects'] = max_subjects
        except (ValueError, TypeError):
            pass
    
    # Number of files filter  
    min_files = request.GET.get('min_files')
    max_files = request.GET.get('max_files')
    if min_files:
        try:
            dandisets = dandisets.filter(assets_summary__number_of_files__gte=int(min_files))
            filters['min_files'] = min_files
        except (ValueError, TypeError):
            pass
    if max_files:
        try:
            dandisets = dandisets.filter(assets_summary__number_of_files__lte=int(max_files))
            filters['max_files'] = max_files
        except (ValueError, TypeError):
            pass
    
    # Size filter (in bytes)
    min_size = request.GET.get('min_size')
    max_size = request.GET.get('max_size')
    if min_size:
        try:
            # Convert from GB to bytes
            min_size_bytes = float(min_size) * 1024 * 1024 * 1024
            dandisets = dandisets.filter(assets_summary__number_of_bytes__gte=min_size_bytes)
            filters['min_size'] = min_size
        except (ValueError, TypeError):
            pass
    if max_size:
        try:
            # Convert from GB to bytes
            max_size_bytes = float(max_size) * 1024 * 1024 * 1024
            dandisets = dandisets.filter(assets_summary__number_of_bytes__lte=max_size_bytes)
            filters['max_size'] = max_size
        except (ValueError, TypeError):
            pass
    
    # Publication date range filter
    pub_date_start = request.GET.get('pub_date_start')
    pub_date_end = request.GET.get('pub_date_end')
    if pub_date_start:
        try:
            from datetime import datetime
            start_date = datetime.strptime(pub_date_start, '%Y-%m-%d').date()
            dandisets = dandisets.filter(date_published__date__gte=start_date)
            filters['pub_date_start'] = pub_date_start
        except (ValueError, TypeError):
            pass
    if pub_date_end:
        try:
            from datetime import datetime
            end_date = datetime.strptime(pub_date_end, '%Y-%m-%d').date()
            dandisets = dandisets.filter(date_published__date__lte=end_date)
            filters['pub_date_end'] = pub_date_end
        except (ValueError, TypeError):
            pass
    
    # Creation date range filter
    created_date_start = request.GET.get('created_date_start')
    created_date_end = request.GET.get('created_date_end')
    if created_date_start:
        try:
            from datetime import datetime
            start_date = datetime.strptime(created_date_start, '%Y-%m-%d').date()
            dandisets = dandisets.filter(date_created__date__gte=start_date)
            filters['created_date_start'] = created_date_start
        except (ValueError, TypeError):
            pass
    if created_date_end:
        try:
            from datetime import datetime
            end_date = datetime.strptime(created_date_end, '%Y-%m-%d').date()
            dandisets = dandisets.filter(date_created__date__lte=end_date)
            filters['created_date_end'] = created_date_end
        except (ValueError, TypeError):
            pass
    
    # File format filter - filter dandisets that contain assets with specific encoding formats
    file_formats = request.GET.getlist('file_format')
    if file_formats:
        dandisets = dandisets.filter(
            assets__encoding_format__in=file_formats
        ).distinct()
        filters['file_format'] = file_formats
    
    # Variables measured filter - search in JSON field for specific variables
    variables_measured = request.GET.getlist('variables_measured')
    if variables_measured:
        variable_queries = Q()
        for variable in variables_measured:
            variable_queries |= Q(assets_summary__variable_measured__icontains=variable)
        dandisets = dandisets.filter(variable_queries).distinct()
        filters['variables_measured'] = variables_measured
    
    # Data standards filter
    data_standards = request.GET.getlist('data_standards')
    if data_standards:
        from ..models import AssetsSummaryDataStandard
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryDataStandard.objects.filter(
                data_standard__id__in=data_standards
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['data_standards'] = data_standards
    
    return dandisets, filters


def get_asset_filter_options():
    """Get all available filter options including asset-specific ones"""
    base_options = get_filter_options()
    
    # Add asset-specific variables measured
    asset_variables = get_unique_asset_variables_measured()
    
    # Merge the options
    base_options['asset_variables_measured'] = asset_variables[:50]
    
    return base_options


def get_unique_asset_variables_measured():
    """Extract unique variables measured from all assets - using same approach as dandisets search"""
    from .utils import get_unique_variables_measured
    
    # Use the same function that works for the dandisets search, but get data from Asset model instead
    import json
    
    variables_set = set()
    
    # Get all assets with non-empty variable_measured fields
    assets = Asset.objects.exclude(variable_measured__isnull=True).exclude(variable_measured=[])
    
    for asset in assets:
        if asset.variable_measured:
            try:
                # Handle both list and string formats
                if isinstance(asset.variable_measured, list):
                    variables_list = asset.variable_measured
                else:
                    # Try to parse as JSON if it's a string
                    try:
                        variables_list = json.loads(asset.variable_measured)
                    except (json.JSONDecodeError, TypeError):
                        # If it's just a string, treat it as a single variable
                        variables_list = [asset.variable_measured]
                
                # Add each variable to the set
                for variable in variables_list:
                    if variable and isinstance(variable, str):
                        # Clean up the variable name
                        cleaned_variable = variable.strip()
                        if cleaned_variable:
                            variables_set.add(cleaned_variable)
                            
            except Exception:
                # Skip problematic entries
                continue
    
    # Convert to sorted list of tuples (value, display_name)
    variables_list = [(var, var) for var in sorted(variables_set)]
    
    return variables_list


def get_asset_stats(dandisets_queryset, asset_query):
    """Get statistics for assets in the given dandisets"""
    # Get all assets that match both dandiset and asset filters
    if asset_query != Q():
        asset_queryset = Asset.objects.filter(
            dandisets__in=dandisets_queryset
        ).filter(asset_query).distinct()
    else:
        asset_queryset = Asset.objects.filter(
            dandisets__in=dandisets_queryset
        ).distinct()
    
    stats = asset_queryset.aggregate(
        total_assets=Count('id'),
        min_asset_size=Min('content_size'),
        max_asset_size=Max('content_size'),
    )
    
    # Convert bytes to MB for display
    if stats['min_asset_size']:
        stats['min_asset_size_mb'] = round(stats['min_asset_size'] / (1024**2), 2)
    if stats['max_asset_size']:
        stats['max_asset_size_mb'] = round(stats['max_asset_size'] / (1024**2), 2)
    
    return stats
