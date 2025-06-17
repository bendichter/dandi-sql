import os
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.management import call_command
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
        
        # Parse request parameters
        force_full = request.GET.get('force_full', 'false').lower() == 'true'
        
        try:
            # Capture command output
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture
                
                # Build command arguments
                args = ['sync_dandi_incremental', '--no-progress', '--verbose']
                if force_full:
                    args.append('--force-full-sync')
                
                # Run the sync command
                call_command(*args)
                
                success = True
                output = stdout_capture.getvalue()
                error_output = stderr_capture.getvalue()
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            logger.info(f"DANDI sync completed successfully. Force full: {force_full}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'DANDI sync completed successfully',
                'force_full_sync': force_full,
                'output': output,
                'errors': error_output if error_output else None
            })
            
        except Exception as e:
            logger.error(f"DANDI sync failed: {str(e)}")
            
            return JsonResponse({
                'status': 'error',
                'message': f'DANDI sync failed: {str(e)}',
                'force_full_sync': force_full
            }, status=500)
    
    def get(self, request):
        """Health check endpoint"""
        return JsonResponse({
            'status': 'ready',
            'message': 'DANDI sync endpoint is available',
            'authenticated': bool(request.headers.get('Authorization'))
        })

# Function-based view for simpler URL routing
@csrf_exempt
@require_http_methods(["GET", "POST"])
def trigger_sync(request):
    """Function-based wrapper for the sync trigger"""
    view = TriggerSyncView()
    return view.dispatch(request)
