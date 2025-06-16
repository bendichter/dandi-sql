from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.template.loader import render_to_string
from ..models import Dandiset, Asset
from .utils import get_filter_options


def api_filter_options(request):
    """JSON API endpoint for getting filter options"""
    options = get_filter_options()
    
    # Convert to JSON-serializable format
    data = {
        'species': [{'id': s.id, 'name': s.name, 'identifier': s.identifier} for s in options['species']],
        'anatomy': [{'id': a.id, 'name': a.name, 'identifier': a.identifier} for a in options['anatomy']],
        'approaches': [{'id': a.id, 'name': a.name, 'identifier': a.identifier} for a in options['approaches']],
        'measurement_techniques': [{'id': m.id, 'name': m.name, 'identifier': m.identifier} for m in options['measurement_techniques']],
        'data_standards': [{'id': d.id, 'name': d.name, 'identifier': d.identifier} for d in options['data_standards']],
    }
    
    return JsonResponse(data)


def api_dandiset_assets(request, dandiset_id):
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
