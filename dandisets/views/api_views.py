from django.http import JsonResponse
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
