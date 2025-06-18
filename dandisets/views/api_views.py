from typing import Dict, Any
from django.http import JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.template.loader import render_to_string
from ..models import Dandiset, Asset
from .utils import get_filter_options, get_dandiset_stats


def perform_dandiset_search(request_params) -> Dict[str, Any]:
    """
    Core search logic that can be used by both web and API interfaces.
    
    Args:
        request_params: Query parameters (request.GET or similar dict-like object)
    
    Returns:
        dict: Contains filtered dandisets queryset, filters applied, and other metadata
    """
    # Get all dandisets with basic related data
    dandisets = Dandiset.objects.select_related('assets_summary')
    
    # Apply filters based on request parameters
    filters = {}
    
    # Text search in name and description
    search_query = request_params.get('search', '').strip()
    if search_query:
        dandisets = dandisets.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
        filters['search'] = search_query
    
    # Species filter
    species_params = request_params.getlist('species')
    if species_params:
        from ..models import AssetsSummarySpecies, SpeciesType
        from .utils import get_deduplicated_species
        
        species_ids = []
        for param in species_params:
            try:
                if param.isdigit():
                    species_ids.append(int(param))
                else:
                    deduplicated_species = get_deduplicated_species()
                    for species_group in deduplicated_species:
                        if species_group['name'] == param:
                            species_ids.extend(species_group['all_ids'])
                            break
                    else:
                        species = SpeciesType.objects.filter(name=param).first()
                        if species:
                            species_ids.append(species.pk)
            except (ValueError, TypeError):
                continue
        
        if species_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummarySpecies.objects.filter(
                    species__id__in=species_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['species'] = species_params
    
    # Anatomy filter
    anatomy_params = request_params.getlist('anatomy')
    if anatomy_params:
        from ..models import Anatomy
        anatomy_ids = []
        for param in anatomy_params:
            try:
                if param.isdigit():
                    anatomy_ids.append(int(param))
                else:
                    anatomy = Anatomy.objects.filter(name=param).first()
                    if anatomy:
                        anatomy_ids.append(anatomy.pk)
            except (ValueError, TypeError):
                continue
        
        if anatomy_ids:
            dandisets = dandisets.filter(
                about__anatomy__id__in=anatomy_ids
            ).distinct()
            filters['anatomy'] = anatomy_params
    
    # Approach filter
    approach_params = request_params.getlist('approach')
    if approach_params:
        from ..models import AssetsSummaryApproach, ApproachType
        approach_ids = []
        for param in approach_params:
            try:
                if param.isdigit():
                    approach_ids.append(int(param))
                else:
                    approach = ApproachType.objects.filter(name=param).first()
                    if approach:
                        approach_ids.append(approach.pk)
            except (ValueError, TypeError):
                continue
        
        if approach_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryApproach.objects.filter(
                    approach__id__in=approach_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['approach'] = approach_params
    
    # Measurement technique filter
    technique_params = request_params.getlist('measurement_technique')
    if technique_params:
        from ..models import AssetsSummaryMeasurementTechnique, MeasurementTechniqueType
        technique_ids = []
        for param in technique_params:
            try:
                if param.isdigit():
                    technique_ids.append(int(param))
                else:
                    technique = MeasurementTechniqueType.objects.filter(name=param).first()
                    if technique:
                        technique_ids.append(technique.pk)
            except (ValueError, TypeError):
                continue
        
        if technique_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryMeasurementTechnique.objects.filter(
                    measurement_technique__id__in=technique_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['measurement_technique'] = technique_params
    
    # Subject sex filter
    sex_params = request_params.getlist('sex')
    if sex_params:
        from ..models import SexType
        sex_ids = []
        for param in sex_params:
            try:
                if param.isdigit():
                    sex_ids.append(int(param))
                else:
                    sex = SexType.objects.filter(name=param).first()
                    if sex:
                        sex_ids.append(sex.pk)
            except (ValueError, TypeError):
                continue
        
        if sex_ids:
            dandisets = dandisets.filter(
                assets__attributed_to__participant__sex__id__in=sex_ids
            ).distinct()
            filters['sex'] = sex_params
    
    # Number of subjects filter
    min_subjects = request_params.get('min_subjects')
    max_subjects = request_params.get('max_subjects')
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
    min_files = request_params.get('min_files')
    max_files = request_params.get('max_files')
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
    min_size = request_params.get('min_size')
    max_size = request_params.get('max_size')
    if min_size:
        try:
            min_size_bytes = float(min_size) * 1024 * 1024 * 1024
            dandisets = dandisets.filter(assets_summary__number_of_bytes__gte=min_size_bytes)
            filters['min_size'] = min_size
        except (ValueError, TypeError):
            pass
    if max_size:
        try:
            max_size_bytes = float(max_size) * 1024 * 1024 * 1024
            dandisets = dandisets.filter(assets_summary__number_of_bytes__lte=max_size_bytes)
            filters['max_size'] = max_size
        except (ValueError, TypeError):
            pass
    
    # Publication date range filter
    pub_date_start = request_params.get('pub_date_start')
    pub_date_end = request_params.get('pub_date_end')
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
    created_date_start = request_params.get('created_date_start')
    created_date_end = request_params.get('created_date_end')
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
    
    # Variables measured filter
    variables_measured = request_params.getlist('variables_measured')
    if variables_measured:
        variable_queries = Q()
        for variable in variables_measured:
            variable_queries |= Q(assets_summary__variable_measured__icontains=variable)
        dandisets = dandisets.filter(variable_queries).distinct()
        filters['variables_measured'] = variables_measured
    
    # Data standards filter
    data_standards_params = request_params.getlist('data_standards')
    if data_standards_params:
        from ..models import AssetsSummaryDataStandard, StandardsType
        data_standard_ids = []
        for param in data_standards_params:
            try:
                if param.isdigit():
                    data_standard_ids.append(int(param))
                else:
                    data_standard = StandardsType.objects.filter(name=param).first()
                    if data_standard:
                        data_standard_ids.append(data_standard.pk)
            except (ValueError, TypeError):
                continue
        
        if data_standard_ids:
            dandisets = dandisets.filter(
                assets_summary__in=AssetsSummaryDataStandard.objects.filter(
                    data_standard__id__in=data_standard_ids
                ).values_list('assets_summary', flat=True)
            ).distinct()
            filters['data_standards'] = data_standards_params
    
    # Asset-specific filters - these are used to filter assets within the filtered dandisets
    asset_path_search = request_params.get('asset_path', '').strip()
    asset_min_size = request_params.get('asset_min_size')
    asset_max_size = request_params.get('asset_max_size')
    asset_dandiset_id = request_params.get('asset_dandiset_id', '').strip()
    asset_sex_params = request_params.getlist('asset_sex')
    file_formats = request_params.getlist('file_format')
    
    # Build asset query for filtering assets within dandisets
    asset_query = Q()
    has_asset_filters = False
    
    if asset_path_search:
        asset_query &= Q(path__icontains=asset_path_search)
        filters['asset_path'] = asset_path_search
        has_asset_filters = True
    
    if file_formats:
        asset_query &= Q(encoding_format__in=file_formats)
        filters['file_format'] = file_formats
        has_asset_filters = True
        # Also filter dandisets that have these file formats
        dandisets = dandisets.filter(
            assets__encoding_format__in=file_formats
        ).distinct()
    
    if asset_min_size:
        try:
            min_size_bytes = float(asset_min_size) * 1024 * 1024
            asset_query &= Q(content_size__gte=min_size_bytes)
            filters['asset_min_size'] = asset_min_size
            has_asset_filters = True
        except (ValueError, TypeError):
            pass
    
    if asset_max_size:
        try:
            max_size_bytes = float(asset_max_size) * 1024 * 1024
            asset_query &= Q(content_size__lte=max_size_bytes)
            filters['asset_max_size'] = asset_max_size
            has_asset_filters = True
        except (ValueError, TypeError):
            pass
    
    if asset_sex_params:
        from ..models import SexType
        sex_ids = []
        for param in asset_sex_params:
            try:
                if param.isdigit():
                    sex_ids.append(int(param))
                else:
                    sex = SexType.objects.filter(name=param).first()
                    if sex:
                        sex_ids.append(sex.pk)
            except (ValueError, TypeError):
                continue
        
        if sex_ids:
            asset_query &= Q(attributed_to__participant__sex__id__in=sex_ids)
            filters['asset_sex'] = asset_sex_params
            has_asset_filters = True
    
    if asset_dandiset_id:
        if asset_dandiset_id.startswith('DANDI:'):
            dandiset_number = asset_dandiset_id[6:]
        else:
            dandiset_number = asset_dandiset_id
        
        asset_query &= Q(dandisets__base_id__icontains=dandiset_number)
        filters['asset_dandiset_id'] = asset_dandiset_id
        has_asset_filters = True
    
    # For non-file-format asset filters, also filter dandisets that contain matching assets
    if has_asset_filters and not file_formats:
        dandisets = dandisets.filter(assets__in=Asset.objects.filter(asset_query)).distinct()
    elif has_asset_filters and file_formats:
        # If we have file formats plus other asset filters, combine them
        other_asset_query = asset_query & ~Q(encoding_format__in=file_formats)  # Remove file format from asset query
        if other_asset_query != Q():
            dandisets = dandisets.filter(assets__in=Asset.objects.filter(other_asset_query)).distinct()
    
    # Apply ordering
    order_by = request_params.get('order_by', '-date_published')
    
    # Define valid ordering fields and their corresponding model fields
    order_field_mapping = {
        'name': 'name',
        '-name': '-name',
        'date_published': 'date_published',
        '-date_published': '-date_published',
        'created': 'date_created',
        '-created': '-date_created',
        'assets_summary__number_of_bytes': 'assets_summary__number_of_bytes',
        '-assets_summary__number_of_bytes': '-assets_summary__number_of_bytes',
        'assets_summary__number_of_subjects': 'assets_summary__number_of_subjects',
        '-assets_summary__number_of_subjects': '-assets_summary__number_of_subjects',
        'assets_summary__number_of_files': 'assets_summary__number_of_files',
        '-assets_summary__number_of_files': '-assets_summary__number_of_files',
    }
    
    # Apply ordering if valid
    if order_by in order_field_mapping:
        dandisets = dandisets.order_by(order_field_mapping[order_by])
        filters['order_by'] = order_by
    else:
        # Default ordering
        dandisets = dandisets.order_by('-date_published')
        filters['order_by'] = '-date_published'
    
    # Get statistics for the current filtered results
    stats = get_dandiset_stats(dandisets)
    
    return {
        'dandisets': dandisets,
        'filters': filters,
        'has_asset_filters': has_asset_filters,
        'stats': stats,
        'asset_query': asset_query,
    }


def api_filter_options(request: HttpRequest) -> JsonResponse:
    """JSON API endpoint for getting filter options"""
    options = get_filter_options()
    
    # Convert to JSON-serializable format
    data = {
        'species': [
            {
                'id': s['id'], 
                'name': s['name'], 
                'scientific_name': s['scientific_name'],
                'all_ids': s['all_ids']
            } if isinstance(s, dict) else {
                'id': s.id, 
                'name': s.name, 
                'identifier': getattr(s, 'identifier', '')
            } 
            for s in options['species']
        ],
        'anatomy': [{'id': a.id, 'name': a.name, 'identifier': getattr(a, 'identifier', '')} for a in options['anatomy']],
        'approaches': [{'id': a.id, 'name': a.name, 'identifier': getattr(a, 'identifier', '')} for a in options['approaches']],
        'measurement_techniques': [{'id': m.id, 'name': m.name, 'identifier': getattr(m, 'identifier', '')} for m in options['measurement_techniques']],
        'data_standards': [{'id': d.id, 'name': d.name, 'identifier': getattr(d, 'identifier', '')} for d in options['data_standards']],
        'variables_measured': options.get('variables_measured', []),
        'sex_types': [{'id': s.id, 'name': s.name} for s in options.get('sex_types', [])],
    }
    
    return JsonResponse(data)


def api_dandiset_assets(request: HttpRequest, dandiset_id: str) -> JsonResponse:
    """JSON API endpoint for getting paginated assets for a specific dandiset"""
    try:
        dandiset = get_object_or_404(Dandiset, id=dandiset_id)
        
        # Get filters from request parameters (same logic as main search view)
        asset_query = Q()
        has_asset_filters = False
        
        # Asset path search
        asset_path_search = request.GET.get('asset_path', '').strip()
        if asset_path_search:
            asset_query &= Q(path__icontains=asset_path_search)
            has_asset_filters = True
        
        # File format filter
        file_formats = request.GET.getlist('file_format')
        if file_formats:
            asset_query &= Q(encoding_format__in=file_formats)
            has_asset_filters = True
        
        # Asset size filters
        asset_min_size = request.GET.get('asset_min_size')
        asset_max_size = request.GET.get('asset_max_size')
        
        if asset_min_size:
            try:
                # Convert MB to bytes
                min_size_bytes = float(asset_min_size) * 1024 * 1024
                asset_query &= Q(content_size__gte=min_size_bytes)
                has_asset_filters = True
            except (ValueError, TypeError):
                pass
        
        if asset_max_size:
            try:
                # Convert MB to bytes
                max_size_bytes = float(asset_max_size) * 1024 * 1024
                asset_query &= Q(content_size__lte=max_size_bytes)
                has_asset_filters = True
            except (ValueError, TypeError):
                pass
        
        # Subject sex filter
        asset_sex_params = request.GET.getlist('asset_sex')
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
                            sex_ids.append(sex.pk)
                except (ValueError, TypeError):
                    continue
            
            if sex_ids:
                # Filter assets by participant sex using the relationship:
                # Asset → AssetWasAttributedTo → Participant → SexType
                asset_query &= Q(attributed_to__participant__sex__id__in=sex_ids)
                has_asset_filters = True
        
        # Dandiset ID filter
        asset_dandiset_id = request.GET.get('asset_dandiset_id', '').strip()
        if asset_dandiset_id:
            # Handle both full DANDI ID format (DANDI:000001) and just the number (000001)
            if asset_dandiset_id.startswith('DANDI:'):
                dandiset_number = asset_dandiset_id[6:]  # Remove 'DANDI:' prefix
            else:
                dandiset_number = asset_dandiset_id
            
            # Filter assets that belong to dandisets with this base_id pattern
            asset_query &= Q(dandisets__base_id__icontains=dandiset_number)
            has_asset_filters = True
        
        # Get all assets for this dandiset (for total count)
        all_assets = Asset.objects.filter(dandisets=dandiset)
        total_assets_count = all_assets.count()
        
        # Get filtered assets for this dandiset
        if has_asset_filters:
            assets = all_assets.filter(asset_query).order_by('path')
        else:
            assets = all_assets.order_by('path')
        
        # Pagination
        assets_per_page = 10
        page_number = request.GET.get('page', 1)
        paginator = Paginator(assets, assets_per_page)
        page_obj = paginator.get_page(page_number)
        
        # Render the assets as HTML
        try:
            assets_html = render_to_string('dandisets/assets_list.html', {
                'assets': page_obj,
                'dandiset': dandiset,
            })
        except Exception as e:
            return JsonResponse({
                'error': f'Template rendering error: {str(e)}',
                'template': 'assets_list.html'
            }, status=500)
        
        # Render pagination controls as HTML
        try:
            pagination_html = render_to_string('dandisets/assets_pagination.html', {
                'page_obj': page_obj,
                'dandiset': dandiset,
            })
        except Exception as e:
            return JsonResponse({
                'error': f'Template rendering error: {str(e)}',
                'template': 'assets_pagination.html'
            }, status=500)
        
        return JsonResponse({
            'assets_html': assets_html,
            'pagination_html': pagination_html,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,  # Filtered count
            'total_assets_count': total_assets_count,  # All assets in dandiset
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'start_index': page_obj.start_index(),
            'end_index': page_obj.end_index(),
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'API error: {str(e)}',
            'dandiset_id': dandiset_id
        }, status=500)


def api_asset_search(request: HttpRequest) -> JsonResponse:
    """REST API endpoint for searching assets across all dandisets with pagination
    
    Supports asset-specific filtering and pagination.
    
    Query Parameters:
        - asset_path: Asset path search
        - file_format: File format filter
        - asset_min_size, asset_max_size: Asset size range in MB
        - asset_dandiset_id: Asset dandiset ID filter
        - asset_sex: Asset subject sex filter (ID or name)
        - encoding_format: Encoding format filter
        - page: Page number for pagination (default: 1)
        - per_page: Results per page (default: 20, max: 100)
        - format: Response format ('summary' or 'detailed', default: 'summary')
        - order_by: Order results by field (default: 'path')
    
    Returns:
        JSON response with paginated asset results and metadata
    """
    try:
        # Start with all assets
        assets = Asset.objects.all()
        
        # Apply asset-specific filters
        filters = {}
        
        # Asset path search
        asset_path_search = request.GET.get('asset_path', '').strip()
        if asset_path_search:
            assets = assets.filter(path__icontains=asset_path_search)
            filters['asset_path'] = asset_path_search
        
        # File format filter
        file_formats = request.GET.getlist('file_format')
        if file_formats:
            assets = assets.filter(encoding_format__in=file_formats)
            filters['file_format'] = file_formats
        
        # Encoding format filter (alias for file_format)
        encoding_formats = request.GET.getlist('encoding_format')
        if encoding_formats:
            assets = assets.filter(encoding_format__in=encoding_formats)
            filters['encoding_format'] = encoding_formats
        
        # Asset size filters
        asset_min_size = request.GET.get('asset_min_size')
        asset_max_size = request.GET.get('asset_max_size')
        
        if asset_min_size:
            try:
                min_size_bytes = float(asset_min_size) * 1024 * 1024
                assets = assets.filter(content_size__gte=min_size_bytes)
                filters['asset_min_size'] = asset_min_size
            except (ValueError, TypeError):
                pass
        
        if asset_max_size:
            try:
                max_size_bytes = float(asset_max_size) * 1024 * 1024
                assets = assets.filter(content_size__lte=max_size_bytes)
                filters['asset_max_size'] = asset_max_size
            except (ValueError, TypeError):
                pass
        
        # Subject sex filter
        asset_sex_params = request.GET.getlist('asset_sex')
        if asset_sex_params:
            from ..models import SexType
            sex_ids = []
            for param in asset_sex_params:
                try:
                    if param.isdigit():
                        sex_ids.append(int(param))
                    else:
                        sex = SexType.objects.filter(name=param).first()
                        if sex:
                            sex_ids.append(sex.pk)
                except (ValueError, TypeError):
                    continue
            
            if sex_ids:
                assets = assets.filter(attributed_to__participant__sex__id__in=sex_ids)
                filters['asset_sex'] = asset_sex_params
        
        # Dandiset ID filter
        asset_dandiset_id = request.GET.get('asset_dandiset_id', '').strip()
        if asset_dandiset_id:
            if asset_dandiset_id.startswith('DANDI:'):
                dandiset_number = asset_dandiset_id[6:]
            else:
                dandiset_number = asset_dandiset_id
            
            assets = assets.filter(dandisets__base_id__icontains=dandiset_number)
            filters['asset_dandiset_id'] = asset_dandiset_id
        
        # Date range filters - use created_at since date_created doesn't exist on Asset model
        date_created_start = request.GET.get('date_created_start')
        date_created_end = request.GET.get('date_created_end')
        
        if date_created_start:
            try:
                from datetime import datetime
                start_date = datetime.strptime(date_created_start, '%Y-%m-%d').date()
                assets = assets.filter(created_at__date__gte=start_date)
                filters['date_created_start'] = date_created_start
            except (ValueError, TypeError):
                pass
        
        if date_created_end:
            try:
                from datetime import datetime
                end_date = datetime.strptime(date_created_end, '%Y-%m-%d').date()
                assets = assets.filter(created_at__date__lte=end_date)
                filters['date_created_end'] = date_created_end
            except (ValueError, TypeError):
                pass
        
        # Ordering
        order_by = request.GET.get('order_by', 'path')
        valid_order_fields = ['path', 'content_size', 'date_created', 'date_modified', 'encoding_format']
        
        if order_by.lstrip('-') in valid_order_fields:
            assets = assets.order_by(order_by)
        else:
            assets = assets.order_by('path')  # Default ordering
        
        # Pagination
        per_page = min(int(request.GET.get('per_page', 20)), 100)  # Max 100 per page
        page_number = request.GET.get('page', 1)
        paginator = Paginator(assets, per_page)
        page_obj = paginator.get_page(page_number)
        
        # Get response format
        response_format = request.GET.get('format', 'summary')
        
        # Serialize assets
        results = []
        for asset in page_obj:
            if response_format == 'detailed':
                # Detailed format with more fields
                asset_data = {
                    'id': asset.id,
                    'path': asset.path,
                    'encoding_format': asset.encoding_format,
                    'content_size': asset.content_size,
                    'content_size_mb': round(asset.content_size / (1024 * 1024), 2) if asset.content_size else None,
                    'date_created': asset.created_at.isoformat() if asset.created_at else None,
                    'date_modified': asset.date_modified.isoformat() if asset.date_modified else None,
                    'digest': asset.digest,
                    'content_url': asset.content_url,
                }
                
                # Add associated dandisets
                dandisets_data = []
                for dandiset in asset.dandisets.all():
                    dandisets_data.append({
                        'id': dandiset.id,
                        'dandi_id': dandiset.dandi_id,
                        'name': dandiset.name,
                        'url': dandiset.url,
                    })
                asset_data['dandisets'] = dandisets_data
                
            else:
                # Summary format with basic fields
                asset_data = {
                    'id': asset.id,
                    'path': asset.path,
                    'encoding_format': asset.encoding_format,
                    'content_size_mb': round(asset.content_size / (1024 * 1024), 2) if asset.content_size else None,
                    'date_created': asset.created_at.isoformat() if asset.created_at else None,
                }
                
                # Add basic dandiset info
                dandiset = asset.dandisets.first()
                if dandiset:
                    asset_data['dandiset'] = {
                        'id': dandiset.id,
                        'dandi_id': dandiset.dandi_id,
                        'name': dandiset.name,
                    }
            
            results.append(asset_data)
        
        # Build response
        response_data = {
            'results': results,
            'pagination': {
                'page': page_obj.number,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'start_index': page_obj.start_index(),
                'end_index': page_obj.end_index(),
            },
            'filters_applied': filters,
            'meta': {
                'query_time': None,
                'api_version': '1.0',
                'format': response_format,
                'order_by': order_by,
            }
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'error': f'Asset search API error: {str(e)}',
            'status': 'error'
        }, status=500)


def api_search(request):
    """REST API endpoint for searching dandisets
    
    Accepts the same parameters as the web search interface and returns JSON results.
    Supports all the filters available in the main search functionality.
    
    Query Parameters:
        - search: Text search in name and description
        - species: Species filter (ID or name)
        - anatomy: Anatomy filter (ID or name) 
        - approach: Approach filter (ID or name)
        - measurement_technique: Measurement technique filter (ID or name)
        - sex: Subject sex filter (ID or name)
        - min_subjects, max_subjects: Number of subjects range
        - min_files, max_files: Number of files range
        - min_size, max_size: Size range in GB
        - pub_date_start, pub_date_end: Publication date range (YYYY-MM-DD)
        - created_date_start, created_date_end: Creation date range (YYYY-MM-DD)
        - file_format: File format filter
        - variables_measured: Variables measured filter
        - data_standards: Data standards filter (ID or name)
        - asset_path: Asset path search
        - asset_min_size, asset_max_size: Asset size range in MB
        - asset_dandiset_id: Asset dandiset ID filter
        - asset_sex: Asset subject sex filter (ID or name)
        - page: Page number for pagination (default: 1)
        - per_page: Results per page (default: 10, max: 100)
        - format: Response format ('summary' or 'detailed', default: 'summary')
    
    Returns:
        JSON response with paginated dandiset results and metadata
    """
    try:
        # Use the shared search function
        search_results = perform_dandiset_search(request.GET)
        dandisets = search_results['dandisets']
        filters = search_results['filters']
        has_asset_filters = search_results['has_asset_filters']
        stats = search_results['stats']
        
        # Pagination
        per_page = min(int(request.GET.get('per_page', 10)), 100)  # Max 100 per page
        page_number = request.GET.get('page', 1)
        paginator = Paginator(dandisets, per_page)
        page_obj = paginator.get_page(page_number)
        
        # Get response format
        response_format = request.GET.get('format', 'summary')
        
        # Check if we should include asset matches with pagination
        include_assets = request.GET.get('include_assets', 'false').lower() == 'true'
        assets_per_dandiset = min(int(request.GET.get('assets_per_dandiset', 5)), 20)  # Max 20 assets per dandiset
        
        # Asset pagination settings
        include_asset_pagination = request.GET.get('include_asset_pagination', 'false').lower() == 'true'
        assets_page = int(request.GET.get('assets_page', 1))
        assets_per_page = min(int(request.GET.get('assets_per_page', 20)), 100)  # Max 100 assets per page
        
        # Serialize dandisets
        results = []
        for dandiset in page_obj:
            if response_format == 'detailed':
                # Detailed format with more fields
                dandiset_data = {
                    'id': dandiset.id,
                    'dandi_id': dandiset.dandi_id,
                    'base_id': dandiset.base_id,
                    'name': dandiset.name,
                    'description': dandiset.description,
                    'date_created': dandiset.date_created.isoformat() if dandiset.date_created else None,
                    'date_published': dandiset.date_published.isoformat() if dandiset.date_published else None,
                    'date_modified': dandiset.date_modified.isoformat() if dandiset.date_modified else None,
                    'url': dandiset.url,
                }
                
                # Add assets summary if available
                if hasattr(dandiset, 'assets_summary') and dandiset.assets_summary:
                    summary = dandiset.assets_summary
                    dandiset_data['assets_summary'] = {
                        'number_of_subjects': summary.number_of_subjects,
                        'number_of_files': summary.number_of_files,
                        'number_of_bytes': summary.number_of_bytes,
                        'variable_measured': summary.variable_measured,
                    }
            else:
                # Summary format with basic fields
                dandiset_data = {
                    'id': dandiset.id,
                    'dandi_id': dandiset.dandi_id,
                    'name': dandiset.name,
                    'description': dandiset.description[:200] + '...' if dandiset.description and len(dandiset.description) > 200 else dandiset.description,
                    'date_published': dandiset.date_published.isoformat() if dandiset.date_published else None,
                    'url': dandiset.url,
                }
                
                # Add basic assets summary
                if hasattr(dandiset, 'assets_summary') and dandiset.assets_summary:
                    summary = dandiset.assets_summary
                    dandiset_data['summary'] = {
                        'subjects': summary.number_of_subjects,
                        'files': summary.number_of_files,
                        'size_bytes': summary.number_of_bytes,
                    }
            
            # Include matching assets if requested and we have asset filters
            if include_assets:
                if has_asset_filters:
                    # Get assets that match the asset filters for this dandiset
                    matching_assets = dandiset.assets.filter(search_results['asset_query']).order_by('path')[:assets_per_dandiset]
                    total_matching_assets = dandiset.assets.filter(search_results['asset_query']).count()
                else:
                    # Get all assets for this dandiset (limited number)
                    matching_assets = dandiset.assets.all().order_by('path')[:assets_per_dandiset]
                    total_matching_assets = dandiset.assets.count()
                
                assets_data = []
                for asset in matching_assets:
                    asset_info = {
                        'id': asset.id,
                        'path': asset.path,
                        'encoding_format': asset.encoding_format,
                        'content_size': asset.content_size,
                        'content_size_mb': round(asset.content_size / (1024 * 1024), 2) if asset.content_size else None,
                        'date_created': asset.created_at.isoformat() if asset.created_at else None,
                        'date_modified': asset.date_modified.isoformat() if asset.date_modified else None,
                    }
                    
                    # Add more details in detailed format
                    if response_format == 'detailed':
                        asset_info.update({
                            'digest': asset.digest,
                            'content_url': asset.content_url,
                        })
                    
                    assets_data.append(asset_info)
                
                dandiset_data['matching_assets'] = {
                    'assets': assets_data,
                    'total_matching_assets': total_matching_assets,
                    'shown_count': len(assets_data),
                    'has_more': total_matching_assets > len(assets_data),
                }
            
            results.append(dandiset_data)
        
        # Add asset search results if requested
        asset_results = None
        if include_asset_pagination and has_asset_filters:
            # Get all assets that match the filters across all dandisets
            all_matching_assets = Asset.objects.filter(search_results['asset_query']).order_by('path')
            
            # Paginate the assets
            assets_paginator = Paginator(all_matching_assets, assets_per_page)
            assets_page_obj = assets_paginator.get_page(assets_page)
            
            # Serialize assets
            assets_data = []
            for asset in assets_page_obj:
                asset_info = {
                    'id': asset.id,
                    'path': asset.path,
                    'encoding_format': asset.encoding_format,
                    'content_size_mb': round(asset.content_size / (1024 * 1024), 2) if asset.content_size else None,
                    'date_created': asset.created_at.isoformat() if asset.created_at else None,
                    'date_modified': asset.date_modified.isoformat() if asset.date_modified else None,
                }
                
                # Add more details in detailed format
                if response_format == 'detailed':
                    asset_info.update({
                        'digest': asset.digest,
                        'content_url': asset.content_url,
                    })
                
                # Add basic dandiset info
                dandiset = asset.dandisets.first()
                if dandiset:
                    asset_info['dandiset'] = {
                        'id': dandiset.id,
                        'dandi_id': dandiset.dandi_id,
                        'name': dandiset.name,
                    }
                
                assets_data.append(asset_info)
            
            asset_results = {
                'assets': assets_data,
                'pagination': {
                    'page': assets_page_obj.number,
                    'per_page': assets_per_page,
                    'total_pages': assets_paginator.num_pages,
                    'total_count': assets_paginator.count,
                    'has_previous': assets_page_obj.has_previous(),
                    'has_next': assets_page_obj.has_next(),
                    'start_index': assets_page_obj.start_index(),
                    'end_index': assets_page_obj.end_index(),
                }
            }
        
        # Build response
        response_data = {
            'results': results,
            'pagination': {
                'page': page_obj.number,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'start_index': page_obj.start_index(),
                'end_index': page_obj.end_index(),
            },
            'filters_applied': filters,
            'statistics': {
                'total_dandisets': stats['total_count'],
                'total_subjects': stats['total_subjects'],
                'total_files': stats['max_files'],  # Using max files as an approximation
                'total_bytes': stats['max_size'],  # Using max size as an approximation
                'min_subjects': stats['min_subjects'],
                'max_subjects': stats['max_subjects'],
                'min_files': stats['min_files'],
                'max_files': stats['max_files'],
                'min_size': stats['min_size'],
                'max_size': stats['max_size'],
                'min_size_gb': stats.get('min_size_gb'),
                'max_size_gb': stats.get('max_size_gb'),
            },
            'meta': {
                'query_time': None,  # Could add timing if needed
                'api_version': '1.0',
                'format': response_format,
            }
        }
        
        # Include asset results if available
        if asset_results:
            response_data['asset_results'] = asset_results
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'error': f'Search API error: {str(e)}',
            'status': 'error'
        }, status=500)
