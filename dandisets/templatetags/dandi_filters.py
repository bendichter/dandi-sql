from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Split a string by a delimiter"""
    if value:
        return value.split(arg)
    return []

@register.filter
def get_dandiset_number(dandi_id):
    """Extract dandiset number from DANDI ID like 'DANDI:000574/0.250610.0938'"""
    if dandi_id and 'DANDI:' in dandi_id:
        # Remove 'DANDI:' prefix and get the part before '/'
        parts = dandi_id.replace('DANDI:', '').split('/')
        if parts:
            return parts[0]
    return None

@register.filter
def get_dandiset_version(dandi_id):
    """Extract version from DANDI ID like 'DANDI:000574/0.250610.0938'"""
    if dandi_id and '/' in dandi_id:
        parts = dandi_id.split('/')
        if len(parts) >= 2:
            return parts[1]
    return None

@register.filter
def build_asset_api_url(asset, dandiset):
    """Build the DANDI API URL for an asset"""
    if not asset.dandi_asset_id or not dandiset.dandi_id:
        return None
    
    dandiset_number = get_dandiset_number(dandiset.dandi_id)
    dandiset_version = get_dandiset_version(dandiset.dandi_id)
    
    if dandiset_number and dandiset_version:
        return f"https://api.dandiarchive.org/api/dandisets/{dandiset_number}/versions/{dandiset_version}/assets/{asset.dandi_asset_id}/"
    
    return None
