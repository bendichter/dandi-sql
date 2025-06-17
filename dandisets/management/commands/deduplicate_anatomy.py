from typing import Optional
from django.core.management.base import BaseCommand
from django.db import transaction
from dandisets.models import Anatomy, DandisetAbout
import re


class Command(BaseCommand):
    help = 'Deduplicate anatomy objects based on normalized identifiers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def normalize_identifier(self, identifier: Optional[str]) -> Optional[str]:
        """Normalize UBERON identifiers to standard format"""
        if not identifier:
            return identifier
            
        # Convert http://purl.obolibrary.org/obo/UBERON_XXXXXXX to UBERON:XXXXXXX
        match = re.match(r'http://purl\.obolibrary\.org/obo/UBERON_(\d+)', identifier)
        if match:
            return f"UBERON:{match.group(1)}"
            
        return identifier

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
        
        with transaction.atomic():
            # Get all anatomy objects and group by normalized identifier
            anatomy_groups = {}
            
            for anatomy in Anatomy.objects.all():
                normalized_id = self.normalize_identifier(anatomy.identifier)
                
                # Skip empty identifiers
                if not normalized_id:
                    continue
                    
                if normalized_id not in anatomy_groups:
                    anatomy_groups[normalized_id] = []
                anatomy_groups[normalized_id].append(anatomy)
            
            # Process groups with duplicates
            for normalized_id, anatomies in anatomy_groups.items():
                if len(anatomies) <= 1:
                    continue
                    
                self.stdout.write(f"Processing normalized identifier '{normalized_id}' ({len(anatomies)} records)")
                
                # Sort by ID to keep the first one (most likely the original)
                anatomies.sort(key=lambda x: x.id)
                primary = anatomies[0]
                duplicates_to_remove = anatomies[1:]
                
                # Update primary to have the normalized identifier
                if primary.identifier != normalized_id:
                    self.stdout.write(f"  Normalizing primary anatomy ID {primary.id} identifier from '{primary.identifier}' to '{normalized_id}'")
                    if not dry_run:
                        primary.identifier = normalized_id
                        primary.save()
                
                self.stdout.write(f"  Keeping anatomy ID {primary.id}: '{primary.name}' with identifier '{primary.identifier}'")
                
                for duplicate_anatomy in duplicates_to_remove:
                    self.stdout.write(f"  Removing anatomy ID {duplicate_anatomy.id}: '{duplicate_anatomy.name}' with identifier '{duplicate_anatomy.identifier}'")
                    
                    # Update any DandisetAbout records that reference this duplicate
                    dandiset_about_count = DandisetAbout.objects.filter(anatomy=duplicate_anatomy).count()
                    if dandiset_about_count > 0:
                        self.stdout.write(f"    Updating {dandiset_about_count} DandisetAbout references")
                        if not dry_run:
                            DandisetAbout.objects.filter(anatomy=duplicate_anatomy).update(anatomy=primary)
                    
                    # Delete the duplicate
                    if not dry_run:
                        duplicate_anatomy.delete()
                
                self.stdout.write(f"  Completed processing '{normalized_id}'")
            
            if dry_run:
                self.stdout.write("DRY RUN completed - no changes made")
                # Rollback the transaction for dry run
                transaction.set_rollback(True)
            else:
                self.stdout.write("Deduplication completed successfully")
