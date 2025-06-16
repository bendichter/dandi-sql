"""
API views for the JSON Query Builder.

Provides REST endpoints for executing complex queries, validating queries,
and getting schema information.
"""

import json
import logging
from typing import Dict, Any
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.core.serializers import serialize
from django.forms.models import model_to_dict

from ..query import QueryExecutor
from ..query.schema import QuerySchema
from ..query.exceptions import QueryValidationError, QueryExecutionError

logger = logging.getLogger(__name__)


def serialize_query_results(results, model_name):
    """
    Serialize query results to JSON-compatible format.
    
    Args:
        results: List of model instances or dictionaries (from values())
        model_name: Name of the model
        
    Returns:
        List of serialized objects
    """
    serialized_results = []
    
    for obj in results:
        try:
            # Check if obj is already a dictionary (from values() queryset)
            if isinstance(obj, dict):
                obj_dict = obj.copy()
                
                # Handle special field types in dictionary values
                for key, value in obj_dict.items():
                    # Convert datetime objects to ISO strings
                    if hasattr(value, 'isoformat'):
                        obj_dict[key] = value.isoformat()
                    # Convert UUID objects to strings
                    elif hasattr(value, 'hex'):
                        obj_dict[key] = str(value)
                
                serialized_results.append(obj_dict)
            else:
                # Handle model instances
                obj_dict = model_to_dict(obj)
                
                # Handle special field types
                for key, value in obj_dict.items():
                    # Convert datetime objects to ISO strings
                    if hasattr(value, 'isoformat'):
                        obj_dict[key] = value.isoformat()
                    # Convert UUID objects to strings
                    elif hasattr(value, 'hex'):
                        obj_dict[key] = str(value)
                
                # Add the primary key if not already included
                if 'id' not in obj_dict and hasattr(obj, 'pk'):
                    obj_dict['id'] = obj.pk
                
                serialized_results.append(obj_dict)
            
        except Exception as e:
            # Fallback serialization
            logger.warning(f"Error serializing object {obj}: {e}")
            try:
                if isinstance(obj, dict):
                    # For dict objects, just convert problematic values to strings
                    safe_dict = {}
                    for key, value in obj.items():
                        try:
                            json.dumps(value)  # Test if value is JSON serializable
                            safe_dict[key] = value
                        except:
                            safe_dict[key] = str(value)
                    serialized_results.append(safe_dict)
                else:
                    # Use Django's built-in serializer as fallback for model instances
                    serialized = serialize('json', [obj])
                    parsed = json.loads(serialized)[0]['fields']
                    parsed['id'] = obj.pk
                    serialized_results.append(parsed)
            except Exception as e2:
                logger.error(f"Failed to serialize object {obj}: {e2}")
                serialized_results.append({'id': getattr(obj, 'pk', None), 'error': 'Serialization failed'})
    
    return serialized_results


@method_decorator(csrf_exempt, name='dispatch')
class QueryAPIView(View):
    """Main API view for executing JSON queries."""
    
    def post(self, request):
        """
        Execute a JSON query.
        
        Expected JSON body:
        {
            "model": "Dandiset",
            "fields": ["id", "name", "description"],
            "filters": {"name__icontains": "mouse"},
            "annotations": {...},
            "order_by": ["name"],
            "limit": 10,
            "offset": 0
        }
        """
        try:
            # Parse JSON body
            try:
                query_json = json.loads(request.body)
            except json.JSONDecodeError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid JSON: {str(e)}',
                    'results': []
                }, status=400)
            
            # Execute the query
            result = QueryExecutor.execute(query_json)
            
            if result['success']:
                # Serialize the results
                serialized_results = serialize_query_results(
                    result['results'], 
                    query_json.get('model', 'Unknown')
                )
                
                response_data = {
                    'success': True,
                    'results': serialized_results,
                    'metadata': result['metadata'],
                    'query': query_json
                }
                
                return JsonResponse(response_data)
            else:
                return JsonResponse({
                    'success': False,
                    'error': result['metadata'].get('error', 'Unknown error'),
                    'results': [],
                    'query': query_json
                }, status=400)
                
        except Exception as e:
            logger.error(f"Query API error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Internal server error: {str(e)}',
                'results': []
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class QueryValidateAPIView(View):
    """API view for validating queries without executing them."""
    
    def post(self, request):
        """
        Validate a JSON query.
        
        Returns validation results without executing the query.
        """
        try:
            # Parse JSON body
            try:
                query_json = json.loads(request.body)
            except json.JSONDecodeError as e:
                return JsonResponse({
                    'valid': False,
                    'error': f'Invalid JSON: {str(e)}'
                }, status=400)
            
            # Validate the query
            validation_result = QueryExecutor.validate_query(query_json)
            
            return JsonResponse(validation_result)
            
        except Exception as e:
            logger.error(f"Query validation error: {str(e)}")
            return JsonResponse({
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class QueryExplainAPIView(View):
    """API view for getting query execution plans."""
    
    def post(self, request):
        """
        Get the execution plan for a query.
        
        Returns SQL and execution plan information without running the query.
        """
        try:
            # Parse JSON body
            try:
                query_json = json.loads(request.body)
            except json.JSONDecodeError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid JSON: {str(e)}'
                }, status=400)
            
            # Get query plan
            plan_result = QueryExecutor.get_query_plan(query_json)
            
            return JsonResponse(plan_result)
            
        except Exception as e:
            logger.error(f"Query explain error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Explain error: {str(e)}'
            }, status=500)


