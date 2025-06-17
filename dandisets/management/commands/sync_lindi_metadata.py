import json
import time
import requests
from datetime import datetime, timezone
from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from dandisets.models import Asset, LindiMetadata, SyncTracker, Dandiset


class Command(BaseCommand):
    help = 'Sync LINDI metadata for NWB assets from lindi.neurosift.org'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {
            'assets_checked': 0,
            'lindi_processed': 0,
            'lindi_updated': 0,
            'lindi_skipped': 0,
            'dandisets_skipped': 0,
            'errors': 0,
        }
        self.dry_run = False
        self.verbose = False
        self.session = requests.Session()
        # Set a reasonable timeout and user agent
        self.session.headers.update({
            'User-Agent': 'dandi-sql-lindi-sync/1.0'
        })

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force refresh of all LINDI metadata, ignoring existing records',
        )
        parser.add_argument(
            '--dandiset-id',
            type=str,
            help='Process only assets from a specific dandiset (e.g., 000409)',
        )
        parser.add_argument(
            '--asset-id',
            type=str,
            help='Process only a specific asset by its dandi_asset_id',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress and debug information',
        )
        parser.add_argument(
            '--no-progress',
            action='store_true',
            help='Disable progress bars (useful for logging)',
        )
        parser.add_argument(
            '--max-assets',
            type=int,
            default=1000,
            help='Maximum number of assets to process (default: 1000)',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='HTTP timeout in seconds (default: 30)',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        self.no_progress = options['no_progress']
        
        start_time = time.time()
        sync_tracker = None
        
        try:
            # Store timeout for later use
            self.timeout = options['timeout']
            
            if self.dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            else:
                # Create sync tracker with 'running' status
                sync_tracker = SyncTracker.objects.create(
                    sync_type='lindi',
                    status='running',
                    last_sync_timestamp=datetime.now(timezone.utc),
                    lindi_metadata_processed=0,
                    sync_duration_seconds=0.0
                )
            
            # Get NWB assets to process
            assets_queryset = self._get_assets_queryset(options)
            total_assets = assets_queryset.count()
            
            self.stdout.write(f"Found {total_assets} NWB assets to check for LINDI metadata")
            
            if total_assets == 0:
                self.stdout.write("No NWB assets found to process")
                return
            
            # Apply max assets limit
            max_assets = options.get('max_assets', 1000)
            if total_assets > max_assets:
                self.stdout.write(f"Limiting to {max_assets} assets (total: {total_assets})")
                assets_queryset = assets_queryset[:max_assets]
            
            # Process assets
            self._process_assets(assets_queryset, options, sync_tracker)
            
            # Record sync completion
            end_time = time.time()
            duration = end_time - start_time
            
            if not self.dry_run and sync_tracker:
                self._record_sync_completion(sync_tracker, duration)
            
            # Print summary
            self._print_summary(duration)
            
        except Exception as e:
            # Record failure if sync tracker exists
            if not self.dry_run and sync_tracker:
                end_time = time.time()
                duration = end_time - start_time
                self._record_sync_failure(sync_tracker, duration, str(e))
            
            self.stdout.write(
                self.style.ERROR(f'Error during LINDI sync: {str(e)}')
            )
            if self.verbose:
                import traceback
                self.stdout.write(traceback.format_exc())
            raise
        finally:
            self.session.close()

    def _get_assets_queryset(self, options):
        """Get the queryset of NWB assets to process"""
        # Start with all NWB assets
        queryset = Asset.objects.filter(encoding_format='application/x-nwb')
        
        # Filter by dandiset if specified
        if options['dandiset_id']:
            dandiset_id = options['dandiset_id']
            # Handle both DANDI:000409 and 000409 formats
            if not dandiset_id.startswith('DANDI:'):
                dandiset_id = f"DANDI:{dandiset_id.zfill(6)}"
            
            queryset = queryset.filter(dandisets__base_id=dandiset_id)
        
        # Filter by specific asset if specified
        if options['asset_id']:
            queryset = queryset.filter(dandi_asset_id=options['asset_id'])
        
        # Skip assets that already have LINDI metadata unless force refresh
        if not options['force_refresh']:
            queryset = queryset.filter(lindi_metadata__isnull=True)
        
        # Filter out assets from dandisets that haven't been updated since last LINDI sync
        # (unless force refresh or specific asset/dandiset specified)
        if not options['force_refresh'] and not options['asset_id'] and not options['dandiset_id']:
            updated_dandisets = self._get_updated_dandisets_since_last_sync()
            if updated_dandisets is not None:
                queryset = queryset.filter(dandisets__base_id__in=updated_dandisets)
        
        return queryset.select_related().prefetch_related('dandisets')

    def _get_updated_dandisets_since_last_sync(self):
        """Get list of dandiset base_ids that have been updated since the last LINDI sync"""
        try:
            # Get the last successful LINDI sync
            last_sync = SyncTracker.objects.filter(
                sync_type='lindi',
                status='completed'
            ).order_by('-last_sync_timestamp').first()
            
            if not last_sync:
                if self.verbose:
                    self.stdout.write("No previous LINDI sync found - processing all dandisets")
                return None  # No previous sync, process all
            
            last_sync_time = last_sync.last_sync_timestamp
            if self.verbose:
                self.stdout.write(f"Last LINDI sync was at: {last_sync_time}")
            
            # Find dandisets modified since the last sync
            updated_dandisets = list(
                Dandiset.objects.filter(
                    date_modified__gt=last_sync_time,
                    is_latest=True  # Only check latest versions
                ).values_list('base_id', flat=True).distinct()
            )
            
            if self.verbose:
                if updated_dandisets:
                    self.stdout.write(f"Found {len(updated_dandisets)} dandisets updated since last sync:")
                    for dandiset_id in updated_dandisets[:10]:  # Show first 10
                        self.stdout.write(f"  - {dandiset_id}")
                    if len(updated_dandisets) > 10:
                        self.stdout.write(f"  ... and {len(updated_dandisets) - 10} more")
                else:
                    self.stdout.write("No dandisets have been updated since last sync")
            
            return updated_dandisets
            
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error checking for updated dandisets: {e}")
            return None  # On error, process all to be safe

    def _process_assets(self, assets_queryset, options, sync_tracker=None):
        """Process the assets for LINDI metadata"""
        
        process_desc = "Processing NWB assets for LINDI metadata"
        if self.no_progress:
            for asset in assets_queryset:
                self._process_single_asset(asset, sync_tracker)
                self.stats['assets_checked'] += 1
        else:
            with tqdm(assets_queryset, desc=process_desc, unit="asset") as pbar:
                for asset in pbar:
                    # Get dandiset info for display
                    dandiset_info = "no-dandiset"
                    if asset.dandisets.exists():
                        dandiset_info = asset.dandisets.first().base_id.replace('DANDI:', '')
                    
                    pbar.set_postfix(
                        dandiset=dandiset_info,
                        processed=self.stats['lindi_processed'],
                        errors=self.stats['errors']
                    )
                    
                    self._process_single_asset(asset, sync_tracker)
                    self.stats['assets_checked'] += 1

    def _process_single_asset(self, asset, sync_tracker=None):
        """Process a single asset for LINDI metadata"""
        try:
            # Construct LINDI URL
            lindi_url = self._construct_lindi_url(asset)
            if not lindi_url:
                if self.verbose:
                    self.stdout.write(f"Could not construct LINDI URL for asset {asset.dandi_asset_id}")
                self.stats['lindi_skipped'] += 1
                return
            
            # Check if we should process this asset
            should_process = True
            if hasattr(asset, 'lindi_metadata') and asset.lindi_metadata:
                if self.verbose:
                    self.stdout.write(f"Asset {asset.dandi_asset_id} already has LINDI metadata")
                self.stats['lindi_skipped'] += 1
                should_process = False
            
            if not should_process:
                return
            
            if self.dry_run:
                if self.verbose:
                    self.stdout.write(f"Would process LINDI for asset: {asset.path}")
                    self.stdout.write(f"  URL: {lindi_url}")
                self.stats['lindi_processed'] += 1
                return
            
            # Download and process LINDI file
            lindi_data = self._download_lindi_file(lindi_url)
            if not lindi_data:
                self.stats['errors'] += 1
                return
            
            # Filter LINDI data
            filtered_data = self._filter_lindi_data(lindi_data)
            
            # Save to database
            self._save_lindi_metadata(asset, lindi_url, lindi_data, filtered_data, sync_tracker)
            self.stats['lindi_processed'] += 1
            
            if self.verbose:
                self.stdout.write(f"Processed LINDI metadata for: {asset.path}")
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing asset {asset.dandi_asset_id}: {e}")

    def _construct_lindi_url(self, asset):
        """Construct the LINDI URL for an asset"""
        try:
            # Get dandiset ID
            if not asset.dandisets.exists():
                return None
            
            dandiset = asset.dandisets.first()
            dandiset_id = dandiset.base_id.replace('DANDI:', '').zfill(6)
            
            # Use draft version for URL construction
            # Pattern: https://lindi.neurosift.org/dandi/dandisets/{dandiset_id}/assets/{asset_id}/nwb.lindi.json
            lindi_url = f"https://lindi.neurosift.org/dandi/dandisets/{dandiset_id}/assets/{asset.dandi_asset_id}/nwb.lindi.json"
            
            return lindi_url
            
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error constructing LINDI URL for {asset.dandi_asset_id}: {e}")
            return None

    def _download_lindi_file(self, lindi_url):
        """Download LINDI file from URL"""
        try:
            if self.verbose:
                self.stdout.write(f"Downloading LINDI file: {lindi_url}")
            
            response = self.session.get(lindi_url, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.Timeout:
            if self.verbose:
                self.stdout.write(f"Timeout downloading LINDI file: {lindi_url}")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                if self.verbose:
                    self.stdout.write(f"LINDI file not found: {lindi_url}")
            else:
                if self.verbose:
                    self.stdout.write(f"HTTP error downloading LINDI file {lindi_url}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            if self.verbose:
                self.stdout.write(f"Request error downloading LINDI file {lindi_url}: {e}")
            return None
        except json.JSONDecodeError as e:
            if self.verbose:
                self.stdout.write(f"JSON decode error for LINDI file {lindi_url}: {e}")
            return None

    def _filter_lindi_data(self, lindi_data):
        """Filter LINDI data to remove base64-encoded values and large data arrays"""
        try:
            # Extract generation metadata and clean it
            generation_metadata = self._clean_json_data(lindi_data.get('generationMetadata', {}))
            
            # Filter refs data using the provided logic
            refs_data = lindi_data.get('refs', {})
            filtered_refs = {}
            
            for key, val in refs_data.items():
                # Skip base64-encoded values
                if isinstance(val, str) and val.startswith("base64:"):
                    continue
                
                # Skip array data that looks like [chunks, dtype, shape] format
                if isinstance(val, list) and len(val) == 3:
                    continue
                
                # Skip strings with problematic Unicode escape sequences
                if isinstance(val, str) and self._has_problematic_unicode(val):
                    continue
                
                # Clean the value and keep it
                cleaned_val = self._clean_json_data(val)
                filtered_refs[key] = cleaned_val
            
            if self.verbose:
                original_count = len(refs_data)
                filtered_count = len(filtered_refs)
                removed_count = original_count - filtered_count
                self.stdout.write(f"Filtered LINDI refs: kept {filtered_count}, removed {removed_count} entries")
            
            return {
                'generationMetadata': generation_metadata,
                'refs': filtered_refs
            }
            
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error filtering LINDI data: {e}")
            return lindi_data  # Return original data if filtering fails

    def _has_problematic_unicode(self, text):
        """Check if text contains problematic Unicode escape sequences"""
        if not isinstance(text, str):
            return False
        
        # Check for null bytes and other control characters
        problematic_sequences = [
            '\\u0000', '\\u0001', '\\u0002', '\\u0003', '\\u0004', '\\u0005', 
            '\\u0006', '\\u0007', '\\u0008', '\\u000b', '\\u000c', '\\u000e', 
            '\\u000f', '\\u0010', '\\u0011', '\\u0012', '\\u0013', '\\u0014', 
            '\\u0015', '\\u0016', '\\u0017', '\\u0018', '\\u0019', '\\u001a', 
            '\\u001b', '\\u001c', '\\u001d', '\\u001e', '\\u001f'
        ]
        
        return any(seq in text for seq in problematic_sequences)

    def _clean_json_data(self, data):
        """Recursively clean JSON data to remove problematic characters"""
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                # Clean the key
                clean_key = self._clean_string(k) if isinstance(k, str) else k
                # Clean the value recursively
                clean_value = self._clean_json_data(v)
                cleaned[clean_key] = clean_value
            return cleaned
        elif isinstance(data, list):
            return [self._clean_json_data(item) for item in data]
        elif isinstance(data, str):
            return self._clean_string(data)
        else:
            return data

    def _clean_string(self, text):
        """Clean a string by removing or replacing problematic Unicode sequences"""
        if not isinstance(text, str):
            return text
        
        # Replace null bytes and other control characters with empty string
        import re
        # Remove control characters (except normal whitespace: \t, \n, \r)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Also handle Unicode escape sequences in the string itself
        problematic_patterns = [
            r'\\u000[0-9a-fA-F]',  # \u0000 to \u000F
            r'\\u001[0-9a-fA-F]',  # \u0010 to \u001F
        ]
        
        for pattern in problematic_patterns:
            cleaned = re.sub(pattern, '', cleaned)
        
        return cleaned

    def _save_lindi_metadata(self, asset, lindi_url, original_data, filtered_data, sync_tracker=None):
        """Save LINDI metadata to database"""
        try:
            with transaction.atomic():
                # Create or update LindiMetadata record - store complete filtered data structure
                lindi_metadata, created = LindiMetadata.objects.update_or_create(
                    asset=asset,
                    defaults={
                        'structure_metadata': filtered_data,  # Complete filtered structure including generationMetadata
                        'lindi_url': lindi_url,
                        'processing_version': '1.0',
                        'sync_tracker': sync_tracker,
                    }
                )
                
                if created:
                    if self.verbose:
                        self.stdout.write(f"Created new LINDI metadata record for {asset.dandi_asset_id}")
                else:
                    if self.verbose:
                        self.stdout.write(f"Updated existing LINDI metadata record for {asset.dandi_asset_id}")
                
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error saving LINDI metadata for {asset.dandi_asset_id}: {e}")
            raise

    def _record_sync_completion(self, sync_tracker, duration):
        """Record sync completion in database"""
        sync_tracker.status = 'completed'
        sync_tracker.last_sync_timestamp = datetime.now(timezone.utc)
        sync_tracker.assets_synced = self.stats['assets_checked']
        sync_tracker.lindi_metadata_processed = self.stats['lindi_processed']
        sync_tracker.sync_duration_seconds = duration
        sync_tracker.save()

    def _record_sync_failure(self, sync_tracker, duration, error_message):
        """Record sync failure in database"""
        sync_tracker.status = 'failed'
        sync_tracker.last_sync_timestamp = datetime.now(timezone.utc)
        sync_tracker.assets_synced = self.stats['assets_checked']
        sync_tracker.lindi_metadata_processed = self.stats['lindi_processed']
        sync_tracker.sync_duration_seconds = duration
        sync_tracker.error_message = error_message[:1000] if error_message else ''  # Truncate if too long
        sync_tracker.save()

    def _print_summary(self, duration):
        """Print sync summary"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("LINDI METADATA SYNC SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Duration: {duration:.2f} seconds")
        self.stdout.write(f"Assets checked: {self.stats['assets_checked']}")
        self.stdout.write(f"LINDI metadata processed: {self.stats['lindi_processed']}")
        self.stdout.write(f"LINDI metadata skipped: {self.stats['lindi_skipped']}")
        self.stdout.write(f"Errors: {self.stats['errors']}")
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made"))
        else:
            self.stdout.write(self.style.SUCCESS("LINDI metadata sync completed successfully"))
