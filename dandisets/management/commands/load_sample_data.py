import json
import re
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
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
    AssetWasGeneratedBy, SexType, AssetDandiset
)


class Command(BaseCommand):
    help = 'Load sample DANDI metadata into the database'

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
            '--file',
            type=str,
            help='Path to JSON file containing the data to load',
            default='/Users/bdichter/dev/sandbox/dandi-metadata.json'
        )
        parser.add_argument(
            '--asset-file',
            type=str,
            help='Path to JSON file containing asset data to load',
            default='/Users/bdichter/dev/sandbox/asset_metadata.json'
        )

    def handle(self, *args, **options):
        try:
            # Load dandisets first
            file_path = options['file']
            self.stdout.write(f"Loading dandisets from: {file_path}")
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            self.stdout.write(f"Loading {len(data)} dandisets...")
            
            for item in data:
                self.load_dandiset(item)
                
            self.stdout.write(
                self.style.SUCCESS(f'Successfully loaded {len(data)} dandisets')
            )

            # Load assets
            asset_file_path = options['asset_file']
            try:
                self.stdout.write(f"Loading assets from: {asset_file_path}")
                
                with open(asset_file_path, 'r') as f:
                    asset_data = json.load(f)
                
                self.stdout.write(f"Loading {len(asset_data)} assets...")
                
                for asset_item in asset_data:
                    # Find the dandiset for this asset using the dandiset_id field
                    dandiset_id = asset_item.get('dandiset_id')
                    if dandiset_id:
                        try:
                            # Try to find dandiset by base_id (e.g., "DANDI:000003" should match dandiset_id "000003")
                            dandiset = Dandiset.objects.filter(base_id__endswith=dandiset_id).first()
                            if dandiset:
                                self.load_asset(asset_item, dandiset)
                            else:
                                self.stdout.write(f"Could not find dandiset for asset with dandiset_id: {dandiset_id}")
                        except Exception as e:
                            self.stdout.write(f"Error finding dandiset for asset: {e}")
                    else:
                        self.stdout.write(f"Asset missing dandiset_id: {asset_item.get('path', '')}")
                
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully loaded assets')
                )
            except FileNotFoundError:
                self.stdout.write(
                    self.style.WARNING(f'Asset file not found: {asset_file_path} - skipping assets')
                )
            except json.JSONDecodeError as e:
                self.stdout.write(
                    self.style.ERROR(f'Invalid JSON in asset file: {str(e)}')
                )
                
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'File not found: {options["file"]}')
            )
        except json.JSONDecodeError as e:
            self.stdout.write(
                self.style.ERROR(f'Invalid JSON in file: {str(e)}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading data: {str(e)}')
            )

    def load_dandiset(self, data):
        """Load a single dandiset from JSON data."""
        # Extract version information from the ID
        full_id = data.get('id', '')  # Full ID like "DANDI:000003/0.230629.1955"
        identifier = data.get('identifier', '')  # Base ID like "DANDI:000003"
        version = data.get('version', '')
        
        # Determine if this is a draft (no version)
        is_draft = not bool(version)
        version_order = 0 if is_draft else 1  # Default to 1 for published versions
        
        # Create or get the dandiset
        dandiset, created = Dandiset.objects.get_or_create(
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
                'date_published': parse_datetime(data.get('datePublished')) if data.get('datePublished') else None,
                'license': data.get('license', []),
                'keywords': data.get('keywords', []),
                'study_target': data.get('studyTarget', []),
                'protocol': data.get('protocol', []),
                'acknowledgement': data.get('acknowledgement', ''),
                'manifest_location': data.get('manifestLocation', []),
            }
        )

        if created:
            self.stdout.write(f"Created dandiset: {dandiset.name}")
        else:
            self.stdout.write(f"Updated dandiset: {dandiset.name}")

        # Load contributors
        for contributor_data in data.get('contributor', []):
            contributor = self.load_contributor(contributor_data)
            if contributor:
                # Create the relationship
                DandisetContributor.objects.get_or_create(
                    dandiset=dandiset,
                    contributor=contributor
                )

        # Load about section
        for about_data in data.get('about', []):
            about_obj, field_name = self.load_about_object(about_data)
            if about_obj and field_name:
                kwargs = {
                    'dandiset': dandiset,
                    field_name: about_obj
                }
                DandisetAbout.objects.get_or_create(**kwargs)

        # Load access requirements
        for access_data in data.get('access', []):
            access_req = self.load_access_requirements(access_data)
            if access_req:
                DandisetAccessRequirements.objects.get_or_create(
                    dandiset=dandiset,
                    access_requirement=access_req
                )

        # Load related resources
        for resource_data in data.get('relatedResource', []):
            resource = self.load_resource(resource_data)
            if resource:
                DandisetRelatedResource.objects.get_or_create(
                    dandiset=dandiset,
                    resource=resource
                )

        # Load assets summary
        assets_summary_data = data.get('assetsSummary')
        if assets_summary_data:
            assets_summary = self.load_assets_summary(assets_summary_data)
            if assets_summary:
                dandiset.assets_summary = assets_summary
                dandiset.save()

        # Load published by activity
        published_by_data = data.get('publishedBy')
        if published_by_data:
            activity = self.load_activity(published_by_data)
            if activity:
                dandiset.published_by = activity
                dandiset.save()

    def load_contributor(self, data):
        """Load a contributor from JSON data."""
        try:
            contributor, created = Contributor.objects.get_or_create(
                name=data.get('name', ''),
                defaults={
                    'email': data.get('email', ''),
                    'identifier': data.get('identifier', ''),
                    'schema_key': data.get('schemaKey', ''),
                    'role_name': data.get('roleName', []),
                    'include_in_citation': data.get('includeInCitation', False),
                    'award_number': data.get('awardNumber', ''),
                    'url': data.get('url', ''),
                }
            )

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
            self.stdout.write(f"Error loading contributor: {e}")
            return None

    def load_about_object(self, data):
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
            self.stdout.write(f"Error loading about object: {e}")
            return None, None

    def load_access_requirements(self, data):
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
            self.stdout.write(f"Error loading access requirements: {e}")
            return None

    def load_resource(self, data):
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
            self.stdout.write(f"Error loading resource: {e}")
            return None

    def load_assets_summary(self, data):
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
            self.stdout.write(f"Error loading assets summary: {e}")
            return None

    def load_activity(self, data):
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
            self.stdout.write(f"Error loading activity: {e}")
            return None

    def load_asset(self, data, dandiset):
        """Load an asset from JSON data."""
        try:
            # Extract asset ID from the full ID
            asset_id = data.get('identifier', '')
            if not asset_id:
                # Try to extract from id field like "dandiasset:a0a7ee60-6e67-42fa-aa88-d31b6b2cb95c"
                full_id = data.get('id', '')
                if ':' in full_id:
                    asset_id = full_id.split(':', 1)[1]
                else:
                    asset_id = full_id

            asset, created = Asset.objects.get_or_create(
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
                }
            )

            if created:
                self.stdout.write(f"Created asset: {asset.path}")
            else:
                self.stdout.write(f"Updated asset: {asset.path}")

            # Create the asset-dandiset relationship
            AssetDandiset.objects.get_or_create(
                asset=asset,
                dandiset=dandiset,
                defaults={'is_primary': True}
            )

            # Load access requirements
            for access_data in data.get('access', []):
                access_req = self.load_access_requirements(access_data)
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
                participant = self.load_participant(participant_data)
                if participant:
                    AssetWasAttributedTo.objects.get_or_create(
                        asset=asset,
                        participant=participant
                    )

            # Load activities that generated this asset
            for activity_data in data.get('wasGeneratedBy', []):
                activity = self.load_activity(activity_data)
                if activity:
                    AssetWasGeneratedBy.objects.get_or_create(
                        asset=asset,
                        activity=activity
                    )

            # Load published by activity
            published_by_data = data.get('publishedBy')
            if published_by_data:
                activity = self.load_activity(published_by_data)
                if activity:
                    asset.published_by = activity
                    asset.save()

            return asset
        except Exception as e:
            self.stdout.write(f"Error loading asset: {e}")
            return None

    def load_participant(self, data):
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
            self.stdout.write(f"Error loading participant: {e}")
            return None
