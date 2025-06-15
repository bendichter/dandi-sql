from django.db.models import Count, Min, Max
from ..models import SpeciesType, Anatomy, ApproachType, MeasurementTechniqueType, StandardsType
import json


def get_filter_options():
    """Get all available filter options"""
    from ..models import AssetsSummary
    
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
    from ..models import AssetsSummary
    
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
