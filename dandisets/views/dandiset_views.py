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
    
    # Species filter - handle both IDs and formatted names
    species_params = request.GET.getlist('species')
    if species_params:
        from ..models import AssetsSummarySpecies, SpeciesType
        from .utils import get_deduplicated_species
        
        species_ids = []
        for param in species_params:
            try:
                # Try as ID first
                if param.isdigit():
                    species_ids.append(int(param))
                else:
                    # Try as formatted name (e.g., "Mus musculus - Mouse")
                    deduplicated_species = get_deduplicated_species()
                    for species_group in deduplicated_species:
                        if species_group['name'] == param:
                            species_ids.extend(species_group['all_ids'])
                            break
                    else:
                        # Fallback: try direct name match
                        species = SpeciesType.objects.filter(name=param).first()
                        if species:
                            species_ids.append(species.id)
            except (ValueError, TypeError):
                continue
        
        if species_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummarySpecies.objects.filter(
                    species__id__in=species_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['species'] = species_params
    
    # Anatomy filter - handle both IDs and names
    anatomy_params = request.GET.getlist('anatomy')
    if anatomy_params:
        from ..models import Anatomy
        # Try to get anatomy by name first, fall back to ID if numeric
        anatomy_ids = []
        for param in anatomy_params:
            try:
                # Try as ID first
                if param.isdigit():
                    anatomy_ids.append(int(param))
                else:
                    # Try as name
                    anatomy = Anatomy.objects.filter(name=param).first()
                    if anatomy:
                        anatomy_ids.append(anatomy.id)
            except (ValueError, TypeError):
                continue
        
        if anatomy_ids:
            dandisets = dandisets.filter(
                about__anatomy__id__in=anatomy_ids
            ).distinct()
            filters['anatomy'] = anatomy_params
    
    # Approach filter - handle both IDs and names
    approach_params = request.GET.getlist('approach')
    if approach_params:
        from ..models import AssetsSummaryApproach, ApproachType
        # Try to get approach by name first, fall back to ID if numeric
        approach_ids = []
        for param in approach_params:
            try:
                # Try as ID first
                if param.isdigit():
                    approach_ids.append(int(param))
                else:
                    # Try as name
                    approach = ApproachType.objects.filter(name=param).first()
                    if approach:
                        approach_ids.append(approach.id)
            except (ValueError, TypeError):
                continue
        
        if approach_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryApproach.objects.filter(
                    approach__id__in=approach_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['approach'] = approach_params
    
    # Measurement technique filter - handle both IDs and names
    technique_params = request.GET.getlist('measurement_technique')
    if technique_params:
        from ..models import AssetsSummaryMeasurementTechnique, MeasurementTechniqueType
        # Try to get technique by name first, fall back to ID if numeric
        technique_ids = []
        for param in technique_params:
            try:
                # Try as ID first
                if param.isdigit():
                    technique_ids.append(int(param))
                else:
                    # Try as name
                    technique = MeasurementTechniqueType.objects.filter(name=param).first()
                    if technique:
                        technique_ids.append(technique.id)
            except (ValueError, TypeError):
                continue
        
        if technique_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryMeasurementTechnique.objects.filter(
                    measurement_technique__id__in=technique_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['measurement_technique'] = technique_params
    
    # Subject sex filter (dandiset level) - handle both IDs and names
    sex_params = request.GET.getlist('sex')
    if sex_params:
        from ..models import SexType
        # Try to get sex by name first, fall back to ID if numeric
        sex_ids = []
        for param in sex_params:
            try:
                # Try as ID first
                if param.isdigit():
                    sex_ids.append(int(param))
                else:
                    # Try as name
                    sex = SexType.objects.filter(name=param).first()
                    if sex:
                        sex_ids.append(sex.id)
            except (ValueError, TypeError):
                continue
        
        if sex_ids:
            # Filter dandisets that have assets with participants of the specified sex
            dandisets = dandisets.filter(
                assets__attributed_to__participant__sex__id__in=sex_ids
            ).distinct()
            filters['sex'] = sex_params
    
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
    
    # Data standards filter - handle both IDs and names
    data_standards_params = request.GET.getlist('data_standards')
    if data_standards_params:
        from ..models import AssetsSummaryDataStandard, StandardsType
        # Try to get data standard by name first, fall back to ID if numeric
        data_standard_ids = []
        for param in data_standards_params:
            try:
                # Try as ID first
                if param.isdigit():
                    data_standard_ids.append(int(param))
                else:
                    # Try as name
                    data_standard = StandardsType.objects.filter(name=param).first()
                    if data_standard:
                        data_standard_ids.append(data_standard.id)
            except (ValueError, TypeError):
                continue
        
        if data_standard_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryDataStandard.objects.filter(
                    data_standard__id__in=data_standard_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['data_standards'] = data_standards_params
    
    # Asset-specific filters
    asset_path_search = request.GET.get('asset_path', '').strip()
    asset_min_size = request.GET.get('asset_min_size')
    asset_max_size = request.GET.get('asset_max_size')
    asset_dandiset_id = request.GET.get('asset_dandiset_id', '').strip()
    asset_sex_params = request.GET.getlist('asset_sex')
    
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
    
    # Subject sex filter for assets
    if asset_sex_params:
        from ..models import SexType
        sex_ids = []
        for param in asset_sex_params:
            try:
                # Try as ID first
                if param.isdigit():
                    sex_ids.append(int(param))
                else:
                    # Try as name
                    sex = SexType.objects.filter(name=param).first()
                    if sex:
                        sex_ids.append(sex.id)
            except (ValueError, TypeError):
                continue
        
        if sex_ids:
            # Filter assets by participant sex using the relationship:
            # Asset → AssetWasAttributedTo → Participant → SexType
            asset_query &= Q(attributed_to__participant__sex__id__in=sex_ids)
            filters['asset_sex'] = asset_sex_params
            has_asset_filters = True
    
    # Dandiset ID filter for assets
    if asset_dandiset_id:
        # Handle both full DANDI ID format (DANDI:000001) and just the number (000001)
        if asset_dandiset_id.startswith('DANDI:'):
            dandiset_number = asset_dandiset_id[6:]  # Remove 'DANDI:' prefix
        else:
            dandiset_number = asset_dandiset_id
        
        # Filter assets that belong to dandisets with this base_id pattern
        asset_query &= Q(dandisets__base_id__icontains=dandiset_number)
        filters['asset_dandiset_id'] = asset_dandiset_id
        has_asset_filters = True
    
    # If we have asset filters, filter dandisets that contain matching assets
    if has_asset_filters:
        dandisets = dandisets.filter(assets__in=Asset.objects.filter(asset_query)).distinct()
    
    # Order by name
    dandisets = dandisets.order_by('name')
    
    # Pagination
    paginator = Paginator(dandisets, 6)  # Show 6 dandisets per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate asset counts for each dandiset in the current page
    dandisets_with_counts = []
    for dandiset in page_obj:
        total_assets = dandiset.assets.count()
        filtered_assets = total_assets  # Default to total if no asset filters
        
        if has_asset_filters:
            # Calculate how many assets match the filters for this specific dandiset
            filtered_assets = dandiset.assets.filter(asset_query).count()
        
        dandisets_with_counts.append({
            'dandiset': dandiset,
            'total_assets': total_assets,
            'filtered_assets': filtered_assets,
        })
    
    # Get filter options for the form
    filter_options = get_filter_options()
    
    # Get statistics for the current filtered results
    stats = get_dandiset_stats(dandisets)
    
    context = {
        'page_obj': page_obj,
        'dandisets': page_obj,
        'dandisets_with_counts': dandisets_with_counts,
        'filter_options': filter_options,
        'current_filters': filters,
        'stats': stats,
        'total_results': paginator.count,
        'has_asset_filters': has_asset_filters,
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
