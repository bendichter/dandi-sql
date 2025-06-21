from django import template

register = template.Library()

@register.filter
def lookup(dict_value, key):
    """
    Custom template filter to look up dictionary values by key.
    Usage: {{ dict|lookup:key }}
    """
    if isinstance(dict_value, dict):
        return dict_value.get(key)
    return None


@register.filter
def paginate_range(total_pages, current_page):
    """
    Generate a range of page numbers for pagination, with ellipsis for large ranges.
    Usage: {{ total_pages|paginate_range:current_page }}
    """
    if total_pages <= 7:
        # Show all pages if 7 or fewer
        return list(range(1, total_pages + 1))
    
    if current_page <= 4:
        # Show first 5 pages + ellipsis + last page
        return [1, 2, 3, 4, 5, "...", total_pages]
    elif current_page >= total_pages - 3:
        # Show first page + ellipsis + last 5 pages
        return [1, "...", total_pages - 4, total_pages - 3, total_pages - 2, total_pages - 1, total_pages]
    else:
        # Show first page + ellipsis + current-1, current, current+1 + ellipsis + last page
        return [1, "...", current_page - 1, current_page, current_page + 1, "...", total_pages]


@register.filter
def get_dandiset_number(dandi_id):
    """
    Extract the dandiset number from a DANDI ID.
    Example: "DANDI:000001/draft" -> "000001"
    Usage: {{ dandiset.dandi_id|get_dandiset_number }}
    """
    if not dandi_id:
        return None
    
    # Handle format: "DANDI:000001/draft" or "DANDI:000001/0.210812.1515"
    if dandi_id.startswith('DANDI:'):
        parts = dandi_id.split('/')
        if len(parts) >= 1:
            # Extract number part after "DANDI:"
            number_part = parts[0][6:]  # Remove "DANDI:" prefix
            return number_part
    
    return None


@register.filter
def get_dandiset_version(dandi_id):
    """
    Extract the version from a DANDI ID.
    Example: "DANDI:000001/draft" -> "draft"
    Example: "DANDI:000001/0.210812.1515" -> "0.210812.1515"
    Usage: {{ dandiset.dandi_id|get_dandiset_version }}
    """
    if not dandi_id:
        return None
    
    # Handle format: "DANDI:000001/draft" or "DANDI:000001/0.210812.1515"
    if '/' in dandi_id:
        parts = dandi_id.split('/')
        if len(parts) >= 2:
            return parts[1]
    
    return None
