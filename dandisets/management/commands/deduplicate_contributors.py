import logging
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction
from dandisets.models import Contributor, DandisetContributor, ContributorAffiliation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Deduplicate contributors by ORCID (for persons) or ROR ID (for organizations)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output',
        )
        parser.add_argument(
            '--schema-key',
            type=str,
            choices=['Person', 'Organization', 'Contributor'],
            help='Only deduplicate contributors of specific schema key type',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        schema_key_filter = options.get('schema_key')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Track duplicates by identifier
        orcid_groups = defaultdict(list)  # ORCID -> list of contributor objects
        ror_groups = defaultdict(list)    # ROR -> list of contributor objects
        
        # Get all contributors with identifiers
        contributors_query = Contributor.objects.exclude(identifier__isnull=True).exclude(identifier__exact='')
        
        if schema_key_filter:
            contributors_query = contributors_query.filter(schema_key=schema_key_filter)
        
        contributors = list(contributors_query)
        
        self.stdout.write(f"Analyzing {len(contributors)} contributors with identifiers...")
        
        # Group contributors by their identifiers
        for contributor in contributors:
            identifier = contributor.identifier.strip() if contributor.identifier else ''
            
            if not identifier:
                continue
                
            # Normalize identifier format
            identifier = self._normalize_identifier(identifier)
            
            # Determine if this is an ORCID or ROR identifier
            if self._is_orcid(identifier):
                orcid_groups[identifier].append(contributor)
            elif self._is_ror(identifier):
                ror_groups[identifier].append(contributor)
            elif verbose:
                self.stdout.write(f"Unknown identifier format: {identifier} for contributor {contributor.name}")
        
        # Find groups with duplicates
        duplicate_orcid_groups = {orcid: contribs for orcid, contribs in orcid_groups.items() if len(contribs) > 1}
        duplicate_ror_groups = {ror: contribs for ror, contribs in ror_groups.items() if len(contribs) > 1}
        
        total_duplicates = len(duplicate_orcid_groups) + len(duplicate_ror_groups)
        
        if total_duplicates == 0:
            self.stdout.write(self.style.SUCCESS("No duplicate contributors found!"))
            return
        
        self.stdout.write(f"Found {len(duplicate_orcid_groups)} ORCID groups with duplicates")
        self.stdout.write(f"Found {len(duplicate_ror_groups)} ROR groups with duplicates")
        
        # Process ORCID duplicates
        if duplicate_orcid_groups:
            self.stdout.write("\n=== ORCID Duplicates ===")
            for orcid, contributors_list in duplicate_orcid_groups.items():
                self._process_duplicate_group(orcid, contributors_list, 'ORCID', dry_run, verbose)
        
        # Process ROR duplicates
        if duplicate_ror_groups:
            self.stdout.write("\n=== ROR Duplicates ===")
            for ror, contributors_list in duplicate_ror_groups.items():
                self._process_duplicate_group(ror, contributors_list, 'ROR', dry_run, verbose)
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Deduplication completed! Processed {total_duplicates} duplicate groups."))

    def _normalize_identifier(self, identifier):
        """Normalize identifier format"""
        # Remove whitespace
        identifier = identifier.strip()
        
        # Normalize ORCID URLs to standard format
        if 'orcid.org' in identifier.lower():
            # Extract ORCID from URL
            if identifier.startswith('http'):
                identifier = identifier.split('/')[-1]
            # Ensure ORCID format
            if not identifier.startswith('0000-'):
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

    def _is_orcid(self, identifier):
        """Check if identifier is an ORCID"""
        # ORCID format: 0000-0000-0000-000X or 0009-0000-0000-000X (where X can be a digit or X)
        return ((identifier.startswith('0000-') or identifier.startswith('0009-')) and len(identifier) == 19) or 'orcid.org' in identifier.lower()

    def _is_ror(self, identifier):
        """Check if identifier is a ROR ID"""
        return 'ror.org' in identifier.lower()

    def _process_duplicate_group(self, identifier, contributors_list, id_type, dry_run, verbose):
        """Process a group of duplicate contributors with the same identifier"""
        self.stdout.write(f"\n{id_type} {identifier}:")
        
        # Sort contributors to pick the "canonical" one
        # Prefer: 1) Most recent, 2) Most complete (has email, url, etc), 3) Most relationships
        canonical = self._choose_canonical_contributor(contributors_list, verbose)
        duplicates = [c for c in contributors_list if c.id != canonical.id]
        
        self.stdout.write(f"  Canonical: {canonical.name} (ID: {canonical.id})")
        if verbose:
            self.stdout.write(f"    Email: {canonical.email or 'None'}")
            self.stdout.write(f"    URL: {canonical.url or 'None'}")
            self.stdout.write(f"    Schema Key: {canonical.schema_key}")
            # Show roles from relationships
            canonical_roles = []
            for rel in DandisetContributor.objects.filter(contributor=canonical):
                if rel.role_name:
                    canonical_roles.extend(rel.role_name if isinstance(rel.role_name, list) else [rel.role_name])
            self.stdout.write(f"    Role Names: {canonical_roles}")
        
        for duplicate in duplicates:
            self.stdout.write(f"  Duplicate: {duplicate.name} (ID: {duplicate.id})")
            if verbose:
                self.stdout.write(f"    Email: {duplicate.email or 'None'}")
                self.stdout.write(f"    URL: {duplicate.url or 'None'}")
                self.stdout.write(f"    Schema Key: {duplicate.schema_key}")
                # Show roles from relationships
                duplicate_roles = []
                for rel in DandisetContributor.objects.filter(contributor=duplicate):
                    if rel.role_name:
                        duplicate_roles.extend(rel.role_name if isinstance(rel.role_name, list) else [rel.role_name])
                self.stdout.write(f"    Role Names: {duplicate_roles}")
        
        if not dry_run:
            self._merge_contributors(canonical, duplicates, verbose)

    def _choose_canonical_contributor(self, contributors_list, verbose):
        """Choose the canonical contributor from a list of duplicates"""
        # Score each contributor based on completeness and recency
        def score_contributor(contrib):
            score = 0
            
            # More recent creation gets higher score
            if hasattr(contrib, 'created_at') and contrib.created_at:
                # Use days since epoch as score component
                score += contrib.created_at.timestamp() / 86400
            
            # Completeness score
            if contrib.email:
                score += 10
            if contrib.url:
                score += 5
            if contrib.schema_key and contrib.schema_key != 'Contributor':
                score += 5  # More specific schema key is better
            
            # Relationship count (more relationships = more established)
            try:
                dandiset_relationships = DandisetContributor.objects.filter(contributor=contrib)
                dandiset_count = dandiset_relationships.count()
                
                # Count total roles across all relationships
                total_roles = 0
                for rel in dandiset_relationships:
                    if rel.role_name:
                        total_roles += len(rel.role_name) if isinstance(rel.role_name, list) else 1
                
                affiliation_count = ContributorAffiliation.objects.filter(contributor=contrib).count()
                score += dandiset_count * 2 + affiliation_count + total_roles
            except:
                pass
            
            return score
        
        # Sort by score (highest first)
        scored_contributors = [(score_contributor(c), c) for c in contributors_list]
        scored_contributors.sort(key=lambda x: x[0], reverse=True)
        
        if verbose:
            self.stdout.write("    Scoring:")
            for score, contrib in scored_contributors:
                self.stdout.write(f"      {contrib.name} (ID: {contrib.id}): {score:.1f}")
        
        return scored_contributors[0][1]  # Return contributor with highest score

    def _merge_contributors(self, canonical, duplicates, verbose):
        """Merge duplicate contributors into the canonical one"""
        with transaction.atomic():
            for duplicate in duplicates:
                if verbose:
                    self.stdout.write(f"    Merging {duplicate.name} (ID: {duplicate.id}) into canonical...")
                
                # Update all DandisetContributor relationships
                duplicate_relationships = DandisetContributor.objects.filter(contributor=duplicate)
                for rel in duplicate_relationships:
                    # Check if canonical already has this relationship
                    existing, created = DandisetContributor.objects.get_or_create(
                        dandiset=rel.dandiset,
                        contributor=canonical
                    )
                    if created and verbose:
                        self.stdout.write(f"      Moved relationship to dandiset {rel.dandiset.dandi_id}")
                    elif verbose:
                        self.stdout.write(f"      Relationship to dandiset {rel.dandiset.dandi_id} already exists")
                    
                    # Delete the duplicate relationship
                    rel.delete()
                
                # Update ContributorAffiliation relationships
                duplicate_affiliations = ContributorAffiliation.objects.filter(contributor=duplicate)
                for affil_rel in duplicate_affiliations:
                    # Check if canonical already has this affiliation
                    existing, created = ContributorAffiliation.objects.get_or_create(
                        contributor=canonical,
                        affiliation=affil_rel.affiliation
                    )
                    if created and verbose:
                        self.stdout.write(f"      Moved affiliation to {affil_rel.affiliation.name}")
                    elif verbose:
                        self.stdout.write(f"      Affiliation to {affil_rel.affiliation.name} already exists")
                    
                    # Delete the duplicate relationship
                    affil_rel.delete()
                
                # Merge data from duplicate into canonical if canonical is missing data
                updated_fields = []
                
                if not canonical.email and duplicate.email:
                    canonical.email = duplicate.email
                    updated_fields.append('email')
                
                if not canonical.url and duplicate.url:
                    canonical.url = duplicate.url
                    updated_fields.append('url')
                
                # Note: Role names are now stored in DandisetContributor relationships,
                # so they are handled when we move the relationships above
                
                if not canonical.award_number and duplicate.award_number:
                    canonical.award_number = duplicate.award_number
                    updated_fields.append('award_number')
                
                # Use more specific schema_key if available
                if canonical.schema_key == 'Contributor' and duplicate.schema_key in ['Person', 'Organization']:
                    canonical.schema_key = duplicate.schema_key
                    updated_fields.append('schema_key')
                
                if updated_fields:
                    canonical.save()
                    if verbose:
                        self.stdout.write(f"      Updated canonical with fields: {', '.join(updated_fields)}")
                
                # Delete the duplicate contributor
                duplicate.delete()
                if verbose:
                    self.stdout.write(f"      Deleted duplicate contributor {duplicate.name}")