class QuerySchemaAPIView(View):
    """API view for getting schema information."""
    
    def get(self, request):
        """
        Get schema information for the query builder.
        
        Query parameters:
        - model: Get schema for a specific model
        - field: Get field suggestions for a model
        """
        try:
            schema = QuerySchema()
            
            # Check if requesting specific model info
            model_name = request.GET.get('model')
            if model_name:
                models_info = schema.get_models_info()
                if model_name in models_info:
                    return JsonResponse({
                        'model': model_name,
                        'info': models_info[model_name],
                        'operations': schema.get_operations_info(),
                        'aggregations': schema.get_aggregations_info()
                    })
                else:
                    return JsonResponse({
                        'error': f'Model "{model_name}" not found',
                        'available_models': list(models_info.keys())
                    }, status=404)
            
            # Check if requesting field suggestions
            field_partial = request.GET.get('field')
            if field_partial and model_name:
                suggestions = schema.get_field_suggestions(model_name, field_partial)
                return JsonResponse({
                    'model': model_name,
                    'field_partial': field_partial,
                    'suggestions': suggestions
                })
            
            # Return full schema
            full_schema = schema.get_full_schema()
            return JsonResponse(full_schema)
            
        except Exception as e:
            logger.error(f"Schema API error: {str(e)}")
            return JsonResponse({
                'error': f'Schema error: {str(e)}'
            }, status=500)


class QueryExamplesAPIView(View):
    """API view for getting example queries."""
    
    def get(self, request):
        """Get example queries for common use cases."""
        try:
            schema = QuerySchema()
            examples = schema.get_example_queries()
            
            # Filter by model if requested
            model_filter = request.GET.get('model')
            if model_filter:
                examples = [
                    example for example in examples 
                    if example['query'].get('model') == model_filter
                ]
            
            return JsonResponse({
                'examples': examples,
                'total_count': len(examples),
                'model_filter': model_filter
            })
            
        except Exception as e:
            logger.error(f"Examples API error: {str(e)}")
            return JsonResponse({
                'error': f'Examples error: {str(e)}'
            }, status=500)


# Function-based view alternatives for simpler routing
@csrf_exempt
@require_http_methods(["POST"])
def query_execute(request):
    """Function-based view for executing queries."""
    view = QueryAPIView()
    return view.post(request)


@csrf_exempt
@require_http_methods(["POST"])
def query_validate(request):
    """Function-based view for validating queries."""
    view = QueryValidateAPIView()
    return view.post(request)


@csrf_exempt
@require_http_methods(["POST"])
def query_explain(request):
    """Function-based view for explaining queries."""
    view = QueryExplainAPIView()
    return view.post(request)


@require_http_methods(["GET"])
def query_schema(request):
    """Function-based view for getting schema information."""
    view = QuerySchemaAPIView()
    return view.get(request)


@require_http_methods(["GET"])
def query_examples(request):
    """Function-based view for getting example queries."""
    view = QueryExamplesAPIView()
    return view.get(request)
