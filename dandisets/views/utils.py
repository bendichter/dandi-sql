from django.db.models import Count, Min, Max
from ..models import SpeciesType, Anatomy, ApproachType, MeasurementTechniqueType, StandardsType
import json
import re


def standardize_species_name(name):
    """Standardize species names to reduce duplicates and return formatted display name"""
    if not name:
        return name, name
    
    # Convert to lowercase for comparison
    standardized = name.lower().strip()
    
    # Common standardizations - maps to (scientific_name, common_name)
    standardizations = {
        # Mouse variants
        r'\bmus musculus\b': ('Mus musculus', 'Mouse'),
        r'\bmouse\b': ('Mus musculus', 'Mouse'),
        r'\bhouse mouse\b': ('Mus musculus', 'Mouse'),
        
        # Rat variants
        r'\brattus norvegicus\b': ('Rattus norvegicus', 'Rat'),
        r'\brat\b': ('Rattus norvegicus', 'Rat'),
        r'\bnorway rat\b': ('Rattus norvegicus', 'Rat'),
        
        # Human variants
        r'\bhomo sapiens\b': ('Homo sapiens', 'Human'),
        r'\bhuman\b': ('Homo sapiens', 'Human'),
        
        # Macaque variants
        r'\bmacaca mulatta\b': ('Macaca mulatta', 'Rhesus Macaque'),
        r'\brhesus macaque\b': ('Macaca mulatta', 'Rhesus Macaque'),
        r'\brhesus monkey\b': ('Macaca mulatta', 'Rhesus Macaque'),
        
        # Pig-tailed macaque variants
        r'\bmacaca nemestrina\b': ('Macaca nemestrina', 'Pig-tailed Macaque'),
        r'\bpig-tailed macaque\b': ('Macaca nemestrina', 'Pig-tailed Macaque'),
        r'\bpigtailed macaque\b': ('Macaca nemestrina', 'Pig-tailed Macaque'),
        
        # Fly variants
        r'\bdrosophila melanogaster\b': ('Drosophila melanogaster', 'Fruit Fly'),
        r'\bfruit fly\b': ('Drosophila melanogaster', 'Fruit Fly'),
        
        # Zebrafish variants
        r'\bdanio rerio\b': ('Danio rerio', 'Zebrafish'),
        r'\bzebrafish\b': ('Danio rerio', 'Zebrafish'),
        
        # C. elegans variants
        r'\bcaenorhabditis elegans\b': ('Caenorhabditis elegans', 'Nematode'),
        r'\bc\. elegans\b': ('Caenorhabditis elegans', 'Nematode'),
        r'\bnematode\b': ('Caenorhabditis elegans', 'Nematode'),
        
        # Cattle variants
        r'\bbos taurus\b': ('Bos taurus', 'Cattle'),
        r'\bcattle\b': ('Bos taurus', 'Cattle'),
        r'\bcow\b': ('Bos taurus', 'Cattle'),
        
        # Pig variants
        r'\bsus scrofa\b': ('Sus scrofa', 'Pig'),
        r'\bpig\b': ('Sus scrofa', 'Pig'),
        r'\bswine\b': ('Sus scrofa', 'Pig'),
        
        # Dog variants
        r'\bcanis lupus familiaris\b': ('Canis lupus familiaris', 'Dog'),
        r'\bdog\b': ('Canis lupus familiaris', 'Dog'),
        
        # Cat variants
        r'\bfelis catus\b': ('Felis catus', 'Cat'),
        r'\bcat\b': ('Felis catus', 'Cat'),
        
        # Chicken variants
        r'\bgallus gallus\b': ('Gallus gallus', 'Chicken'),
        r'\bchicken\b': ('Gallus gallus', 'Chicken'),
    }
    
    # Apply standardizations
    for pattern, (scientific, common) in standardizations.items():
        if re.search(pattern, standardized):
            return f"{scientific} - {common}", scientific
    
    # If no standardization found, try to parse if it's already in scientific format
    title_name = name.title().strip()
    if ' ' in title_name and len(title_name.split()) >= 2:
        # Assume it's already a scientific name
        return f"{title_name} - {title_name}", title_name
    else:
        # Single word, treat as common name
        return f"{title_name} - {title_name}", title_name


def get_deduplicated_species():
    """Get deduplicated and standardized species list"""
    all_species = SpeciesType.objects.all().order_by('name')
    
    # Group species by scientific name (the key from standardization)
    species_groups = {}
    
    for species in all_species:
        display_name, scientific_name = standardize_species_name(species.name)
        
        if scientific_name not in species_groups:
            species_groups[scientific_name] = {
                'display_name': display_name,
                'species_list': []
            }
        species_groups[scientific_name]['species_list'].append(species)
    
    # Create deduplicated list with representative species and all IDs
    deduplicated_species = []
    
    for scientific_name, group_data in species_groups.items():
        species_list = group_data['species_list']
        display_name = group_data['display_name']
        
        # Use the first species as the representative
        representative = species_list[0]
        
        # Collect all IDs that map to this scientific name
        all_ids = [s.id for s in species_list]
        
        # Create a custom object with standardized name and all associated IDs
        deduplicated_species.append({
            'id': representative.id,  # Primary ID for the option value
            'name': display_name,  # Formatted display name (e.g., "Mus musculus - Mouse")
            'scientific_name': scientific_name,  # Scientific name for matching
            'all_ids': all_ids,  # All IDs that map to this scientific name
            'original_names': [s.name for s in species_list]  # Original names for debugging
        })
    
    # Sort by display name
    deduplicated_species.sort(key=lambda x: x['name'])
    
    return deduplicated_species


def get_filter_options():
    """Get all available filter options"""
    from ..models import AssetsSummary
    
    # Get unique variables measured from the database
    variables_measured = get_unique_variables_measured()
    
    return {
        'species': get_deduplicated_species()[:50],  # Deduplicated species
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
