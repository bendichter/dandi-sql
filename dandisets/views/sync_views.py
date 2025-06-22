import os
import logging
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO
import sys

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class TriggerSyncView(View):
    """
    HTTP endpoint to trigger DANDI sync from external sources like GitHub Actions.
    Requires authorization header for security.
    """
    
    def post(self, request):
        # Check authorization
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('SYNC_API_TOKEN')
        
        if not expected_token:
            return JsonResponse({
                'error': 'Sync API not configured on server'
            }, status=500)
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            return JsonResponse({
                'error': 'Unauthorized'
            }, status=401)
        
        # Parse request parameters from multiple sources
        try:
            # Try to parse JSON body first
            if request.content_type == 'application/json' and request.body:
                json_data = json.loads(request.body)
                force_full = json_data.get('force_full', False)
                dandiset_id = json_data.get('dandiset_id')
            else:
                # Fall back to POST data or GET parameters
                force_full = request.POST.get('force_full', request.GET.get('force_full', 'false'))
                dandiset_id = request.POST.get('dandiset_id', request.GET.get('dandiset_id'))
        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, use POST/GET parameters
            force_full = request.POST.get('force_full', request.GET.get('force_full', 'false'))
            dandiset_id = request.POST.get('dandiset_id', request.GET.get('dandiset_id'))
        
        # Convert force_full to boolean
        if isinstance(force_full, str):
            force_full = force_full.lower() == 'true'
        
        logger.info(f"DANDI sync triggered - force_full: {force_full}, dandiset_id: {dandiset_id}")
        
        try:
            # Capture command output
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            command_failed = False
            exception_message = None
            
            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture
                
                # Build command arguments
                args = ['sync_dandi_incremental', '--no-progress', '--verbose']
                if force_full:
                    args.append('--force-full-sync')
                if dandiset_id:
                    args.extend(['--dandiset-id', dandiset_id])
                
                logger.info(f"Running command: {' '.join(args)}")
                
                # Run the sync command
                call_command(*args)
                
            except CommandError as e:
                command_failed = True
                exception_message = str(e)
                logger.error(f"Django command failed: {e}")
            except Exception as e:
                command_failed = True
                exception_message = str(e)
                logger.error(f"Unexpected error during sync: {e}")
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            output = stdout_capture.getvalue()
            error_output = stderr_capture.getvalue()
            
            if command_failed:
                logger.error(f"DANDI sync failed: {exception_message}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'DANDI sync failed: {exception_message}',
                    'force_full_sync': force_full,
                    'dandiset_id': dandiset_id,
                    'output': output,
                    'errors': error_output
                }, status=500)
            else:
                logger.info(f"DANDI sync completed successfully. Force full: {force_full}, dandiset: {dandiset_id}")
                return JsonResponse({
                    'status': 'success',
                    'message': 'DANDI sync completed successfully',
                    'force_full_sync': force_full,
                    'dandiset_id': dandiset_id,
                    'output': output,
                    'errors': error_output if error_output else None
                })
            
        except Exception as e:
            logger.error(f"DANDI sync failed with unexpected error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'DANDI sync failed: {str(e)}',
                'force_full_sync': force_full,
                'dandiset_id': dandiset_id
            }, status=500)
    
    def get(self, request):
        """Health check endpoint"""
        return JsonResponse({
            'status': 'ready',
            'message': 'DANDI sync endpoint is available',
            'authenticated': bool(request.headers.get('Authorization')),
            'has_token_configured': bool(os.environ.get('SYNC_API_TOKEN'))
        })

# Function-based view for simpler URL routing
@csrf_exempt
@require_http_methods(["GET", "POST"])
def trigger_sync(request):
    """Function-based wrapper for the sync trigger"""
    view = TriggerSyncView()
    if request.method == 'POST':
        return view.post(request)
    else:
        return view.get(request)
