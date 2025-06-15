from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Min, Max
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import (
    Dandiset, SpeciesType, Anatomy, ApproachType, 
    MeasurementTechniqueType, StandardsType
)


def search_dandisets(request):
    """Main search view for dandisets"""
    # Get all dandisets with basic related data
    dandisets = Dandiset.objects.select_related('assets_summary')
    
    # Apply filters based on request parameters
    filters = {}
    
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
        from .models import AssetsSummarySpecies
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
        from .models import AssetsSummaryApproach
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryApproach.objects.filter(
                approach__id__in=approach_ids
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['approach'] = approach_ids
    
    # Measurement technique filter - using exists() to work around OneToOneField issues
    technique_ids = request.GET.getlist('measurement_technique')
    if technique_ids:
        from .models import AssetsSummaryMeasurementTechnique
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
        from .models import AssetsSummaryDataStandard
        dandisets = dandisets.filter(
            assets_summary__in=AssetsSummaryDataStandard.objects.filter(
                data_standard__id__in=data_standards
            ).values_list('assets_summary', flat=True)
        ).distinct()
        filters['data_standards'] = data_standards
    
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


def get_filter_options():
    """Get all available filter options"""
    from .models import AssetsSummary
    
    # Get unique variables measured from the database
    variables_measured = get_unique_variables_measured()
    
    return {
        'species': SpeciesType.objects.all().order_by('name')[:50],  # Limit for demo
        'anatomy': Anatomy.objects.all().order_by('name')[:50],  # Limit for demo
        'approaches': ApproachType.objects.all().order_by('name')[:50],  # Limit for demo
        'measurement_techniques': MeasurementTechniqueType.objects.all().order_by('name')[:50],  # Limit for demo
        'data_standards': StandardsType.objects.all().order_by('name')[:50],  # Limit for demo
        'variables_measured': variables_measured[:50],  # Limit for demo
    }


def get_unique_variables_measured():
    """Extract unique variables measured from all assets summaries"""
    from .models import AssetsSummary
    import json
    
    variables_set = set()
    
    # Get all assets summaries with non-empty variable_measured fields
    summaries = AssetsSummary.objects.exclude(variable_measured__isnull=True).exclude(variable_measured=[])
    
    for summary in summaries:
        if summary.variable_measured:
            try:
                # Handle both list and string formats
                if isinstance(summary.variable_measured, list):
                    variables_list = summary.variable_measured
                else:
                    # Try to parse as JSON if it's a string
                    try:
                        variables_list = json.loads(summary.variable_measured)
                    except (json.JSONDecodeError, TypeError):
                        # If it's just a string, treat it as a single variable
                        variables_list = [summary.variable_measured]
                
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


def get_dandiset_stats(queryset):
    """Get statistics for the given queryset of dandisets"""
    stats = queryset.aggregate(
        total_count=Count('id'),
        total_subjects=Count('assets_summary__number_of_subjects'),
        min_subjects=Min('assets_summary__number_of_subjects'),
        max_subjects=Max('assets_summary__number_of_subjects'),
        min_files=Min('assets_summary__number_of_files'),
        max_files=Max('assets_summary__number_of_files'),
        min_size=Min('assets_summary__number_of_bytes'),
        max_size=Max('assets_summary__number_of_bytes'),
    )
    
    # Convert bytes to GB for display
    if stats['min_size']:
        stats['min_size_gb'] = round(stats['min_size'] / (1024**3), 2)
    if stats['max_size']:
        stats['max_size_gb'] = round(stats['max_size'] / (1024**3), 2)
    
    return stats


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
