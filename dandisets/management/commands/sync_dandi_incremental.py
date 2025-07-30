import json
import re
import time
import requests
import tempfile
import subprocess
import yaml
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils import timezone as django_timezone
from django.db import transaction, connections
from django.db.models import Q
from tqdm import tqdm
from dandi.dandiapi import DandiAPIClient
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from dandisets.models import (
    Dandiset, Contributor, SpeciesType, ApproachType, 
    MeasurementTechniqueType, StandardsType, AssetsSummary,
    ContactPoint, AccessRequirements, Activity, Resource,
    Anatomy, GenericType, Disorder, DandisetContributor,
    DandisetAccessRequirements, DandisetRelatedResource,
    AssetsSummarySpecies, AssetsSummaryApproach, AssetsSummaryDataStandard,
    AssetsSummaryMeasurementTechnique, Affiliation, ContributorAffiliation,
    Software, Asset, Participant, SexType, AssetDandiset, SyncTracker, LindiMetadata
)


class Command(BaseCommand):
    help = 'Incrementally sync DANDI metadata - only updates changed dandisets and assets'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = DandiAPIClient()
        self.stats = {
            'dandisets_checked': 0,
            'dandisets_updated': 0,
            'dandisets_skipped': 0,
            'dandisets_deleted': 0,
            'assets_checked': 0,
            'assets_updated': 0,
            'assets_skipped': 0,
            'assets_deleted': 0,
            'lindi_processed': 0,
            'lindi_skipped': 0,
            'lindi_errors': 0,
            'errors': 0,
            'cache_hits': 0,
            'cache_misses': 0,
        }
        self.dry_run = False
        self.verbose = False
        self.session = requests.Session()
        # Set a reasonable timeout and user agent for LINDI requests
        self.session.headers.update({
            'User-Agent': 'dandi-sql-unified-sync/1.0'
        })
        # Cache for API dandisets to avoid multiple expensive API calls
        self._api_dandisets_cache = None
        self._api_dandisets_dict_cache = None
        
        # Set up YAML file caching
        self.cache_dir = Path.home() / '.cache' / 'dandi-sql' / 'yaml-cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)

    def download_yaml_from_s3(self, dandiset_id, filename):
        """Download YAML file from S3 using AWS CLI with caching"""
        # Normalize dandiset ID (remove DANDI: prefix and ensure 6 digits)
        normalized_id = self._normalize_dandiset_id(dandiset_id)
        
        # Generate cache key
        cache_key = f"{normalized_id}_{filename}"
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        cache_file = self.cache_dir / f"{cache_hash}.yaml"
        
        # Check if cached file exists and is not expired
        if cache_file.exists():
            try:
                file_age = time.time() - cache_file.stat().st_mtime
                if file_age < self.cache_ttl:
                    # Load from cache
                    with open(cache_file, 'r') as f:
                        yaml_content = yaml.safe_load(f)
                    
                    self.stats['cache_hits'] += 1
                    if self.verbose:
                        self.stdout.write(f"Loaded {filename} for dandiset {normalized_id} from cache")
                    return yaml_content
                else:
                    # Cache expired, remove old file
                    cache_file.unlink()
                    if self.verbose:
                        self.stdout.write(f"Cache expired for {filename} for dandiset {normalized_id}")
            except Exception as e:
                if self.verbose:
                    self.stdout.write(f"Error reading cache for {filename}: {e}")
                # Remove corrupted cache file
                cache_file.unlink(missing_ok=True)
        
        # Download from S3
        s3_url = f"s3://dandiarchive/dandisets/{normalized_id}/draft/{filename}"
        self.stats['cache_misses'] += 1
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.yaml', delete=False) as temp_file:
            try:
                # Use AWS CLI to download the file
                result = subprocess.run([
                    'aws', 's3', 'cp', 
                    '--no-sign-request',
                    s3_url,
                    temp_file.name
                ], capture_output=True, text=True, check=True)
                
                # Read and parse the YAML content
                with open(temp_file.name, 'r') as f:
                    yaml_content = yaml.safe_load(f)
                
                # Save to cache
                try:
                    with open(cache_file, 'w') as f:
                        yaml.dump(yaml_content, f)
                    if self.verbose:
                        self.stdout.write(f"Cached {filename} for dandiset {normalized_id}")
                except Exception as e:
                    if self.verbose:
                        self.stdout.write(f"Failed to cache {filename}: {e}")
                
                if self.verbose:
                    self.stdout.write(f"Successfully downloaded {filename} for dandiset {normalized_id}")
                
                return yaml_content
                
            except subprocess.CalledProcessError as e:
                if self.verbose:
                    self.stdout.write(f"Failed to download {filename} for dandiset {normalized_id}: {e.stderr}")
                return None
            except yaml.YAMLError as e:
                if self.verbose:
                    self.stdout.write(f"Failed to parse YAML content from {filename} for dandiset {normalized_id}: {e}")
                return None
            finally:
                # Clean up temp file
                Path(temp_file.name).unlink(missing_ok=True)

    def normalize_uberon_identifier(self, identifier: Optional[str]) -> Optional[str]:
        """Normalize UBERON identifiers to standard format"""
        if not identifier:
            return identifier
            
        # Convert http://purl.obolibrary.org/obo/UBERON_XXXXXXX to UBERON:XXXXXXX
        match = re.match(r'http://purl\.obolibrary\.org/obo/UBERON_(\d+)', identifier)
        if match:
            return f"UBERON:{match.group(1)}"
            
        # Convert http://purl.obolibrary.org/obo/CHEBI_XXXXXXX to CHEBI:XXXXXXX
        match = re.match(r'http://purl\.obolibrary\.org/obo/CHEBI_(\d+)', identifier)
        if match:
            return f"CHEBI:{match.group(1)}"
            
        return identifier

    def _parse_datetime_with_timezone(self, datetime_str):
        """Parse datetime string and ensure it's timezone-aware"""
        if not datetime_str:
            return None
        
        parsed_dt = parse_datetime(datetime_str)
        if not parsed_dt:
            return None
        
        # If the datetime is naive (no timezone info), assume UTC
        if django_timezone.is_naive(parsed_dt):
            parsed_dt = django_timezone.make_aware(parsed_dt, timezone.utc)
        
        return parsed_dt

    def _normalize_dandiset_id(self, dandiset_id: Optional[str]) -> Optional[str]:
        """Normalize dandiset ID to standard 6-digit format"""
        if not dandiset_id:
            return dandiset_id
        
        # Remove DANDI: prefix if present
        if dandiset_id.startswith('DANDI:'):
            dandiset_id = dandiset_id[6:]
        
        # Pad with zeros if needed (e.g., 3 -> 000003)
        return dandiset_id.zfill(6)

    def _get_api_dandisets(self):
        """Get all dandisets from API with caching to avoid multiple expensive calls"""
        if self._api_dandisets_cache is None:
            if self.verbose:
                self.stdout.write("Fetching all dandisets from DANDI API (cached for this sync)...")
            self._api_dandisets_cache = list(self.client.get_dandisets())
        return self._api_dandisets_cache

    def _get_api_dandisets_dict(self):
        """Get API dandisets as a dictionary keyed by identifier for fast lookup"""
        if self._api_dandisets_dict_cache is None:
            api_dandisets = self._get_api_dandisets()
            self._api_dandisets_dict_cache = {ds.identifier: ds for ds in api_dandisets}
        return self._api_dandisets_dict_cache

    def _process_with_progress(self, items, process_func, description, unit="item", postfix_func=None, leave=True):
        """Generic function to process items with optional progress bar
        
        Args:
            items: Iterable of items to process
            process_func: Function to call for each item
            description: Description for progress bar
            unit: Unit name for progress bar
            postfix_func: Optional function that takes an item and returns dict for postfix display
            leave: Whether to leave progress bar after completion
        """
        if self.no_progress:
            for item in items:
                process_func(item)
        else:
            with tqdm(items, desc=description, unit=unit, leave=leave) as pbar:
                for item in pbar:
                    if postfix_func:
                        pbar.set_postfix(**postfix_func(item))
                    process_func(item)

    def _truncate_path(self, path, max_length=30):
        """Truncate a file path for display"""
        if not path:
            return 'unknown'
        return path[:max_length] + '...' if len(path) > max_length else path

    def _asset_has_lindi_metadata(self, asset):
        """Check if an asset already has LINDI metadata"""
        try:
            LindiMetadata.objects.get(asset=asset)
            return True
        except LindiMetadata.DoesNotExist:
            return False

    def _should_process_lindi_for_asset(self, asset, force_refresh=False):
        """Determine if an asset should have its LINDI metadata processed
        
        Args:
            asset: The asset to check
            force_refresh: If True, always process regardless of existing metadata
            
        Returns:
            bool: True if asset should be processed, False otherwise
        """
        if force_refresh:
            return True
        
        try:
            LindiMetadata.objects.get(asset=asset)
            return False  # Asset already has LINDI metadata
        except LindiMetadata.DoesNotExist:
            return True  # Asset needs LINDI metadata

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--force-full-sync',
            action='store_true',
            help='Force full sync, ignoring last sync timestamp',
        )
        parser.add_argument(
            '--dandiset-id',
            type=str,
            help='Sync only a specific dandiset (e.g., DANDI:000003)',
        )
        parser.add_argument(
            '--since',
            type=str,
            help='Sync dandisets modified since this date (YYYY-MM-DD or ISO format)',
        )
        parser.add_argument(
            '--assets-only',
            action='store_true',
            help='Only sync assets, skip dandiset metadata updates',
        )
        parser.add_argument(
            '--dandisets-only',
            action='store_true',
            help='Only sync dandiset metadata, skip assets',
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
            default=2000,
            help='Maximum number of assets to process per dandiset (default: 2000)',
        )
        parser.add_argument(
            '--skip-lindi',
            action='store_true',
            help='Skip LINDI metadata syncing for NWB assets',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='HTTP timeout for LINDI requests in seconds (default: 30)',
        )
        parser.add_argument(
            '--lindi-only',
            action='store_true',
            help='Only sync LINDI metadata for existing NWB assets (skip DANDI API sync)',
        )
        parser.add_argument(
            '--force-lindi-refresh',
            action='store_true',
            help='Force refresh of LINDI metadata even if it already exists',
        )
        parser.add_argument(
            '--dandiset-filter',
            type=str,
            help='Filter assets by dandiset ID for LINDI-only sync (e.g., 000003)',
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=4,
            help='Maximum number of parallel workers for I/O operations (default: 4)',
        )
        parser.add_argument(
            '--disable-parallel',
            action='store_true',
            help='Disable parallel processing (use single-threaded mode)',
        )
        parser.add_argument(
            '--skip-deletions',
            action='store_true',
            help='Skip detecting and deleting dandisets that no longer exist in DANDI',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        self.no_progress = options['no_progress']
        self.options = options  # Store options for later use
        self.timeout = options.get('timeout', 30)
        
        start_time = time.time()
        sync_tracker = None
        
        try:
            # Initialize DANDI client
            if not self.no_progress:
                self.stdout.write("Initializing DANDI client...")
            
            # Determine sync scope and last sync time
            sync_scope = self._determine_sync_scope(options)
            last_sync_time = self._get_last_sync_time(options)
            
            if last_sync_time:
                self.stdout.write(f"Last sync: {last_sync_time}")
            else:
                self.stdout.write("No previous sync found - performing full sync")
            
            if self.dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            else:
                # Create sync tracker with 'running' status
                sync_tracker = SyncTracker.objects.create(
                    sync_type=sync_scope,
                    status='running',
                    last_sync_timestamp=datetime.now(timezone.utc),
                    dandisets_synced=0,
                    assets_synced=0,
                    dandisets_updated=0,
                    assets_updated=0,
                    sync_duration_seconds=0.0
                )
            
            # Check if this is a LINDI-only sync
            if options.get('lindi_only'):
                # Only sync LINDI metadata for existing NWB assets
                self._sync_lindi_metadata_only(options, sync_tracker)
            else:
                # Perform unified sync - iterate through dandisets and handle both metadata and assets
                self._sync_dandisets_and_assets(last_sync_time, options, sync_scope, sync_tracker)
                
                # Check for deleted dandisets unless skipped or processing specific dandiset
                if not options.get('skip_deletions', False) and not options.get('dandiset_id'):
                    self._check_for_deleted_dandisets(options, sync_tracker)
            
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
                self.style.ERROR(f'Error during sync: {str(e)}')
            )
            if self.verbose:
                import traceback
                self.stdout.write(traceback.format_exc())
            raise

    def _determine_sync_scope(self, options):
        """Determine what to sync based on options"""
        if options['assets_only']:
            return 'assets'
        elif options['dandisets_only']:
            return 'dandisets'
        else:
            return 'full'

    def _get_last_sync_time(self, options):
        """Get the last sync timestamp - only consider syncs that covered the current scope"""
        if options['force_full_sync']:
            return None
        
        if options['since']:
            # Parse user-provided date
            try:
                return parse_datetime(options['since'])
            except:
                try:
                    # Try parsing as date only
                    date_only = datetime.strptime(options['since'], '%Y-%m-%d')
                    return date_only.replace(tzinfo=timezone.utc)
                except:
                    raise ValueError(f"Invalid date format: {options['since']}")
        
        # Determine what we're trying to sync
        current_scope = self._determine_sync_scope(options)
        
        # Get last sync from database - only consider syncs that covered our current scope
        try:
            if current_scope == 'assets':
                # For assets-only sync, look for previous full or assets syncs
                last_sync = SyncTracker.objects.filter(
                    sync_type__in=['full', 'assets'],
                    status='completed'
                ).latest()
            elif current_scope == 'dandisets':
                # For dandisets-only sync, look for previous full or dandisets syncs
                last_sync = SyncTracker.objects.filter(
                    sync_type__in=['full', 'dandisets'],
                    status='completed'
                ).latest()
            else:
                # For full sync, look for any previous completed sync
                last_sync = SyncTracker.objects.filter(
                    status='completed'
                ).latest()
            
            return last_sync.last_sync_timestamp
        except SyncTracker.DoesNotExist:
            return None

    def _sync_dandisets_and_assets(self, last_sync_time, options, sync_scope, sync_tracker=None):
        """Unified sync method using REST API for change detection and AWS S3 for efficient metadata loading"""
        self.stdout.write("Starting sync using REST API for change detection and AWS S3 for metadata...")
        
        # Get dandisets from API to determine which need updating
        if options['dandiset_id']:
            # Sync specific dandiset - use direct API call
            dandiset_id = options['dandiset_id']
            # Remove DANDI: prefix if present
            if dandiset_id.startswith('DANDI:'):
                dandiset_id = dandiset_id[6:]
            
            try:
                api_dandiset = self.client.get_dandiset(dandiset_id)
                api_dandisets = [api_dandiset]
                if self.verbose:
                    self.stdout.write(f"Found specific dandiset: {api_dandiset.identifier}")
            except Exception as e:
                self.stdout.write(f"Error getting dandiset {dandiset_id}: {e}")
                return
        else:
            api_dandisets = list(self.client.get_dandisets())
        
        # Filter dandisets that need updating using REST API modification dates
        dandisets_to_process = []
        
        def check_dandiset(api_dandiset):
            if self._dandiset_needs_update(api_dandiset, last_sync_time):
                dandisets_to_process.append(api_dandiset)
            self.stats['dandisets_checked'] += 1
        
        self._process_with_progress(
            api_dandisets,
            check_dandiset,
            "Checking dandisets for updates via REST API",
            unit="dandiset",
            postfix_func=lambda ds: {"current": ds.identifier}
        )
        
        self.stdout.write(f"Found {len(dandisets_to_process)} dandisets to process")
        
        if not dandisets_to_process:
            self.stdout.write("No dandisets need updates")
            return
        
        # Process each dandiset using AWS S3 for metadata download
        self._process_with_progress(
            dandisets_to_process,
            lambda ds: self._process_dandiset_and_assets_from_yaml(ds, last_sync_time, options, sync_scope, sync_tracker),
            "Processing dandisets and assets using AWS S3",
            unit="dandiset",
            postfix_func=lambda ds: {"current": ds.identifier}
        )

    def _process_dandiset_and_assets_from_yaml(self, api_dandiset, last_sync_time, options, sync_scope, sync_tracker=None):
        """Process a single dandiset using YAML metadata from S3 instead of REST API metadata"""
        try:
            dandiset = None
            # Extract dandiset ID for S3 access
            dandiset_id = api_dandiset.identifier
            if dandiset_id.startswith('DANDI:'):
                dandiset_id = dandiset_id[6:]
            
            # Skip dandiset 000026
            if dandiset_id == '000026':
                if self.verbose:
                    self.stdout.write(f"Skipping dandiset 000026 as requested")
                return
            
            # Step 1: Update dandiset metadata using YAML from S3 (if not assets-only)
            if sync_scope in ['full', 'dandisets']:
                if self.dry_run:
                    if self.verbose:
                        self.stdout.write(f"Would update dandiset: {api_dandiset.identifier}")
                    self.stats['dandisets_updated'] += 1
                else:
                    # Download dandiset YAML metadata from S3
                    dandiset_data = self.download_yaml_from_s3(dandiset_id, 'dandiset.yaml')
                    if dandiset_data:
                        with transaction.atomic():
                            dandiset = self._load_dandiset(dandiset_data, sync_tracker)
                            self.stats['dandisets_updated'] += 1
                            if self.verbose:
                                self.stdout.write(f"Updated dandiset: {api_dandiset.identifier}")
                    else:
                        if self.verbose:
                            self.stdout.write(f"Could not download dandiset YAML for {api_dandiset.identifier}")
                        return
            
            # Step 2: Process assets using YAML from S3 (if not dandisets-only)
            if sync_scope in ['full', 'assets'] and not options['dandisets_only']:
                # Get local dandiset for asset relationships
                if not dandiset:
                    try:
                        # Try to find existing dandiset by base_id
                        normalized_id = self._normalize_dandiset_id(dandiset_id)
                        dandiset = Dandiset.objects.get(base_id__endswith=normalized_id)
                    except Dandiset.DoesNotExist:
                        if self.verbose:
                            self.stdout.write(f"Local dandiset not found for {api_dandiset.identifier}, skipping assets")
                        return
                
                self._process_assets_for_dandiset_from_yaml(dandiset_id, dandiset, last_sync_time, options, sync_tracker)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing dandiset {api_dandiset.identifier}: {e}")

    def _process_dandiset_and_assets(self, api_dandiset, last_sync_time, options, sync_scope, sync_tracker=None):
        """Process a single dandiset: update metadata and then process its assets"""
        try:
            dandiset = None
            
            # Step 1: Update dandiset metadata (if not assets-only)
            if sync_scope in ['full', 'dandisets']:
                if self.dry_run:
                    if self.verbose:
                        self.stdout.write(f"Would update dandiset: {api_dandiset.identifier}")
                    self.stats['dandisets_updated'] += 1
                else:
                    with transaction.atomic():
                        metadata = api_dandiset.get_raw_metadata()
                        dandiset = self._load_dandiset(metadata, sync_tracker)
                        self.stats['dandisets_updated'] += 1
                        if self.verbose:
                            self.stdout.write(f"Updated dandiset: {api_dandiset.identifier}")
            
            # Step 2: Process assets (if not dandisets-only)
            if sync_scope in ['full', 'assets'] and not options['dandisets_only']:
                # Get local dandiset for asset relationships
                if not dandiset:
                    try:
                        metadata = api_dandiset.get_raw_metadata()
                        dandiset = Dandiset.objects.get(dandi_id=metadata.get('id'))
                    except Dandiset.DoesNotExist:
                        if self.verbose:
                            self.stdout.write(f"Local dandiset not found for {api_dandiset.identifier}, skipping assets")
                        return
                
                self._process_assets_for_dandiset(api_dandiset, dandiset, last_sync_time, options, sync_tracker)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing dandiset {api_dandiset.identifier}: {e}")

    def _process_assets_for_dandiset_from_yaml(self, dandiset_id, local_dandiset, last_sync_time, options, sync_tracker=None):
        """Process assets for a specific dandiset using YAML metadata from S3"""
        try:
            # Download assets YAML metadata from S3
            assets_data = self.download_yaml_from_s3(dandiset_id, 'assets.yaml')
            if not assets_data:
                if self.verbose:
                    self.stdout.write(f"Could not download assets YAML for {dandiset_id}")
                # Even if no YAML assets, check for deleted assets
                self._check_for_deleted_assets_in_dandiset_from_yaml(local_dandiset, [], options)
                return
            
            if not isinstance(assets_data, list):
                if self.verbose:
                    self.stdout.write(f"Invalid assets data format for {dandiset_id} - expected list, got {type(assets_data)}")
                return
            
            if not assets_data:
                if self.verbose:
                    self.stdout.write(f"No assets found for {dandiset_id}")
                # Check for deleted assets
                self._check_for_deleted_assets_in_dandiset_from_yaml(local_dandiset, [], options)
                return
            
            # Apply max assets limit
            max_assets = options.get('max_assets', 2000)
            if len(assets_data) > max_assets:
                if self.verbose:
                    self.stdout.write(f"Limiting assets for {dandiset_id} to {max_assets} (total: {len(assets_data)})")
                assets_data = assets_data[:max_assets]
            
            # Process assets - filter and update in one pass
            assets_updated = 0
            
            def process_asset(asset_data):
                nonlocal assets_updated
                if self._asset_needs_update_from_yaml(asset_data, last_sync_time):
                    self._update_asset_from_yaml(asset_data, local_dandiset, sync_tracker)
                    assets_updated += 1
                self.stats['assets_checked'] += 1
            
            self._process_with_progress(
                assets_data,
                process_asset,
                f"Processing assets for {dandiset_id}",
                unit="asset",
                postfix_func=lambda asset: {"asset": self._truncate_path(asset.get('path', 'unknown'))},
                leave=False
            )
            
            if self.verbose and assets_updated > 0:
                self.stdout.write(f"Updated {assets_updated} assets for {dandiset_id}")
            
            # Check for deleted assets in this dandiset
            self._check_for_deleted_assets_in_dandiset_from_yaml(local_dandiset, assets_data, options)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing assets for {dandiset_id}: {e}")

    def _process_assets_for_dandiset(self, api_dandiset, local_dandiset, last_sync_time, options, sync_tracker=None):
        """Process assets for a specific dandiset"""
        try:
            # Get assets from API
            try:
                api_assets = list(api_dandiset.get_assets())
            except Exception as e:
                if self.verbose:
                    self.stdout.write(f"Error getting assets for {api_dandiset.identifier}: {e}")
                return
            
            if not api_assets:
                if self.verbose:
                    self.stdout.write(f"No assets found for {api_dandiset.identifier}")
                # Even if no API assets, check for deleted assets
                self._check_for_deleted_assets_in_dandiset(local_dandiset, [], options)
                return
            
            # Apply max assets limit
            max_assets = options.get('max_assets', 2000)
            if len(api_assets) > max_assets:
                if self.verbose:
                    self.stdout.write(f"Limiting assets for {api_dandiset.identifier} to {max_assets} (total: {len(api_assets)})")
                api_assets = api_assets[:max_assets]
            
            # Process assets - filter and update in one pass
            assets_updated = 0
            
            def process_asset(asset):
                nonlocal assets_updated
                if self._asset_needs_update(asset, last_sync_time):
                    self._update_asset(asset, local_dandiset, sync_tracker)
                    assets_updated += 1
                self.stats['assets_checked'] += 1
            
            self._process_with_progress(
                api_assets,
                process_asset,
                f"Processing assets for {api_dandiset.identifier}",
                unit="asset",
                postfix_func=lambda asset: {"asset": self._truncate_path(getattr(asset, 'path', 'unknown'))},
                leave=False
            )
            
            if self.verbose and assets_updated > 0:
                self.stdout.write(f"Updated {assets_updated} assets for {api_dandiset.identifier}")
            
            # Check for deleted assets in this dandiset
            self._check_for_deleted_assets_in_dandiset(local_dandiset, api_assets, options)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing assets for {api_dandiset.identifier}: {e}")

    def _sync_dandisets(self, last_sync_time, options):
        """Sync dandiset metadata"""
        self.stdout.write("Fetching dandisets from DANDI API...")
        
        # Get all dandisets (we'll filter later since DANDI API doesn't support date filtering)
        if options['dandiset_id']:
            # Sync specific dandiset
            dandisets = [ds for ds in self.client.get_dandisets() 
                        if ds.identifier == options['dandiset_id']]
            if not dandisets:
                self.stdout.write(f"Dandiset {options['dandiset_id']} not found")
                return
        else:
            dandisets = list(self.client.get_dandisets())
        
        # Filter dandisets that need updating
        dandisets_to_update = []
        
        filter_desc = "Checking dandisets for updates"
        if self.no_progress:
            for dandiset in dandisets:
                if self._dandiset_needs_update(dandiset, last_sync_time):
                    dandisets_to_update.append(dandiset)
                self.stats['dandisets_checked'] += 1
        else:
            with tqdm(dandisets, desc=filter_desc, unit="dandiset") as pbar:
                for dandiset in pbar:
                    pbar.set_postfix(current=dandiset.identifier)
                    if self._dandiset_needs_update(dandiset, last_sync_time):
                        dandisets_to_update.append(dandiset)
                    self.stats['dandisets_checked'] += 1
        
        self.stdout.write(f"Found {len(dandisets_to_update)} dandisets to update")
        
        if not dandisets_to_update:
            return
        
        # Update dandisets
        update_desc = "Updating dandisets"
        if self.no_progress:
            for dandiset in dandisets_to_update:
                self._update_dandiset(dandiset)
        else:
            with tqdm(dandisets_to_update, desc=update_desc, unit="dandiset") as pbar:
                for dandiset in pbar:
                    pbar.set_postfix(current=dandiset.identifier)
                    self._update_dandiset(dandiset)

    def _sync_assets(self, last_sync_time, options):
        """Sync asset metadata"""
        self.stdout.write("Syncing assets...")
        
        # Get dandisets to check for assets
        if options['dandiset_id']:
            dandisets_query = Dandiset.objects.filter(base_id=options['dandiset_id'])
        else:
            dandisets_query = Dandiset.objects.filter(is_latest=True)
        
        dandisets = list(dandisets_query)
        
        # Filter to only check assets for dandisets that need updating
        # If a dandiset hasn't been modified, its assets haven't been modified either
        if last_sync_time and not options.get('force_full_sync'):
            dandisets_to_check = []
            
            # Get API dandisets to check modification dates
            if self.verbose:
                self.stdout.write("Filtering dandisets that need asset updates...")
            
            api_dandisets = {}
            try:
                for api_ds in self.client.get_dandisets():
                    api_dandisets[api_ds.identifier] = api_ds
            except Exception as e:
                if self.verbose:
                    self.stdout.write(f"Error fetching API dandisets: {e}")
                # Fall back to checking all dandisets if we can't get API list
                dandisets_to_check = dandisets
            
            if api_dandisets:
                filter_desc = "Checking which dandisets need asset updates"
                if self.no_progress:
                    for dandiset in dandisets:
                        # Find corresponding API dandiset
                        api_dandiset = None
                        for identifier in [dandiset.base_id, dandiset.identifier]:
                            if identifier in api_dandisets:
                                api_dandiset = api_dandisets[identifier]
                                break
                        
                        if api_dandiset and self._dandiset_needs_update(api_dandiset, last_sync_time):
                            dandisets_to_check.append(dandiset)
                        elif self.verbose and api_dandiset:
                            self.stdout.write(f"Skipping assets for unchanged dandiset: {dandiset.base_id}")
                        elif not api_dandiset:
                            # If we can't find the API dandiset, check it anyway to be safe
                            dandisets_to_check.append(dandiset)
                else:
                    with tqdm(dandisets, desc=filter_desc, unit="dandiset") as filter_pbar:
                        for dandiset in filter_pbar:
                            filter_pbar.set_postfix(checking=dandiset.base_id)
                            
                            # Find corresponding API dandiset
                            api_dandiset = None
                            for identifier in [dandiset.base_id, dandiset.identifier]:
                                if identifier in api_dandisets:
                                    api_dandiset = api_dandisets[identifier]
                                    break
                            
                            if api_dandiset and self._dandiset_needs_update(api_dandiset, last_sync_time):
                                dandisets_to_check.append(dandiset)
                            elif self.verbose and api_dandiset:
                                self.stdout.write(f"Skipping assets for unchanged dandiset: {dandiset.base_id}")
                            elif not api_dandiset:
                                # If we can't find the API dandiset, check it anyway to be safe
                                dandisets_to_check.append(dandiset)
            
            dandisets = dandisets_to_check
            
        self.stdout.write(f"Processing assets for {len(dandisets)} dandisets")
        
        if not dandisets:
            self.stdout.write("No dandisets need asset updates")
            return
        
        main_desc = "Processing dandisets for asset updates"
        if self.no_progress:
            for dandiset in dandisets:
                self._sync_dandiset_assets(dandiset, last_sync_time, options)
        else:
            with tqdm(dandisets, desc=main_desc, unit="dandiset") as main_pbar:
                for dandiset in main_pbar:
                    main_pbar.set_postfix(dandiset=dandiset.base_id)
                    self._sync_dandiset_assets(dandiset, last_sync_time, options)

    def _dandiset_needs_update(self, api_dandiset, last_sync_time):
        """Check if a dandiset needs updating"""
        if not last_sync_time:
            return True
        
        try:
            api_modified = api_dandiset.modified
            
            if not api_modified:
                if self.verbose:
                    self.stdout.write(f"No dateModified for {api_dandiset.identifier}, skipping")
                return False  # No date info, can't determine if needs update
            
            # Compare API modification time with last sync time
            needs_update = api_modified > last_sync_time
            
            if self.verbose:
                self.stdout.write(f"Dandiset {api_dandiset.identifier}: API modified {api_modified}, last sync {last_sync_time}, needs update: {needs_update}")
            
            return needs_update
                
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error checking {api_dandiset.identifier}: {e}")
            return False  # On error, be conservative and skip

    def _update_dandiset(self, api_dandiset, sync_tracker=None):
        """Update a single dandiset"""
        try:
            if self.dry_run:
                self.stdout.write(f"Would update dandiset: {api_dandiset.identifier}")
                self.stats['dandisets_updated'] += 1
                return
            
            with transaction.atomic():
                metadata = api_dandiset.get_raw_metadata()
                self._load_dandiset(metadata, sync_tracker)
                self.stats['dandisets_updated'] += 1
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error updating dandiset {api_dandiset.identifier}: {e}")

    def _sync_dandiset_assets(self, dandiset, last_sync_time, options):
        """Sync assets for a specific dandiset"""
        try:
            # Get the API dandiset - try multiple identifier formats
            api_dandiset = None
            
            # Extract dandiset number from base_id
            base_id = dandiset.base_id
            if base_id.startswith('DANDI:'):
                dandiset_number = base_id.split(':')[1]
            else:
                dandiset_number = base_id
            
            # Try multiple approaches to get the dandiset from the API
            for attempt_id in [dandiset_number, f"DANDI:{dandiset_number}", base_id]:
                try:
                    if self.verbose:
                        self.stdout.write(f"Trying to get dandiset with ID: {attempt_id}")
                    api_dandiset = self.client.get_dandiset(attempt_id)
                    if self.verbose:
                        self.stdout.write(f"Successfully found dandiset with ID: {attempt_id}")
                    break
                except Exception as e:
                    if self.verbose:
                        self.stdout.write(f"Failed to get dandiset with ID {attempt_id}: {e}")
                    continue
            
            # If direct access fails, try searching through all dandisets
            if not api_dandiset:
                if self.verbose:
                    self.stdout.write(f"Direct access failed for {base_id}, searching through all dandisets...")
                
                try:
                    for ds in self.client.get_dandisets():
                        # Try multiple matching approaches
                        if (ds.identifier == base_id or 
                            ds.identifier == f"DANDI:{dandiset_number}" or
                            ds.identifier == dandiset_number or
                            getattr(ds, 'id', '').endswith(dandiset_number)):
                            api_dandiset = ds
                            if self.verbose:
                                self.stdout.write(f"Found matching dandiset: {ds.identifier}")
                            break
                except Exception as e:
                    if self.verbose:
                        self.stdout.write(f"Error searching through dandisets: {e}")
            
            if not api_dandiset:
                if self.verbose:
                    self.stdout.write(f"Could not find API dandiset for {dandiset.base_id} (tried: {dandiset_number}, DANDI:{dandiset_number}, {base_id})")
                return
            
            # Get assets from API
            api_assets = list(api_dandiset.get_assets())
            
            if not api_assets:
                return
            
            # Apply max assets limit
            max_assets = options.get('max_assets', 2000)
            if len(api_assets) > max_assets:
                if self.verbose:
                    self.stdout.write(f"Limiting assets for {dandiset.base_id} to {max_assets} (total: {len(api_assets)})")
                api_assets = api_assets[:max_assets]
            
            # Filter assets that need updating
            assets_to_update = []
            
            asset_filter_desc = f"Checking assets for {dandiset.base_id}"
            if self.no_progress:
                for asset in api_assets:
                    if self._asset_needs_update(asset, last_sync_time):
                        assets_to_update.append(asset)
                    self.stats['assets_checked'] += 1
            else:
                with tqdm(api_assets, desc=asset_filter_desc, unit="asset", leave=False) as asset_pbar:
                    for asset in asset_pbar:
                        asset_pbar.set_postfix(asset=self._truncate_path(getattr(asset, 'path', 'unknown')))
                        if self._asset_needs_update(asset, last_sync_time):
                            assets_to_update.append(asset)
                        self.stats['assets_checked'] += 1
            
            if not assets_to_update:
                return
            
            # Update assets
            asset_update_desc = f"Updating assets for {dandiset.base_id}"
            if self.no_progress:
                for asset in assets_to_update:
                    self._update_asset(asset, dandiset)
            else:
                with tqdm(assets_to_update, desc=asset_update_desc, unit="asset", leave=False) as update_pbar:
                    for asset in update_pbar:
                        update_pbar.set_postfix(asset=self._truncate_path(getattr(asset, 'path', 'unknown')))
                        self._update_asset(asset, dandiset)
                        
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error syncing assets for {dandiset.base_id}: {e}")

    def _asset_needs_update(self, api_asset, last_sync_time):
        """Check if an asset needs updating"""
        if not last_sync_time:
            return True
        
        try:
            # Get raw metadata
            metadata = api_asset.get_raw_metadata()
            
            # Check modification dates
            api_modified = parse_datetime(metadata.get('dateModified'))
            api_blob_modified = parse_datetime(metadata.get('blobDateModified'))
            
            # Use the latest of the two dates
            latest_api_date = None
            if api_modified and api_blob_modified:
                latest_api_date = max(api_modified, api_blob_modified)
            elif api_modified:
                latest_api_date = api_modified
            elif api_blob_modified:
                latest_api_date = api_blob_modified
            
            if not latest_api_date:
                return True  # No date info, assume needs update
            
            # Check if we have this asset locally
            asset_id = metadata.get('identifier', '')
            if not asset_id and metadata.get('id'):
                full_id = metadata.get('id', '')
                if ':' in full_id:
                    asset_id = full_id.split(':', 1)[1]
                else:
                    asset_id = full_id
            
            try:
                local_asset = Asset.objects.get(dandi_asset_id=asset_id)
                
                # Compare with local dates
                local_modified = local_asset.date_modified
                local_blob_modified = local_asset.blob_date_modified
                
                latest_local_date = None
                if local_modified and local_blob_modified:
                    latest_local_date = max(local_modified, local_blob_modified)
                elif local_modified:
                    latest_local_date = local_modified
                elif local_blob_modified:
                    latest_local_date = local_blob_modified
                
                if not latest_local_date:
                    return True
                
                return latest_api_date > latest_local_date
                
            except Asset.DoesNotExist:
                return True  # New asset
                
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error checking asset: {e}")
            return True  # Assume needs update on error

    def _update_asset(self, api_asset, dandiset, sync_tracker=None):
        """Update a single asset"""
        try:
            if self.dry_run:
                asset_path = getattr(api_asset, 'path', 'unknown')
                if self.verbose:
                    self.stdout.write(f"Would update asset: {asset_path}")
                self.stats['assets_updated'] += 1
                return
            
            with transaction.atomic():
                metadata = api_asset.get_raw_metadata()
                asset = self._load_asset(metadata, dandiset, sync_tracker)
                self.stats['assets_updated'] += 1
                
                # After updating the asset, try to sync LINDI metadata if it's an NWB file
                if not self.options.get('skip_lindi', False) and asset and asset.encoding_format == 'application/x-nwb':
                    self._process_lindi_for_asset(asset, sync_tracker)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                asset_path = getattr(api_asset, 'path', 'unknown')
                self.stdout.write(f"Error updating asset {asset_path}: {e}")

    def _asset_needs_update_from_yaml(self, asset_data, last_sync_time):
        """Check if an asset needs updating based on YAML data"""
        if not last_sync_time:
            return True
        
        try:
            # Check modification dates from YAML
            api_modified = parse_datetime(asset_data.get('dateModified'))
            api_blob_modified = parse_datetime(asset_data.get('blobDateModified'))
            
            # Use the latest of the two dates
            latest_api_date = None
            if api_modified and api_blob_modified:
                latest_api_date = max(api_modified, api_blob_modified)
            elif api_modified:
                latest_api_date = api_modified
            elif api_blob_modified:
                latest_api_date = api_blob_modified
            
            if not latest_api_date:
                return True  # No date info, assume needs update
            
            # Check if we have this asset locally
            asset_id = asset_data.get('identifier', '')
            if not asset_id and asset_data.get('id'):
                full_id = asset_data.get('id', '')
                if ':' in full_id:
                    asset_id = full_id.split(':', 1)[1]
                else:
                    asset_id = full_id
            
            try:
                local_asset = Asset.objects.get(dandi_asset_id=asset_id)
                
                # Compare with local dates
                local_modified = local_asset.date_modified
                local_blob_modified = local_asset.blob_date_modified
                
                latest_local_date = None
                if local_modified and local_blob_modified:
                    latest_local_date = max(local_modified, local_blob_modified)
                elif local_modified:
                    latest_local_date = local_modified
                elif local_blob_modified:
                    latest_local_date = local_blob_modified
                
                if not latest_local_date:
                    return True
                
                return latest_api_date > latest_local_date
                
            except Asset.DoesNotExist:
                return True  # New asset
                
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error checking asset from YAML: {e}")
            return True  # Assume needs update on error

    def _update_asset_from_yaml(self, asset_data, dandiset, sync_tracker=None):
        """Update a single asset from YAML data"""
        try:
            if self.dry_run:
                asset_path = asset_data.get('path', 'unknown')
                if self.verbose:
                    self.stdout.write(f"Would update asset: {asset_path}")
                self.stats['assets_updated'] += 1
                return
            
            with transaction.atomic():
                asset = self._load_asset(asset_data, dandiset, sync_tracker)
                self.stats['assets_updated'] += 1
                
                # After updating the asset, try to sync LINDI metadata if it's an NWB file
                if not self.options.get('skip_lindi', False) and asset and asset.encoding_format == 'application/x-nwb':
                    self._process_lindi_for_asset(asset, sync_tracker)
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                asset_path = asset_data.get('path', 'unknown')
                self.stdout.write(f"Error updating asset {asset_path}: {e}")

    def _check_for_deleted_assets_in_dandiset_from_yaml(self, local_dandiset, assets_data, options):
        """Check for assets that exist locally but not in the YAML for this specific dandiset"""
        try:
            # Create set of asset IDs from YAML for fast lookup
            yaml_asset_ids = set()
            for asset_data in assets_data:
                asset_id = asset_data.get('identifier', '')
                if not asset_id and asset_data.get('id'):
                    full_id = asset_data.get('id', '')
                    if ':' in full_id:
                        asset_id = full_id.split(':', 1)[1]
                    else:
                        asset_id = full_id
                if asset_id:
                    yaml_asset_ids.add(asset_id)
            
            # Get all local assets that belong to this dandiset
            local_assets = local_dandiset.assets.all()
            
            assets_to_delete = []
            
            for local_asset in local_assets:
                if local_asset.dandi_asset_id not in yaml_asset_ids:
                    # Check if this asset belongs to other dandisets before adding to deletion list
                    if local_asset.dandisets.count() == 1:
                        # Asset only belongs to this dandiset - safe to delete completely
                        assets_to_delete.append(('delete_asset', local_asset))
                        if self.verbose:
                            self.stdout.write(f"Asset {local_asset.dandi_asset_id} will be deleted (only belongs to {local_dandiset.base_id})")
                    else:
                        # Asset belongs to multiple dandisets - only remove the relationship
                        assets_to_delete.append(('remove_relationship', local_asset))
                        if self.verbose:
                            self.stdout.write(f"Asset {local_asset.dandi_asset_id} relationship will be removed from {local_dandiset.base_id} (belongs to multiple dandisets)")
            
            if not assets_to_delete:
                if self.verbose:
                    self.stdout.write(f"No deleted assets found in dandiset {local_dandiset.base_id}")
                return
            
            if self.verbose:
                self.stdout.write(f"Found {len(assets_to_delete)} assets to process for deletion in dandiset {local_dandiset.base_id}")
            
            # Process the assets
            for action, asset in assets_to_delete:
                if self.dry_run:
                    if action == 'delete_asset':
                        if self.verbose:
                            self.stdout.write(f"Would delete asset: {asset.path}")
                    else:
                        if self.verbose:
                            self.stdout.write(f"Would remove relationship for asset: {asset.path}")
                    self.stats['assets_deleted'] += 1
                else:
                    with transaction.atomic():
                        if action == 'delete_asset':
                            if self.verbose:
                                self.stdout.write(f"Deleting asset: {asset.path}")
                            asset.delete()
                        else:
                            if self.verbose:
                                self.stdout.write(f"Removing relationship for asset: {asset.path}")
                            AssetDandiset.objects.filter(
                                asset=asset,
                                dandiset=local_dandiset
                            ).delete()
                        
                        self.stats['assets_deleted'] += 1
                        
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error checking for deleted assets in dandiset {local_dandiset.base_id}: {e}")

    def _sync_lindi_metadata_only(self, options, sync_tracker=None):
        """Sync LINDI metadata only for existing NWB assets without touching DANDI API data"""
        self.stdout.write("Starting LINDI-only metadata sync...")
        
        # Build query for NWB assets
        query = Q(encoding_format='application/x-nwb')
        
        # Filter by dandiset if specified
        dandiset_filter = options.get('dandiset_filter') or options.get('dandiset_id')
        if dandiset_filter:
            dandiset_filter = self._normalize_dandiset_id(dandiset_filter)
            query &= Q(dandisets__base_id__endswith=dandiset_filter)
            
            if self.verbose:
                self.stdout.write(f"Filtering assets for dandiset: {dandiset_filter}")
        
        # Get NWB assets
        nwb_assets = Asset.objects.filter(query).distinct()
        
        if not nwb_assets.exists():
            self.stdout.write("No NWB assets found matching criteria")
            return
        
        total_assets = nwb_assets.count()
        self.stdout.write(f"Found {total_assets} NWB assets to process")
        
        # Combined filtering and processing in a single pass
        def process_asset_if_needed(asset):
            # Check if asset needs LINDI processing
            needs_processing = False
            
            # Check if force refresh is enabled
            if options.get('force_lindi_refresh'):
                needs_processing = True
            else:
                # Check if asset already has LINDI metadata
                try:
                    LindiMetadata.objects.get(asset=asset)
                    # Asset already has LINDI metadata
                    needs_processing = False
                except LindiMetadata.DoesNotExist:
                    needs_processing = True
            
            if needs_processing:
                # Process the asset immediately
                self._process_lindi_for_existing_asset(asset, sync_tracker)
            else:
                self.stats['lindi_skipped'] += 1
            
            self.stats['assets_checked'] += 1
        
        # Process assets with combined filtering and processing
        process_desc = "Processing LINDI metadata for assets"
        
        self._process_with_progress(
            nwb_assets,
            process_asset_if_needed,
            process_desc,
            unit="asset",
            postfix_func=lambda asset: {"asset": self._truncate_path(asset.path)},
            leave=True
        )

    def _process_lindi_parallel(self, assets_to_process, sync_tracker, options):
        """Process LINDI metadata for multiple assets in parallel"""
        max_workers = options.get('max_workers', 4)
        self.stdout.write(f"Using parallel processing with {max_workers} workers")
        
        # Thread-safe statistics tracking
        stats_lock = threading.Lock()
        
        def process_single_asset(asset):
            """Process a single asset - used by worker threads"""
            try:
                # Use helper method to determine if asset should be processed
                should_process = self._should_process_lindi_for_asset(
                    asset, 
                    force_refresh=options.get('force_lindi_refresh', False)
                )
                
                if not should_process:
                    with stats_lock:
                        self.stats['lindi_skipped'] += 1
                        self.stats['assets_checked'] += 1
                    return f"Skipped {asset.dandi_asset_id} (already has metadata)"

                # Construct LINDI URL
                lindi_url = self._construct_lindi_url(asset)
                if not lindi_url:
                    with stats_lock:
                        self.stats['lindi_skipped'] += 1
                        self.stats['assets_checked'] += 1
                    return f"Skipped {asset.dandi_asset_id} (no URL)"

                # Download LINDI file (each worker has its own session)
                worker_session = requests.Session()
                worker_session.headers.update(self.session.headers)
                
                try:
                    response = worker_session.get(lindi_url, timeout=self.timeout)
                    response.raise_for_status()
                    lindi_data = response.json()
                except Exception as e:
                    with stats_lock:
                        self.stats['lindi_errors'] += 1
                        self.stats['assets_checked'] += 1
                    return f"Error downloading {asset.dandi_asset_id}: {e}"
                finally:
                    worker_session.close()

                # Filter LINDI data
                filtered_data = self._filter_lindi_data(lindi_data)

                # Save to database (ensure each worker has its own connection)
                if not self.dry_run:
                    try:
                        # Close any existing connection to ensure clean state
                        connections.close_all()
                        
                        with transaction.atomic():
                            lindi_metadata, created = LindiMetadata.objects.update_or_create(
                                asset=asset,
                                defaults={
                                    'structure_metadata': filtered_data,
                                    'lindi_url': lindi_url,
                                    'processing_version': '1.0',
                                    'sync_tracker': sync_tracker,
                                }
                            )
                        
                        with stats_lock:
                            self.stats['lindi_processed'] += 1
                            self.stats['assets_checked'] += 1
                        
                        action = "Created" if created else "Updated"
                        return f"{action} LINDI metadata for {asset.dandi_asset_id}"
                        
                    except Exception as e:
                        with stats_lock:
                            self.stats['lindi_errors'] += 1
                            self.stats['assets_checked'] += 1
                        return f"Error saving {asset.dandi_asset_id}: {e}"
                else:
                    with stats_lock:
                        self.stats['lindi_processed'] += 1
                        self.stats['assets_checked'] += 1
                    return f"Would process LINDI metadata for {asset.dandi_asset_id}"
                    
            except Exception as e:
                with stats_lock:
                    self.stats['lindi_errors'] += 1
                    self.stats['assets_checked'] += 1
                return f"Unexpected error processing {asset.dandi_asset_id}: {e}"

        # Process assets in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            if self.no_progress:
                # Submit all jobs and wait for completion
                futures = {executor.submit(process_single_asset, asset): asset for asset in assets_to_process}
                
                for future in as_completed(futures):
                    asset = futures[future]
                    try:
                        result = future.result()
                        if self.verbose:
                            self.stdout.write(result)
                    except Exception as exc:
                        if self.verbose:
                            self.stdout.write(f'Asset {asset.dandi_asset_id} generated an exception: {exc}')
            else:
                # Use progress bar
                futures = {executor.submit(process_single_asset, asset): asset for asset in assets_to_process}
                
                with tqdm(total=len(assets_to_process), desc="Processing LINDI metadata (parallel)", unit="asset") as pbar:
                    for future in as_completed(futures):
                        asset = futures[future]
                        try:
                            result = future.result()
                            pbar.set_postfix(asset=self._truncate_path(asset.path))
                            if self.verbose:
                                self.stdout.write(result)
                        except Exception as exc:
                            if self.verbose:
                                self.stdout.write(f'Asset {asset.dandi_asset_id} generated an exception: {exc}')
                        finally:
                            pbar.update(1)

        # Ensure all database connections are closed after parallel processing
        connections.close_all()

    def _process_lindi_for_existing_asset(self, asset, sync_tracker=None):
        """Process LINDI metadata for an existing asset (used in LINDI-only sync)"""
        try:
            # Use helper method to determine if asset should be processed
            should_process = self._should_process_lindi_for_asset(
                asset, 
                force_refresh=self.options.get('force_lindi_refresh', False)
            )
            
            if should_process and self.options.get('force_lindi_refresh') and self.verbose:
                self.stdout.write(f"Force refreshing LINDI metadata for: {asset.path}")
            
            if not should_process:
                if self.verbose:
                    self.stdout.write(f"Asset {asset.dandi_asset_id} already has LINDI metadata, skipping")
                self.stats['lindi_skipped'] += 1
                return

            # Construct LINDI URL
            lindi_url = self._construct_lindi_url(asset)
            if not lindi_url:
                if self.verbose:
                    self.stdout.write(f"Could not construct LINDI URL for asset {asset.dandi_asset_id}")
                self.stats['lindi_skipped'] += 1
                return

            # Download and process LINDI file
            lindi_data = self._download_lindi_file(lindi_url)
            if not lindi_data:
                self.stats['lindi_errors'] += 1
                return

            # Filter LINDI data
            filtered_data = self._filter_lindi_data(lindi_data)

            # Save to database (don't skip in dry run for LINDI-only sync)
            if self.dry_run:
                if self.verbose:
                    self.stdout.write(f"Would process LINDI metadata for: {asset.path}")
                self.stats['lindi_processed'] += 1
            else:
                self._save_lindi_metadata(asset, lindi_url, lindi_data, filtered_data, sync_tracker)
                self.stats['lindi_processed'] += 1

                if self.verbose:
                    self.stdout.write(f"Processed LINDI metadata for: {asset.path}")

        except Exception as e:
            self.stats['lindi_errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing LINDI for asset {asset.dandi_asset_id}: {e}")

    def _record_sync_completion(self, sync_tracker, duration):
        """Record sync completion in database"""
        sync_tracker.status = 'completed'
        sync_tracker.last_sync_timestamp = datetime.now(timezone.utc)
        sync_tracker.dandisets_synced = self.stats['dandisets_checked']
        sync_tracker.assets_synced = self.stats['assets_checked']
        sync_tracker.dandisets_updated = self.stats['dandisets_updated']
        sync_tracker.assets_updated = self.stats['assets_updated']
        sync_tracker.sync_duration_seconds = duration
        sync_tracker.save()

    def _record_sync_failure(self, sync_tracker, duration, error_message):
        """Record sync failure in database"""
        sync_tracker.status = 'failed'
        sync_tracker.last_sync_timestamp = datetime.now(timezone.utc)
        sync_tracker.dandisets_synced = self.stats['dandisets_checked']
        sync_tracker.assets_synced = self.stats['assets_checked']
        sync_tracker.dandisets_updated = self.stats['dandisets_updated']
        sync_tracker.assets_updated = self.stats['assets_updated']
        sync_tracker.sync_duration_seconds = duration
        sync_tracker.error_message = error_message[:1000] if error_message else ''  # Truncate if too long
        sync_tracker.save()

    def _print_summary(self, duration):
        """Print sync summary"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("UNIFIED SYNC SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Duration: {duration:.2f} seconds")
        self.stdout.write(f"Dandisets checked: {self.stats['dandisets_checked']}")
        self.stdout.write(f"Dandisets updated: {self.stats['dandisets_updated']}")
        self.stdout.write(f"Dandisets deleted: {self.stats['dandisets_deleted']}")
        self.stdout.write(f"Assets checked: {self.stats['assets_checked']}")
        self.stdout.write(f"Assets updated: {self.stats['assets_updated']}")
        self.stdout.write(f"Assets deleted: {self.stats['assets_deleted']}")
        
        # Show cache statistics
        total_cache_requests = self.stats['cache_hits'] + self.stats['cache_misses']
        if total_cache_requests > 0:
            cache_hit_rate = (self.stats['cache_hits'] / total_cache_requests) * 100
            self.stdout.write(f"YAML cache hits: {self.stats['cache_hits']}")
            self.stdout.write(f"YAML cache misses: {self.stats['cache_misses']}")
            self.stdout.write(f"YAML cache hit rate: {cache_hit_rate:.1f}%")
        
        # Show LINDI statistics only if LINDI processing was enabled
        if not self.options.get('skip_lindi', False):
            self.stdout.write(f"LINDI metadata processed: {self.stats['lindi_processed']}")
            self.stdout.write(f"LINDI metadata skipped: {self.stats['lindi_skipped']}")
            self.stdout.write(f"LINDI errors: {self.stats['lindi_errors']}")
        
        self.stdout.write(f"Total errors: {self.stats['errors']}")
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made"))
        else:
            self.stdout.write(self.style.SUCCESS("Unified sync completed successfully"))

    def _check_for_deleted_dandisets(self, options, sync_tracker=None):
        """Check for dandisets that exist locally but not in DANDI API and delete them"""
        self.stdout.write("Checking for deleted dandisets...")
        
        try:
            # Get all dandisets from DANDI API (using cache)
            api_dandisets = self._get_api_dandisets()
            api_dandiset_ids = {self._extract_base_id(ds.identifier) for ds in api_dandisets}
            
            # Get all local dandisets that are marked as latest
            local_dandisets = Dandiset.objects.filter(is_latest=True)
            
            dandisets_to_delete = []
            
            def check_local_dandiset(local_dandiset):
                local_base_id = self._extract_base_id(local_dandiset.base_id)
                if local_base_id not in api_dandiset_ids:
                    dandisets_to_delete.append(local_dandiset)
                    if self.verbose:
                        self.stdout.write(f"Dandiset {local_dandiset.base_id} no longer exists in DANDI API")
            
            # Check all local dandisets
            self._process_with_progress(
                local_dandisets,
                check_local_dandiset,
                "Checking for deleted dandisets",
                unit="dandiset",
                postfix_func=lambda ds: {"checking": ds.base_id}
            )
            
            if not dandisets_to_delete:
                self.stdout.write("No deleted dandisets found")
                return
            
            self.stdout.write(f"Found {len(dandisets_to_delete)} dandisets to delete")
            
            def delete_dandiset(dandiset):
                if self.dry_run:
                    if self.verbose:
                        self.stdout.write(f"Would delete dandiset: {dandiset.base_id}")
                    self.stats['dandisets_deleted'] += 1
                else:
                    if self.verbose:
                        self.stdout.write(f"Deleting dandiset: {dandiset.base_id}")
                    
                    with transaction.atomic():
                        # Also delete related assets that only belong to this dandiset
                        for asset in dandiset.assets.all():
                            if asset.dandisets.count() == 1:  # Only belongs to this dandiset
                                asset.delete()
                                self.stats['assets_deleted'] += 1
                        
                        dandiset.delete()
                        self.stats['dandisets_deleted'] += 1
            
            # Delete dandisets
            self._process_with_progress(
                dandisets_to_delete,
                delete_dandiset,
                "Deleting dandisets",
                unit="dandiset",
                postfix_func=lambda ds: {"deleting": ds.base_id}
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error checking for deleted dandisets: {e}")

    def _check_for_deleted_assets_in_dandiset(self, local_dandiset, api_assets, options):
        """Check for assets that exist locally but not in the API for this specific dandiset"""
        try:
            # Create set of API asset IDs for fast lookup
            api_asset_ids = set()
            for api_asset in api_assets:
                try:
                    metadata = api_asset.get_raw_metadata()
                    asset_id = metadata.get('identifier', '')
                    if not asset_id and metadata.get('id'):
                        full_id = metadata.get('id', '')
                        if ':' in full_id:
                            asset_id = full_id.split(':', 1)[1]
                        else:
                            asset_id = full_id
                    if asset_id:
                        api_asset_ids.add(asset_id)
                except Exception as e:
                    if self.verbose:
                        self.stdout.write(f"Error getting asset ID from API asset: {e}")
                    continue
            
            # Get all local assets that belong to this dandiset
            local_assets = local_dandiset.assets.all()
            
            assets_to_delete = []
            
            for local_asset in local_assets:
                if local_asset.dandi_asset_id not in api_asset_ids:
                    # Check if this asset belongs to other dandisets before adding to deletion list
                    if local_asset.dandisets.count() == 1:
                        # Asset only belongs to this dandiset - safe to delete completely
                        assets_to_delete.append(('delete_asset', local_asset))
                        if self.verbose:
                            self.stdout.write(f"Asset {local_asset.dandi_asset_id} will be deleted (only belongs to {local_dandiset.base_id})")
                    else:
                        # Asset belongs to multiple dandisets - only remove the relationship
                        assets_to_delete.append(('remove_relationship', local_asset))
                        if self.verbose:
                            self.stdout.write(f"Asset {local_asset.dandi_asset_id} relationship will be removed from {local_dandiset.base_id} (belongs to multiple dandisets)")
            
            if not assets_to_delete:
                if self.verbose:
                    self.stdout.write(f"No deleted assets found in dandiset {local_dandiset.base_id}")
                return
            
            if self.verbose:
                self.stdout.write(f"Found {len(assets_to_delete)} assets to process for deletion in dandiset {local_dandiset.base_id}")
            
            # Process the assets
            for action, asset in assets_to_delete:
                if self.dry_run:
                    if action == 'delete_asset':
                        if self.verbose:
                            self.stdout.write(f"Would delete asset: {asset.path}")
                    else:
                        if self.verbose:
                            self.stdout.write(f"Would remove relationship for asset: {asset.path}")
                    self.stats['assets_deleted'] += 1
                else:
                    with transaction.atomic():
                        if action == 'delete_asset':
                            if self.verbose:
                                self.stdout.write(f"Deleting asset: {asset.path}")
                            asset.delete()
                        else:
                            if self.verbose:
                                self.stdout.write(f"Removing relationship for asset: {asset.path}")
                            AssetDandiset.objects.filter(
                                asset=asset,
                                dandiset=local_dandiset
                            ).delete()
                        
                        self.stats['assets_deleted'] += 1
                        
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error checking for deleted assets in dandiset {local_dandiset.base_id}: {e}")

    def _extract_base_id(self, identifier):
        """Extract base ID from a dandiset identifier"""
        if not identifier:
            return None
        
        # Handle formats like "DANDI:000003" or "000003" 
        if identifier.startswith('DANDI:'):
            return identifier[6:].zfill(6)
        else:
            return identifier.zfill(6)

    # Include all the helper methods from load_sample_data.py for loading data
    def _load_dandiset(self, data, sync_tracker=None):
        """Load a single dandiset from JSON data."""
        # Extract version information from the ID
        full_id = data.get('id', '')  # Full ID like "DANDI:000003/0.230629.1955"
        identifier = data.get('identifier', '')  # Base ID like "DANDI:000003"
        version = data.get('version', '')
        
        # Determine if this is a draft (no version)
        is_draft = not bool(version)
        version_order = 0 if is_draft else 1  # Default to 1 for published versions
        
        # Prepare sync tracking fields
        sync_fields = {}
        if sync_tracker:
            sync_fields['last_modified_by_sync'] = sync_tracker
        
        # Create or get the dandiset
        dandiset, created = Dandiset.objects.update_or_create(
            dandi_id=full_id,
            defaults={
                'identifier': identifier,
                'base_id': identifier,
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'url': data.get('url', ''),
                'doi': data.get('doi', ''),
                'version': version if not is_draft else None,
                'version_order': version_order,
                'is_draft': is_draft,
                'is_latest': True,  # Assume each loaded version is latest for now
                'citation': data.get('citation', ''),
                'schema_version': data.get('schemaVersion', ''),
                'repository': data.get('repository', ''),
                'date_created': parse_datetime(data.get('dateCreated')) if data.get('dateCreated') else None,
                'date_modified': parse_datetime(data.get('dateModified')) if data.get('dateModified') else None,
                'date_published': parse_datetime(data.get('datePublished')) if data.get('datePublished') else None,
                'license': data.get('license', []),
                'keywords': data.get('keywords', []),
                'study_target': data.get('studyTarget', []),
                'protocol': data.get('protocol', []),
                'acknowledgement': data.get('acknowledgement', ''),
                'manifest_location': data.get('manifestLocation', []),
                **sync_fields
            }
        )
        
        # Set created_by_sync for new dandisets
        if created and sync_tracker:
            dandiset.created_by_sync = sync_tracker
            dandiset.save()

        if self.verbose:
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} dandiset: {dandiset.name}")

        # Load contributors
        for contributor_data in data.get('contributor', []):
            contributor = self._load_contributor(contributor_data)
            if contributor:
                # Create the relationship with role information
                relationship, created = DandisetContributor.objects.get_or_create(
                    dandiset=dandiset,
                    contributor=contributor,
                    defaults={
                        'role_name': contributor_data.get('roleName', []),
                        'include_in_citation': contributor_data.get('includeInCitation', True),
                    }
                )
                
                # Update existing relationships with new role data if needed
                if not created:
                    updated = False
                    new_roles = contributor_data.get('roleName', [])
                    if new_roles and new_roles != relationship.role_name:
                        # Merge roles - keep existing and add new ones
                        existing_roles = set(relationship.role_name) if relationship.role_name else set()
                        new_role_set = set(new_roles) if isinstance(new_roles, list) else {new_roles}
                        merged_roles = list(existing_roles | new_role_set)
                        relationship.role_name = merged_roles
                        updated = True
                    
                    include_in_citation = contributor_data.get('includeInCitation')
                    if include_in_citation is not None and include_in_citation != relationship.include_in_citation:
                        relationship.include_in_citation = include_in_citation
                        updated = True
                    
                    if updated:
                        relationship.save()

        # Load about section - now using direct many-to-many relationships
        for about_data in data.get('about', []):
            about_obj, field_name = self._load_about_object(about_data)
            if about_obj and field_name:
                # Use the appropriate many-to-many field on the dandiset
                if field_name == 'anatomy':
                    dandiset.anatomy.add(about_obj)
                elif field_name == 'disorder':
                    dandiset.disorders.add(about_obj)
                elif field_name == 'generic_type':
                    dandiset.generic_types.add(about_obj)

        # Load access requirements - using intermediate model
        for access_data in data.get('access', []):
            access_req = self._load_access_requirements(access_data)
            if access_req:
                DandisetAccessRequirements.objects.get_or_create(
                    dandiset=dandiset,
                    access_requirement=access_req
                )

        # Load related resources - using intermediate model
        for resource_data in data.get('relatedResource', []):
            resource = self._load_resource(resource_data)
            if resource:
                DandisetRelatedResource.objects.get_or_create(
                    dandiset=dandiset,
                    resource=resource
                )

        # Load assets summary
        assets_summary_data = data.get('assetsSummary')
        if assets_summary_data:
            assets_summary = self._load_assets_summary(assets_summary_data)
            if assets_summary:
                dandiset.assets_summary = assets_summary
                dandiset.save()

        # Load published by activity
        published_by_data = data.get('publishedBy')
        if published_by_data:
            activity = self._load_activity(published_by_data)
            if activity:
                dandiset.published_by = activity
                dandiset.save()

    def _load_asset(self, data, dandiset, sync_tracker=None):
        """Load an asset from JSON data."""
        # Extract asset ID from the full ID
        asset_id = data.get('identifier', '')
        if not asset_id:
            # Try to extract from id field like "dandiasset:a0a7ee60-6e67-42fa-aa88-d31b6b2cb95c"
            full_id = data.get('id', '')
            if ':' in full_id:
                asset_id = full_id.split(':', 1)[1]
            else:
                asset_id = full_id

        # Prepare sync tracking fields
        sync_fields = {}
        if sync_tracker:
            sync_fields['last_modified_by_sync'] = sync_tracker

        asset, created = Asset.objects.update_or_create(
            dandi_asset_id=asset_id,
            defaults={
                'identifier': asset_id,
                'content_size': data.get('contentSize', 0),
                'encoding_format': data.get('encodingFormat', ''),
                'schema_version': data.get('schemaVersion', '0.6.7'),
                'date_modified': self._parse_datetime_with_timezone(data.get('dateModified')),
                'date_published': self._parse_datetime_with_timezone(data.get('datePublished')),
                'blob_date_modified': self._parse_datetime_with_timezone(data.get('blobDateModified')),
                'digest': data.get('digest', {}),
                'content_url': data.get('contentUrl', []),
                'variable_measured': data.get('variableMeasured', []),
                **sync_fields
            }
        )
        
        # Set created_by_sync for new assets
        if created and sync_tracker:
            asset.created_by_sync = sync_tracker
            asset.save()

        if self.verbose:
            action = "Created" if created else "Updated"
            # Get path from the data we're loading
            path_from_data = data.get('path', 'unknown')
            self.stdout.write(f"{action} asset: {path_from_data}")

        # Create the asset-dandiset relationship with path
        asset_path = data.get('path', '')
        AssetDandiset.objects.get_or_create(
            asset=asset,
            dandiset=dandiset,
            defaults={
                'path': asset_path,
                'is_primary': True
            }
        )

        # Load access requirements - now using direct many-to-many relationship
        for access_data in data.get('access', []):
            access_req = self._load_access_requirements(access_data)
            if access_req:
                asset.access_requirements.add(access_req)

        # Load approaches - now using direct many-to-many relationship
        for approach_data in data.get('approach', []):
            approach, _ = ApproachType.objects.get_or_create(
                name=approach_data.get('name', ''),
                defaults={
                    'identifier': approach_data.get('identifier', ''),
                }
            )
            asset.approaches.add(approach)

        # Load measurement techniques - now using direct many-to-many relationship
        for technique_data in data.get('measurementTechnique', []):
            technique, _ = MeasurementTechniqueType.objects.get_or_create(
                name=technique_data.get('name', ''),
                defaults={
                    'identifier': technique_data.get('identifier', ''),
                }
            )
            asset.measurement_techniques.add(technique)

        # Load participants (wasAttributedTo) - now using direct many-to-many relationship
        for participant_data in data.get('wasAttributedTo', []):
            participant = self._load_participant(participant_data)
            if participant:
                asset.participants.add(participant)

        # Load activities that generated this asset - now using direct many-to-many relationship
        for activity_data in data.get('wasGeneratedBy', []):
            activity = self._load_activity(activity_data)
            if activity:
                asset.activities.add(activity)

        # Load published by activity
        published_by_data = data.get('publishedBy')
        if published_by_data:
            activity = self._load_activity(published_by_data)
            if activity:
                asset.published_by = activity
                asset.save()

        return asset

    # Copy all the helper methods from load_sample_data.py
    def _load_contributor(self, data):
        """Load a contributor from JSON data with deduplication.
        
        Deduplication priority:
        1. By identifier (if provided)
        2. By email address (if provided)
        3. By name (fallback)
        """
        try:
            name = data.get('name', '')
            identifier = data.get('identifier', '').strip() if data.get('identifier') else ''
            email = data.get('email', '').strip() if data.get('email') else ''
            
            # Try to find existing contributor by identifier first (if provided)
            contributor = None
            if identifier:
                # Normalize identifier
                identifier = self._normalize_contributor_identifier(identifier)
                
                # Look for existing contributor with this identifier
                existing_contributors = Contributor.objects.filter(identifier=identifier)
                if existing_contributors.exists():
                    contributor = existing_contributors.first()
                    if self.verbose and contributor:
                        self.stdout.write(f"Found existing contributor by identifier {identifier}: {contributor.name}")
            
            # If no contributor found by identifier, try by email (if provided)
            if not contributor and email:
                existing_contributors = Contributor.objects.filter(email=email)
                if existing_contributors.exists():
                    contributor = existing_contributors.first()
                    if self.verbose and contributor:
                        self.stdout.write(f"Found existing contributor by email {email}: {contributor.name}")
            
            # If no contributor found by identifier or email, try by name
            if not contributor:
                contributor, created = Contributor.objects.get_or_create(
                    name=name,
                    defaults={
                        'email': email,
                        'identifier': identifier,
                        'schema_key': data.get('schemaKey', 'Contributor'),
                        'award_number': data.get('awardNumber', ''),
                        'url': data.get('url', ''),
                    }
                )
                if created and self.verbose:
                    self.stdout.write(f"Created new contributor: {name}")
            else:
                # Update existing contributor with any missing information
                updated = False
                if not contributor.email and email:
                    contributor.email = email
                    updated = True
                if not contributor.url and data.get('url'):
                    contributor.url = data.get('url')
                    updated = True
                if not contributor.award_number and data.get('awardNumber'):
                    contributor.award_number = data.get('awardNumber')
                    updated = True
                if not contributor.identifier and identifier:
                    contributor.identifier = identifier
                    updated = True
                
                # Note: Role names are now stored in DandisetContributor relationships,
                # not on the Contributor model itself
                
                if updated:
                    contributor.save()
                    if self.verbose:
                        self.stdout.write(f"Updated existing contributor: {contributor.name}")

            # Load affiliations
            for affiliation_data in data.get('affiliation', []):
                affiliation, _ = Affiliation.objects.get_or_create(
                    name=affiliation_data.get('name', ''),
                    defaults={
                        'identifier': affiliation_data.get('identifier', ''),
                    }
                )
                ContributorAffiliation.objects.get_or_create(
                    contributor=contributor,
                    affiliation=affiliation
                )

            return contributor
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading contributor: {e}")
            return None

    def _normalize_contributor_identifier(self, identifier):
        """Normalize contributor identifier format"""
        if not identifier:
            return identifier
            
        # Remove whitespace
        identifier = identifier.strip()
        
        # Normalize ORCID URLs to standard format
        if 'orcid.org' in identifier.lower():
            # Extract ORCID from URL
            if identifier.startswith('http'):
                identifier = identifier.split('/')[-1]
            # Ensure ORCID format
            if not (identifier.startswith('0000-') or identifier.startswith('0009-')):
                # Try to format as ORCID if it looks like one
                if len(identifier) == 16 and identifier.replace('-', '').isdigit():
                    pass  # Already formatted
                elif len(identifier) == 16:
                    # Add dashes if missing
                    identifier = f"{identifier[:4]}-{identifier[4:8]}-{identifier[8:12]}-{identifier[12:]}"
        
        # Normalize ROR URLs to standard format  
        elif 'ror.org' in identifier.lower():
            # Extract ROR from URL
            if identifier.startswith('http'):
                identifier = identifier.split('/')[-1]
            # Ensure ROR format starts with https://ror.org/
            if not identifier.startswith('https://ror.org/'):
                identifier = f"https://ror.org/{identifier}"
        
        return identifier

    def _load_about_object(self, data):
        """Load an about object (Anatomy, etc.) from JSON data."""
        try:
            schema_key = data.get('schemaKey', '')
            if schema_key == 'Anatomy':
                # Normalize the identifier before creating/getting the anatomy object
                raw_identifier = data.get('identifier', '')
                normalized_identifier = self.normalize_uberon_identifier(raw_identifier)
                
                obj, _ = Anatomy.objects.get_or_create(
                    name=data.get('name', ''),
                    defaults={'identifier': normalized_identifier}
                )
                return obj, 'anatomy'
            # Add other schema keys as needed
            return None, None
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading about object: {e}")
            return None, None

    def _load_access_requirements(self, data):
        """Load access requirements from JSON data."""
        try:
            contact_point = None
            contact_point_data = data.get('contactPoint')
            if contact_point_data:
                contact_point, _ = ContactPoint.objects.get_or_create(
                    email=contact_point_data.get('email', ''),
                    defaults={
                        'url': contact_point_data.get('url', ''),
                    }
                )

            access_req, _ = AccessRequirements.objects.get_or_create(
                status=data.get('status', ''),
                defaults={
                    'contact_point': contact_point,
                    'description': data.get('description', ''),
                    'embargoed_until': parse_datetime(data.get('embargoedUntil')) if data.get('embargoedUntil') else None,
                }
            )
            return access_req
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading access requirements: {e}")
            return None

    def _load_resource(self, data):
        """Load a resource from JSON data."""
        try:
            resource, _ = Resource.objects.get_or_create(
                url=data.get('url', ''),
                defaults={
                    'name': data.get('name', ''),
                    'relation': data.get('relation', ''),
                    'identifier': data.get('identifier', ''),
                    'repository': data.get('repository', ''),
                    'resource_type': data.get('resourceType', ''),
                }
            )
            return resource
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading resource: {e}")
            return None

    def _load_assets_summary(self, data):
        """Load assets summary from JSON data."""
        try:
            # Create a new AssetsSummary for each dandiset
            assets_summary = AssetsSummary.objects.create(
                number_of_bytes=data.get('numberOfBytes', 0),
                number_of_files=data.get('numberOfFiles', 0),
                number_of_subjects=data.get('numberOfSubjects', 0),
                number_of_samples=data.get('numberOfSamples', 0),
                number_of_cells=data.get('numberOfCells', 0),
                variable_measured=data.get('variableMeasured', []),
            )

            # Load species
            for species_data in data.get('species', []):
                species, _ = SpeciesType.objects.get_or_create(
                    name=species_data.get('name', ''),
                    defaults={
                        'identifier': species_data.get('identifier', ''),
                    }
                )
                AssetsSummarySpecies.objects.get_or_create(
                    assets_summary=assets_summary,
                    species=species
                )

            # Load approaches
            for approach_data in data.get('approach', []):
                approach, _ = ApproachType.objects.get_or_create(
                    name=approach_data.get('name', ''),
                    defaults={
                        'identifier': approach_data.get('identifier', ''),
                    }
                )
                AssetsSummaryApproach.objects.get_or_create(
                    assets_summary=assets_summary,
                    approach=approach
                )

            # Load measurement techniques
            for technique_data in data.get('measurementTechnique', []):
                technique, _ = MeasurementTechniqueType.objects.get_or_create(
                    name=technique_data.get('name', ''),
                    defaults={
                        'identifier': technique_data.get('identifier', ''),
                    }
                )
                AssetsSummaryMeasurementTechnique.objects.get_or_create(
                    assets_summary=assets_summary,
                    measurement_technique=technique
                )

            # Load data standards
            for standard_data in data.get('dataStandard', []):
                standard, _ = StandardsType.objects.get_or_create(
                    name=standard_data.get('name', ''),
                    defaults={
                        'identifier': standard_data.get('identifier', ''),
                    }
                )
                AssetsSummaryDataStandard.objects.get_or_create(
                    assets_summary=assets_summary,
                    data_standard=standard
                )

            return assets_summary
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading assets summary: {e}")
            return None

    def _load_activity(self, data):
        """Load an activity from JSON data."""
        try:
            activity, _ = Activity.objects.get_or_create(
                name=data.get('name', ''),
                defaults={
                    'identifier': data.get('id', ''),
                    'schema_key': data.get('schemaKey', ''),
                    'description': data.get('description', ''),
                    'start_date': parse_datetime(data.get('startDate')) if data.get('startDate') else None,
                    'end_date': parse_datetime(data.get('endDate')) if data.get('endDate') else None,
                }
            )

            # Load associated software - now using direct many-to-many relationship
            for software_data in data.get('wasAssociatedWith', []):
                software, _ = Software.objects.get_or_create(
                    name=software_data.get('name', ''),
                    defaults={
                        'identifier': software_data.get('identifier', ''),
                        'version': software_data.get('version', ''),
                        'url': software_data.get('url', ''),
                    }
                )
                activity.software.add(software)

            return activity
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading activity: {e}")
            return None

    def _load_participant(self, data):
        """Load a participant from JSON data."""
        try:
            # Load species
            species = None
            species_data = data.get('species')
            if species_data:
                species, _ = SpeciesType.objects.get_or_create(
                    name=species_data.get('name', ''),
                    defaults={
                        'identifier': species_data.get('identifier', ''),
                    }
                )

            # Load sex
            sex = None
            sex_data = data.get('sex')
            if sex_data:
                sex, _ = SexType.objects.get_or_create(
                    name=sex_data.get('name', ''),
                    defaults={
                        'identifier': sex_data.get('identifier', ''),
                    }
                )

            participant, _ = Participant.objects.get_or_create(
                identifier=data.get('identifier', ''),
                defaults={
                    'species': species,
                    'sex': sex,
                    'age': data.get('age'),
                }
            )
            return participant
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading participant: {e}")
            return None

    def _process_lindi_for_asset(self, asset, sync_tracker=None):
        """Process LINDI metadata for a single NWB asset"""
        try:
            # Check if asset already has LINDI metadata (unless force refresh)
            if hasattr(asset, 'lindi_metadata') and asset.lindi_metadata:
                if self.verbose:
                    self.stdout.write(f"Asset {asset.dandi_asset_id} already has LINDI metadata, skipping")
                self.stats['lindi_skipped'] += 1
                return

            # Construct LINDI URL
            lindi_url = self._construct_lindi_url(asset)
            if not lindi_url:
                if self.verbose:
                    self.stdout.write(f"Could not construct LINDI URL for asset {asset.dandi_asset_id}")
                self.stats['lindi_skipped'] += 1
                return

            # Download and process LINDI file
            lindi_data = self._download_lindi_file(lindi_url)
            if not lindi_data:
                self.stats['lindi_errors'] += 1
                return

            # Filter LINDI data
            filtered_data = self._filter_lindi_data(lindi_data)

            # Save to database
            self._save_lindi_metadata(asset, lindi_url, lindi_data, filtered_data, sync_tracker)
            self.stats['lindi_processed'] += 1

            if self.verbose:
                self.stdout.write(f"Processed LINDI metadata for: {asset.path}")

        except Exception as e:
            self.stats['lindi_errors'] += 1
            if self.verbose:
                self.stdout.write(f"Error processing LINDI for asset {asset.dandi_asset_id}: {e}")

    def _construct_lindi_url(self, asset):
        """Construct the LINDI URL for an asset"""
        try:
            # Get dandiset ID from asset relationships
            if not asset.dandisets.exists():
                return None

            dandiset = asset.dandisets.first()
            dandiset_id = dandiset.base_id.replace('DANDI:', '').zfill(6)

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
