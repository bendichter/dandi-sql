import json
import re
import time
from datetime import datetime, timezone
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.db.models import Q
from tqdm import tqdm
from dandi.dandiapi import DandiAPIClient

from dandisets.models import (
    Dandiset, Contributor, SpeciesType, ApproachType, 
    MeasurementTechniqueType, StandardsType, AssetsSummary,
    ContactPoint, AccessRequirements, Activity, Resource,
    Anatomy, GenericType, Disorder, DandisetContributor,
    DandisetAbout, DandisetAccessRequirements, DandisetRelatedResource,
    AssetsSummarySpecies, AssetsSummaryApproach, AssetsSummaryDataStandard,
    AssetsSummaryMeasurementTechnique, Affiliation, ContributorAffiliation,
    Software, ActivityAssociation, Asset, Participant, AssetAccess,
    AssetApproach, AssetMeasurementTechnique, AssetWasAttributedTo,
    AssetWasGeneratedBy, SexType, AssetDandiset, SyncTracker
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
            'assets_checked': 0,
            'assets_updated': 0,
            'assets_skipped': 0,
            'errors': 0,
        }
        self.dry_run = False
        self.verbose = False

    def normalize_uberon_identifier(self, identifier):
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

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        self.no_progress = options['no_progress']
        
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
            
            # Perform unified sync - iterate through dandisets and handle both metadata and assets
            self._sync_dandisets_and_assets(last_sync_time, options, sync_scope, sync_tracker)
            
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
        """Get the last sync timestamp"""
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
        
        # Get last sync from database
        try:
            last_sync = SyncTracker.objects.latest()
            return last_sync.last_sync_timestamp
        except SyncTracker.DoesNotExist:
            return None

    def _sync_dandisets_and_assets(self, last_sync_time, options, sync_scope, sync_tracker=None):
        """Unified sync method that iterates through dandisets and handles both metadata and assets"""
        self.stdout.write("Fetching dandisets from DANDI API...")
        
        # Get dandisets from API
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
        
        # Filter dandisets that need updating
        dandisets_to_process = []
        
        filter_desc = "Checking dandisets for updates"
        if self.no_progress:
            for api_dandiset in api_dandisets:
                if self._dandiset_needs_update(api_dandiset, last_sync_time):
                    dandisets_to_process.append(api_dandiset)
                self.stats['dandisets_checked'] += 1
        else:
            with tqdm(api_dandisets, desc=filter_desc, unit="dandiset") as pbar:
                for api_dandiset in pbar:
                    pbar.set_postfix(current=api_dandiset.identifier)
                    if self._dandiset_needs_update(api_dandiset, last_sync_time):
                        dandisets_to_process.append(api_dandiset)
                    self.stats['dandisets_checked'] += 1
        
        self.stdout.write(f"Found {len(dandisets_to_process)} dandisets to process")
        
        if not dandisets_to_process:
            self.stdout.write("No dandisets need updates")
            return
        
        # Process each dandiset (both metadata and assets)
        process_desc = "Processing dandisets and assets"
        if self.no_progress:
            for api_dandiset in dandisets_to_process:
                self._process_dandiset_and_assets(api_dandiset, last_sync_time, options, sync_scope, sync_tracker)
        else:
            with tqdm(dandisets_to_process, desc=process_desc, unit="dandiset") as pbar:
                for api_dandiset in pbar:
                    pbar.set_postfix(current=api_dandiset.identifier)
                    self._process_dandiset_and_assets(api_dandiset, last_sync_time, options, sync_scope, sync_tracker)

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
                return
            
            # Apply max assets limit
            max_assets = options.get('max_assets', 2000)
            if len(api_assets) > max_assets:
                if self.verbose:
                    self.stdout.write(f"Limiting assets for {api_dandiset.identifier} to {max_assets} (total: {len(api_assets)})")
                api_assets = api_assets[:max_assets]
            
            # Process assets - filter and update in one pass
            assets_updated = 0
            asset_desc = f"Processing assets for {api_dandiset.identifier}"
            
            if self.no_progress:
                for asset in api_assets:
                    if self._asset_needs_update(asset, last_sync_time):
                        self._update_asset(asset, local_dandiset, sync_tracker)
                        assets_updated += 1
                    self.stats['assets_checked'] += 1
            else:
                with tqdm(api_assets, desc=asset_desc, unit="asset", leave=False) as asset_pbar:
                    for asset in asset_pbar:
                        asset_path = getattr(asset, 'path', 'unknown')
                        short_path = asset_path[:30] + '...' if len(asset_path) > 30 else asset_path
                        asset_pbar.set_postfix(asset=short_path)
                        
                        if self._asset_needs_update(asset, last_sync_time):
                            self._update_asset(asset, local_dandiset, sync_tracker)
                            assets_updated += 1
                        self.stats['assets_checked'] += 1
            
            if self.verbose and assets_updated > 0:
                self.stdout.write(f"Updated {assets_updated} assets for {api_dandiset.identifier}")
                
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
                        asset_path = getattr(asset, 'path', 'unknown')
                        asset_pbar.set_postfix(asset=asset_path[:30] + '...' if len(asset_path) > 30 else asset_path)
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
                        asset_path = getattr(asset, 'path', 'unknown')
                        update_pbar.set_postfix(asset=asset_path[:30] + '...' if len(asset_path) > 30 else asset_path)
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
                self._load_asset(metadata, dandiset, sync_tracker)
                self.stats['assets_updated'] += 1
                
        except Exception as e:
            self.stats['errors'] += 1
            if self.verbose:
                asset_path = getattr(api_asset, 'path', 'unknown')
                self.stdout.write(f"Error updating asset {asset_path}: {e}")

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
        self.stdout.write("SYNC SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Duration: {duration:.2f} seconds")
        self.stdout.write(f"Dandisets checked: {self.stats['dandisets_checked']}")
        self.stdout.write(f"Dandisets updated: {self.stats['dandisets_updated']}")
        self.stdout.write(f"Assets checked: {self.stats['assets_checked']}")
        self.stdout.write(f"Assets updated: {self.stats['assets_updated']}")
        self.stdout.write(f"Errors: {self.stats['errors']}")
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made"))
        else:
            self.stdout.write(self.style.SUCCESS("Sync completed successfully"))

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
                'schema_key': data.get('schemaKey', ''),
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

        # Load about section
        for about_data in data.get('about', []):
            about_obj, field_name = self._load_about_object(about_data)
            if about_obj and field_name:
                kwargs = {
                    'dandiset': dandiset,
                    field_name: about_obj
                }
                DandisetAbout.objects.get_or_create(**kwargs)

        # Load access requirements
        for access_data in data.get('access', []):
            access_req = self._load_access_requirements(access_data)
            if access_req:
                DandisetAccessRequirements.objects.get_or_create(
                    dandiset=dandiset,
                    access_requirement=access_req
                )

        # Load related resources
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
                'path': data.get('path', ''),
                'content_size': data.get('contentSize', 0),
                'encoding_format': data.get('encodingFormat', ''),
                'schema_key': data.get('schemaKey', 'Asset'),
                'schema_version': data.get('schemaVersion', '0.6.7'),
                'date_modified': parse_datetime(data.get('dateModified')) if data.get('dateModified') else None,
                'date_published': parse_datetime(data.get('datePublished')) if data.get('datePublished') else None,
                'blob_date_modified': parse_datetime(data.get('blobDateModified')) if data.get('blobDateModified') else None,
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
            self.stdout.write(f"{action} asset: {asset.path}")

        # Create the asset-dandiset relationship
        AssetDandiset.objects.get_or_create(
            asset=asset,
            dandiset=dandiset,
            defaults={'is_primary': True}
        )

        # Load access requirements
        for access_data in data.get('access', []):
            access_req = self._load_access_requirements(access_data)
            if access_req:
                AssetAccess.objects.get_or_create(
                    asset=asset,
                    access_requirement=access_req
                )

        # Load approaches
        for approach_data in data.get('approach', []):
            approach, _ = ApproachType.objects.get_or_create(
                name=approach_data.get('name', ''),
                defaults={
                    'identifier': approach_data.get('identifier', ''),
                    'schema_key': approach_data.get('schemaKey', ''),
                }
            )
            AssetApproach.objects.get_or_create(
                asset=asset,
                approach=approach
            )

        # Load measurement techniques
        for technique_data in data.get('measurementTechnique', []):
            technique, _ = MeasurementTechniqueType.objects.get_or_create(
                name=technique_data.get('name', ''),
                defaults={
                    'identifier': technique_data.get('identifier', ''),
                    'schema_key': technique_data.get('schemaKey', ''),
                }
            )
            AssetMeasurementTechnique.objects.get_or_create(
                asset=asset,
                measurement_technique=technique
            )

        # Load participants (wasAttributedTo)
        for participant_data in data.get('wasAttributedTo', []):
            participant = self._load_participant(participant_data)
            if participant:
                AssetWasAttributedTo.objects.get_or_create(
                    asset=asset,
                    participant=participant
                )

        # Load activities that generated this asset
        for activity_data in data.get('wasGeneratedBy', []):
            activity = self._load_activity(activity_data)
            if activity:
                AssetWasGeneratedBy.objects.get_or_create(
                    asset=asset,
                    activity=activity
                )

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
        """Load a contributor from JSON data."""
        try:
            name = data.get('name', '')
            identifier = data.get('identifier', '').strip() if data.get('identifier') else ''
            
            # Try to find existing contributor by identifier first (if provided)
            contributor = None
            if identifier:
                # Normalize identifier
                identifier = self._normalize_contributor_identifier(identifier)
                
                # Look for existing contributor with this identifier
                existing_contributors = Contributor.objects.filter(identifier=identifier)
                if existing_contributors.exists():
                    contributor = existing_contributors.first()
                    if self.verbose:
                        self.stdout.write(f"Found existing contributor by identifier {identifier}: {contributor.name}")
            
            # If no contributor found by identifier, try by name
            if not contributor:
                contributor, created = Contributor.objects.get_or_create(
                    name=name,
                    defaults={
                        'email': data.get('email', ''),
                        'identifier': identifier,
                        'schema_key': data.get('schemaKey', ''),
                        'award_number': data.get('awardNumber', ''),
                        'url': data.get('url', ''),
                    }
                )
                if created and self.verbose:
                    self.stdout.write(f"Created new contributor: {name}")
            else:
                # Update existing contributor with any missing information
                updated = False
                if not contributor.email and data.get('email'):
                    contributor.email = data.get('email')
                    updated = True
                if not contributor.url and data.get('url'):
                    contributor.url = data.get('url')
                    updated = True
                if not contributor.award_number and data.get('awardNumber'):
                    contributor.award_number = data.get('awardNumber')
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
                        'schema_key': affiliation_data.get('schemaKey', ''),
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
            return None

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
                        'schema_key': contact_point_data.get('schemaKey', ''),
                    }
                )

            access_req, _ = AccessRequirements.objects.get_or_create(
                status=data.get('status', ''),
                defaults={
                    'schema_key': data.get('schemaKey', ''),
                    'contact_point': contact_point,
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
                    'schema_key': data.get('schemaKey', ''),
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
                schema_key=data.get('schemaKey', ''),
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
                        'schema_key': species_data.get('schemaKey', ''),
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
                        'schema_key': approach_data.get('schemaKey', ''),
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
                        'schema_key': technique_data.get('schemaKey', ''),
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
                        'schema_key': standard_data.get('schemaKey', ''),
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

            # Load associated software
            for software_data in data.get('wasAssociatedWith', []):
                software, _ = Software.objects.get_or_create(
                    name=software_data.get('name', ''),
                    defaults={
                        'identifier': software_data.get('identifier', ''),
                        'schema_key': software_data.get('schemaKey', ''),
                        'version': software_data.get('version', ''),
                        'url': software_data.get('url', ''),
                    }
                )
                ActivityAssociation.objects.get_or_create(
                    activity=activity,
                    software=software
                )

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
                        'schema_key': species_data.get('schemaKey', ''),
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
                        'schema_key': sex_data.get('schemaKey', ''),
                    }
                )

            participant, _ = Participant.objects.get_or_create(
                identifier=data.get('identifier', ''),
                defaults={
                    'species': species,
                    'sex': sex,
                    'age': data.get('age'),
                    'schema_key': data.get('schemaKey', 'Participant'),
                }
            )
            return participant
        except Exception as e:
            if self.verbose:
                self.stdout.write(f"Error loading participant: {e}")
            return None
