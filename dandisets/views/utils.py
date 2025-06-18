from typing import Dict, List, Tuple, Any, Optional
from django.db.models import Count, Min, Max, QuerySet
from ..models import SpeciesType, Anatomy, ApproachType, MeasurementTechniqueType, StandardsType
import json
import re


def standardize_species_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Standardize species names to reduce duplicates and return formatted display name"""
    if not name:
        return name, name
    
    # Clean the input name
    cleaned_name = name.strip()
    
    # Check if the name is already in "Scientific Name - Common Name" format
    if ' - ' in cleaned_name:
        parts = cleaned_name.split(' - ', 1)  # Split on first occurrence only
        if len(parts) == 2:
            scientific_part, common_part = parts
            scientific_part = scientific_part.strip()
            common_part = common_part.strip()
            
            # If both parts exist and scientific part looks like a binomial name (two words)
            if (scientific_part and common_part and 
                len(scientific_part.split()) >= 2):
                # Already properly formatted, just return it with proper capitalization
                words = scientific_part.split()
                formatted_scientific = words[0].capitalize() + ' ' + ' '.join(word.lower() for word in words[1:])
                formatted_common = common_part  # Keep common name as is
                return f"{formatted_scientific} - {formatted_common}", formatted_scientific
    
    # Convert to lowercase for comparison with patterns
    standardized = cleaned_name.lower()
    
    # Common standardizations - maps to (scientific_name, common_name)
    standardizations = {
        # Mouse variants
        r'\bmus musculus\b': ('Mus musculus', 'Mouse'),
        r'\bmouse\b': ('Mus musculus', 'Mouse'),
        r'\bhouse mouse\b': ('Mus musculus', 'Mouse'),
        
        # Rat variants (including brown rat and compound entries)
        r'\brattus norvegicus\b': ('Rattus norvegicus', 'Rat'),
        r'\bnorway rat\b': ('Rattus norvegicus', 'Rat'),
        r'\bbrown rat\b': ('Rattus norvegicus', 'Rat'),
        r'\brats\b': ('Rattus norvegicus', 'Rat'),
        r'\brat\b': ('Rattus norvegicus', 'Rat'),
        
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
        
        # Zebra finch variants
        r'\btaeniopygia guttata\b': ('Taeniopygia guttata', 'Zebra Finch'),
        r'\bzebra finch\b': ('Taeniopygia guttata', 'Zebra Finch'),
        
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
        
        # Marmoset variants
        r'\bcallithrix jacchus\b': ('Callithrix jacchus', 'Common Marmoset'),
        r'\bcommon marmoset\b': ('Callithrix jacchus', 'Common Marmoset'),
        r'\bmarmoset\b': ('Callithrix jacchus', 'Common Marmoset'),
        
        # Cynomolgus monkey variants
        r'\bmacaca fascicularis\b': ('Macaca fascicularis', 'Cynomolgus Monkey'),
        r'\bcynomolgus monkey\b': ('Macaca fascicularis', 'Cynomolgus Monkey'),
    }
    
    # Apply standardizations
    for pattern, (scientific, common) in standardizations.items():
        if re.search(pattern, standardized):
            return f"{scientific} - {common}", scientific
    
    # If no standardization found, try to parse if it's already in scientific format
    title_name = cleaned_name.title()
    if ' ' in title_name and len(title_name.split()) >= 2:
        # Looks like a scientific name (genus species)
        words = title_name.split()
        if len(words) >= 2:
            # Take first two words as genus and species
            genus = words[0].capitalize()
            species = words[1].lower()
            scientific_name = f"{genus} {species}"
            return f"{scientific_name} - {scientific_name}", scientific_name
    
    # Single word, treat as common name and create a placeholder scientific name
    return f"{title_name} - {title_name}", title_name


def get_deduplicated_species() -> List[Dict[str, Any]]:
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


def get_filter_options() -> Dict[str, Any]:
    """Get all available filter options"""
    from ..models import AssetsSummary, SexType
    
    # Get unique variables measured from the database
    variables_measured = get_unique_variables_measured()
    
    return {
        'species': get_deduplicated_species()[:50],  # Deduplicated species
        'anatomy': Anatomy.objects.all().order_by('name')[:50],  # Limit for demo
        'approaches': ApproachType.objects.all().order_by('name')[:50],  # Limit for demo
        'measurement_techniques': MeasurementTechniqueType.objects.all().order_by('name')[:50],  # Limit for demo
        'data_standards': StandardsType.objects.all().order_by('name')[:50],  # Limit for demo
        'variables_measured': variables_measured[:50],  # Limit for demo
        'sex_types': SexType.objects.all().order_by('name'),  # Sex types for asset filtering
    }


def get_unique_variables_measured() -> List[Tuple[str, str]]:
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


def get_dandiset_stats(queryset: QuerySet) -> Dict[str, Any]:
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
