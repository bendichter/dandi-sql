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
