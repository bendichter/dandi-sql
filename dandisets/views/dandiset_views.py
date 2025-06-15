from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Dandiset
from .utils import get_filter_options, get_dandiset_stats


def search_dandisets(request):
    """Main search view for dandisets with optional asset filtering and display"""
    from django.db.models import Prefetch
    from ..models import Asset
    
    # Get all dandisets with basic related data
    dandisets = Dandiset.objects.select_related('assets_summary')
    
    # Apply filters based on request parameters
    filters = {}
    
    # Check if we should show assets
    show_assets = request.GET.get('show_assets')
    if show_assets:
        filters['show_assets'] = True
    
    # Text search in name and description
    search_query = request.GET.get('search', '').strip()
    if search_query:
        dandisets = dandisets.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
        filters['search'] = search_query
    
    # Species filter - using exists() to work around OneToOneField issues
    species_ids = request.GET.getlist('species')
    if species_ids:
        from ..models import AssetsSummarySpecies
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummarySpecies.objects.filter(
                species__id__in=species_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['species'] = species_ids
    
    # Anatomy filter - using Django's default reverse lookups  
    anatomy_ids = request.GET.getlist('anatomy')
    if anatomy_ids:
        dandisets = dandisets.filter(
            about__anatomy__id__in=anatomy_ids
        ).distinct()
        filters['anatomy'] = anatomy_ids
    
    # Approach filter - using exists() to work around OneToOneField issues
    approach_ids = request.GET.getlist('approach')
    if approach_ids:
        from ..models import AssetsSummaryApproach
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryApproach.objects.filter(
                approach__id__in=approach_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['approach'] = approach_ids
    
    # Measurement technique filter - using exists() to work around OneToOneField issues
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
    
    # Data standards filter - using exists() to work around OneToOneField issues
    data_standards = request.GET.getlist('data_standards')
    if data_standards:
        from ..models import AssetsSummaryDataStandard
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryDataStandard.objects.filter(
                data_standard__id__in=data_standards
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['data_standards'] = data_standards
    
    # Asset-specific filters
    asset_path_search = request.GET.get('asset_path', '').strip()
    asset_min_size = request.GET.get('asset_min_size')
    asset_max_size = request.GET.get('asset_max_size')
    
    # Build asset query for filtering dandisets and optionally showing assets
    asset_query = Q()
    has_asset_filters = False
    
    if asset_path_search:
        asset_query &= Q(path__icontains=asset_path_search)
        filters['asset_path'] = asset_path_search
        has_asset_filters = True
    
    # Apply main file format filter to assets as well
    if file_formats:
        asset_query &= Q(encoding_format__in=file_formats)
        has_asset_filters = True
    
    if asset_min_size:
        try:
            # Convert MB to bytes
            min_size_bytes = float(asset_min_size) * 1024 * 1024
            asset_query &= Q(content_size__gte=min_size_bytes)
            filters['asset_min_size'] = asset_min_size
            has_asset_filters = True
        except (ValueError, TypeError):
            pass
    
    if asset_max_size:
        try:
            # Convert MB to bytes
            max_size_bytes = float(asset_max_size) * 1024 * 1024
            asset_query &= Q(content_size__lte=max_size_bytes)
            filters['asset_max_size'] = asset_max_size
            has_asset_filters = True
        except (ValueError, TypeError):
            pass
    
    # If we have asset filters, filter dandisets that contain matching assets
    if has_asset_filters:
        dandisets = dandisets.filter(assets__in=Asset.objects.filter(asset_query)).distinct()
    
    # Always load matching assets for frontend toggle functionality
    if has_asset_filters:
        # Show only matching assets
        matching_assets_prefetch = Prefetch(
            'assets',
            queryset=Asset.objects.filter(asset_query).order_by('path')[:10],
            to_attr='matching_assets'
        )
    else:
        # Show all assets (limited to first 10 for performance)
        matching_assets_prefetch = Prefetch(
            'assets',
            queryset=Asset.objects.order_by('path')[:10],
            to_attr='matching_assets'
        )
    dandisets = dandisets.prefetch_related(matching_assets_prefetch)
    
    # Order by name
    dandisets = dandisets.order_by('name')
    
    # Pagination
    paginator = Paginator(dandisets, 20)  # Show 20 dandisets per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get filter options for the form
    filter_options = get_filter_options()
    
    # Get statistics for the current filtered results
    stats = get_dandiset_stats(dandisets)
    
    context = {
        'page_obj': page_obj,
        'dandisets': page_obj,
        'filter_options': filter_options,
        'current_filters': filters,
        'stats': stats,
        'total_results': paginator.count,
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
