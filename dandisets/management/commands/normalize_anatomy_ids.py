from django.core.management.base import BaseCommand
from django.db import transaction
from dandisets.models import Anatomy
import re


class Command(BaseCommand):
    help = 'Normalize all anatomy identifiers from URL format to UBERON:XXXXXXX format'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def normalize_identifier(self, identifier):
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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
        
        updated_count = 0
        
        with transaction.atomic():
            for anatomy in Anatomy.objects.all():
                original_id = anatomy.identifier
                normalized_id = self.normalize_identifier(original_id)
                
                if original_id != normalized_id:
                    self.stdout.write(f"Anatomy ID {anatomy.id}: '{anatomy.name}'")
                    self.stdout.write(f"  From: '{original_id}'")
                    self.stdout.write(f"  To:   '{normalized_id}'")
                    
                    if not dry_run:
                        anatomy.identifier = normalized_id
                        anatomy.save()
                    
                    updated_count += 1
            
            if updated_count == 0:
                self.stdout.write("No anatomy identifiers needed normalization")
            else:
                self.stdout.write(f"{'Would update' if dry_run else 'Updated'} {updated_count} anatomy identifiers")
            
            if dry_run:
                self.stdout.write("DRY RUN completed - no changes made")
                # Rollback the transaction for dry run
                transaction.set_rollback(True)
            else:
                self.stdout.write("Normalization completed successfully")
