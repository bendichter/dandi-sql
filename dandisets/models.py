from django.db import models
from django.contrib.postgres.fields import ArrayField
import json


class BaseType(models.Model):
    """Base class for enumerated types"""
    identifier = models.TextField(blank=True, null=True, help_text="The identifier can be any url or a compact URI")
    name = models.CharField(max_length=500, blank=True, null=True, help_text="The name of the item")
    schema_key = models.CharField(max_length=50, default="BaseType")
    
    class Meta:
        abstract = True
    
    def __str__(self):
        return self.name or self.identifier or str(self.pk)


class SpeciesType(BaseType):
    """Identifier for species of the sample"""
    schema_key = models.CharField(max_length=50, default="SpeciesType")
    
    class Meta(BaseType.Meta):
        verbose_name_plural = "Species"


class ApproachType(BaseType):
    """Identifier for approach used"""
    schema_key = models.CharField(max_length=50, default="ApproachType")


class MeasurementTechniqueType(BaseType):
    """Identifier for measurement technique used"""
    schema_key = models.CharField(max_length=50, default="MeasurementTechniqueType")


class StandardsType(BaseType):
    """Identifier for data standard used"""
    schema_key = models.CharField(max_length=50, default="StandardsType")


class AssayType(BaseType):
    """OBI based identifier for the assay(s) used"""
    schema_key = models.CharField(max_length=50, default="AssayType")


class SampleType(BaseType):
    """OBI based identifier for the sample type used"""
    schema_key = models.CharField(max_length=50, default="SampleType")


class Anatomy(BaseType):
    """UBERON or other identifier for anatomical part studied"""
    schema_key = models.CharField(max_length=50, default="Anatomy")


class StrainType(BaseType):
    """Identifier for the strain of the sample"""
    schema_key = models.CharField(max_length=50, default="StrainType")


class SexType(BaseType):
    """Identifier for the sex of the sample"""
    schema_key = models.CharField(max_length=50, default="SexType")


class Disorder(BaseType):
    """Biolink, SNOMED, or other identifier for disorder studied"""
    dx_date = models.JSONField(blank=True, null=True, help_text="Dates of diagnosis")
    schema_key = models.CharField(max_length=50, default="Disorder")


class GenericType(BaseType):
    """An object to capture any type for about"""
    schema_key = models.CharField(max_length=50, default="GenericType")


class ContactPoint(models.Model):
    """Contact point information"""
    email = models.EmailField(blank=True, null=True, help_text="Email address of contact")
    url = models.URLField(blank=True, null=True, help_text="A Web page to find information on how to contact")
    schema_key = models.CharField(max_length=50, default="ContactPoint")
    
    def __str__(self):
        return self.email or self.url or "Contact Point"


class Affiliation(models.Model):
    """Affiliation information"""
    identifier = models.TextField(blank=True, null=True, help_text="A ror.org identifier for institutions")
    name = models.TextField(help_text="Name of organization")
    schema_key = models.CharField(max_length=50, default="Affiliation")
    
    def __str__(self):
        return self.name


class Contributor(models.Model):
    """Contributors (people or organizations) to a dandiset"""
    SCHEMA_KEY_CHOICES = [
        ('Person', 'Person'),
        ('Organization', 'Organization'),
        ('Contributor', 'Contributor'),
    ]
    
    identifier = models.TextField(blank=True, null=True, help_text="Use a common identifier such as ORCID for people or ROR for institutions")
    name = models.TextField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    role_name = models.JSONField(default=list, blank=True, help_text="Role(s) of the contributor")
    include_in_citation = models.BooleanField(default=True, help_text="Include contributor in citation")
    award_number = models.TextField(blank=True, null=True, help_text="Identifier associated with a sponsored or gift award")
    schema_key = models.CharField(max_length=20, choices=SCHEMA_KEY_CHOICES, default='Contributor')
    contact_point = models.JSONField(default=list, blank=True, help_text="Organization contact information")
    
    def __str__(self):
        return f"{self.name} ({self.schema_key})"


class ContributorAffiliation(models.Model):
    """Many-to-many relationship between contributors and affiliations"""
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    affiliation = models.ForeignKey(Affiliation, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['contributor', 'affiliation']


class Software(models.Model):
    """Software information"""
    identifier = models.TextField(blank=True, null=True, help_text="RRID of the software from scicrunch.org")
    name = models.TextField()
    version = models.CharField(max_length=100)
    url = models.URLField(blank=True, null=True, help_text="Web page for the software")
    schema_key = models.CharField(max_length=50, default="Software")
    
    def __str__(self):
        return f"{self.name} v{self.version}"


class Agent(models.Model):
    """Agent information"""
    identifier = models.TextField(blank=True, null=True, help_text="Identifier for an agent")
    name = models.TextField()
    url = models.URLField(blank=True, null=True)
    schema_key = models.CharField(max_length=50, default="Agent")
    
    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Equipment information"""
    identifier = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=150, help_text="A name for the equipment")
    description = models.TextField(blank=True, null=True, help_text="The description of the equipment")
    schema_key = models.CharField(max_length=50, default="Equipment")
    
    def __str__(self):
        return self.name


class Activity(models.Model):
    """Information about the Project activity"""
    SCHEMA_KEY_CHOICES = [
        ('Activity', 'Activity'),
        ('Project', 'Project'),
        ('Session', 'Session'),
        ('PublishActivity', 'PublishActivity'),
    ]
    
    identifier = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=150, help_text="The name of the activity")
    description = models.TextField(blank=True, null=True, help_text="The description of the activity")
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    schema_key = models.CharField(max_length=20, choices=SCHEMA_KEY_CHOICES, default='Activity')
    
    def __str__(self):
        return f"{self.name} ({self.schema_key})"


class ActivityAssociation(models.Model):
    """Association between activities and contributors/software/agents"""
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='associations')
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE, blank=True, null=True)
    software = models.ForeignKey(Software, on_delete=models.CASCADE, blank=True, null=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, blank=True, null=True)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(contributor__isnull=False) & 
                    models.Q(software__isnull=True) & 
                    models.Q(agent__isnull=True)
                ) | (
                    models.Q(contributor__isnull=True) & 
                    models.Q(software__isnull=False) & 
                    models.Q(agent__isnull=True)
                ) | (
                    models.Q(contributor__isnull=True) & 
                    models.Q(software__isnull=True) & 
                    models.Q(agent__isnull=False)
                ),
                name='only_one_association_type'
            )
        ]


class ActivityEquipment(models.Model):
    """Equipment used in activities"""
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='equipment_used')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['activity', 'equipment']


class EthicsApproval(models.Model):
    """Information about ethics committee approval for project"""
    identifier = models.TextField(help_text="Approved Protocol identifier")
    contact_point = models.ForeignKey(ContactPoint, on_delete=models.SET_NULL, blank=True, null=True)
    schema_key = models.CharField(max_length=50, default="EthicsApproval")
    
    def __str__(self):
        return f"Ethics Approval: {self.identifier}"


class AccessRequirements(models.Model):
    """Information about access options for the dataset"""
    ACCESS_STATUS_CHOICES = [
        ('dandi:OpenAccess', 'Open Access'),
        ('dandi:EmbargoedAccess', 'Embargoed Access'),
    ]
    
    status = models.CharField(max_length=30, choices=ACCESS_STATUS_CHOICES, help_text="The access status of the item")
    contact_point = models.ForeignKey(ContactPoint, on_delete=models.SET_NULL, blank=True, null=True)
    description = models.TextField(blank=True, null=True, help_text="Information about access requirements")
    embargoed_until = models.DateField(blank=True, null=True, help_text="Date on which embargo ends")
    schema_key = models.CharField(max_length=50, default="AccessRequirements")
    
    def __str__(self):
        return self.status


class Resource(models.Model):
    """Related resources for a dandiset"""
    RELATION_CHOICES = [
        ('dcite:IsCitedBy', 'Is Cited By'),
        ('dcite:Cites', 'Cites'),
        ('dcite:IsSupplementTo', 'Is Supplement To'),
        ('dcite:IsSupplementedBy', 'Is Supplemented By'),
        ('dcite:IsContinuedBy', 'Is Continued By'),
        ('dcite:Continues', 'Continues'),
        ('dcite:Describes', 'Describes'),
        ('dcite:IsDescribedBy', 'Is Described By'),
        ('dcite:HasMetadata', 'Has Metadata'),
        ('dcite:IsMetadataFor', 'Is Metadata For'),
        ('dcite:HasVersion', 'Has Version'),
        ('dcite:IsVersionOf', 'Is Version Of'),
        ('dcite:IsNewVersionOf', 'Is New Version Of'),
        ('dcite:IsPreviousVersionOf', 'Is Previous Version Of'),
        ('dcite:IsPartOf', 'Is Part Of'),
        ('dcite:HasPart', 'Has Part'),
        ('dcite:IsReferencedBy', 'Is Referenced By'),
        ('dcite:References', 'References'),
        ('dcite:IsDocumentedBy', 'Is Documented By'),
        ('dcite:Documents', 'Documents'),
        ('dcite:IsCompiledBy', 'Is Compiled By'),
        ('dcite:Compiles', 'Compiles'),
        ('dcite:IsVariantFormOf', 'Is Variant Form Of'),
        ('dcite:IsOriginalFormOf', 'Is Original Form Of'),
        ('dcite:IsIdenticalTo', 'Is Identical To'),
        ('dcite:IsReviewedBy', 'Is Reviewed By'),
        ('dcite:Reviews', 'Reviews'),
        ('dcite:IsDerivedFrom', 'Is Derived From'),
        ('dcite:IsSourceOf', 'Is Source Of'),
        ('dcite:IsRequiredBy', 'Is Required By'),
        ('dcite:Requires', 'Requires'),
        ('dcite:Obsoletes', 'Obsoletes'),
        ('dcite:IsObsoletedBy', 'Is Obsoleted By'),
        ('dcite:IsPublishedIn', 'Is Published In'),
    ]
    
    identifier = models.TextField(blank=True, null=True)
    name = models.TextField(blank=True, null=True, help_text="A title of the resource")
    url = models.URLField(blank=True, null=True, help_text="URL of the resource")
    repository = models.CharField(max_length=200, blank=True, null=True, help_text="Name of the repository")
    relation = models.CharField(max_length=30, choices=RELATION_CHOICES, help_text="How the resource is related to the dataset")
    resource_type = models.CharField(max_length=50, blank=True, null=True, help_text="The type of resource")
    schema_key = models.CharField(max_length=50, default="Resource")
    
    def __str__(self):
        return self.name or self.url or f"Resource {self.pk}"


class AssetsSummary(models.Model):
    """Summary over assets contained in a dandiset"""
    number_of_bytes = models.BigIntegerField()
    number_of_files = models.IntegerField()
    number_of_subjects = models.IntegerField(blank=True, null=True)
    number_of_samples = models.IntegerField(blank=True, null=True)
    number_of_cells = models.IntegerField(blank=True, null=True)
    variable_measured = models.JSONField(default=list, blank=True)
    schema_key = models.CharField(max_length=50, default="AssetsSummary")
    
    class Meta:
        verbose_name_plural = "Assets summaries"
    
    def __str__(self):
        return f"Assets summary: {self.number_of_files} files, {self.number_of_bytes} bytes"


class AssetsSummarySpecies(models.Model):
    """Species associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='species_relations')
    species = models.ForeignKey(SpeciesType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'species']
        verbose_name_plural = "Assets summary species"


class AssetsSummaryApproach(models.Model):
    """Approaches associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='approach_relations')
    approach = models.ForeignKey(ApproachType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'approach']
        verbose_name_plural = "Assets summary approaches"


class AssetsSummaryDataStandard(models.Model):
    """Data standards associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='data_standard_relations')
    data_standard = models.ForeignKey(StandardsType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'data_standard']
        verbose_name_plural = "Assets summary data standards"


class AssetsSummaryMeasurementTechnique(models.Model):
    """Measurement techniques associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='measurement_technique_relations')
    measurement_technique = models.ForeignKey(MeasurementTechniqueType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'measurement_technique']
        verbose_name_plural = "Assets summary measurement techniques"


class Dandiset(models.Model):
    """A body of structured information describing a DANDI dataset"""
    LICENSE_CHOICES = [
        ('spdx:CC0-1.0', 'CC0 1.0'),
        ('spdx:CC-BY-4.0', 'CC BY 4.0'),
    ]
    
    # Core identifiers
    dandi_id = models.CharField(max_length=100, unique=True, help_text="Full DANDI identifier with version like DANDI:000003/0.230629.1955")
    identifier = models.CharField(max_length=100, help_text="A Dandiset identifier")
    
    # Version information
    base_id = models.CharField(max_length=50, help_text="Base DANDI ID without version (e.g., DANDI:000003)", db_index=True)
    version = models.CharField(max_length=100, blank=True, null=True, help_text="Version string (e.g., 0.230629.1955) - null for drafts")
    version_order = models.IntegerField(default=1, help_text="Numeric ordering for versions (0=draft, 1=first published, 2=second, etc.)")
    is_draft = models.BooleanField(default=False, help_text="Whether this is a draft version (not yet published)")
    is_latest = models.BooleanField(default=True, help_text="Whether this is the latest version of this dandiset")
    
    # Version relationships
    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, 
                                       related_name='newer_versions', help_text="Previous version of this dandiset")
    
    # Schema information
    schema_version = models.CharField(max_length=20, default="0.6.4")
    schema_key = models.CharField(max_length=50, default="Dandiset")
    
    # Basic metadata
    name = models.CharField(max_length=500, help_text="A title associated with the Dandiset")
    description = models.TextField(max_length=10000, help_text="A description of the Dandiset")
    
    # Dates
    date_created = models.DateTimeField(blank=True, null=True)
    date_modified = models.DateTimeField(blank=True, null=True)
    date_published = models.DateTimeField(blank=True, null=True)
    
    # License
    license = models.JSONField(default=list, help_text="Licenses associated with the item")
    
    # Citation and version
    citation = models.TextField(blank=True, null=True)
    
    # URLs
    url = models.URLField(blank=True, null=True, help_text="permalink to the item")
    repository = models.URLField(blank=True, null=True, help_text="location of the item")
    doi = models.CharField(max_length=200, blank=True, null=True)
    
    # JSON fields for arrays
    keywords = models.JSONField(default=list, blank=True, help_text="Keywords used to describe this content")
    study_target = models.JSONField(default=list, blank=True, help_text="Objectives or specific questions of the study")
    protocol = models.JSONField(default=list, blank=True, help_text="A list of persistent URLs describing the protocol")
    acknowledgement = models.TextField(blank=True, null=True, help_text="Any acknowledgments not covered by contributors")
    manifest_location = models.JSONField(default=list, blank=True)
    
    # Relationships
    assets_summary = models.OneToOneField(AssetsSummary, on_delete=models.SET_NULL, blank=True, null=True)
    published_by = models.ForeignKey(Activity, on_delete=models.SET_NULL, blank=True, null=True, 
                                   limit_choices_to={'schema_key': 'PublishActivity'})
    
    # Sync tracking
    created_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                      related_name='dandisets_created', help_text="Sync operation that created this dandiset")
    last_modified_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                            related_name='dandisets_modified', help_text="Last sync operation that modified this dandiset")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['base_id', '-version_order']
        unique_together = [('base_id', 'version')]
    
    def __str__(self):
        return f"{self.dandi_id}: {self.name}"
    
    def get_all_versions(self):
        """Get all versions of this dandiset ordered by version"""
        return Dandiset.objects.filter(base_id=self.base_id).order_by('version_order')
    
    def get_latest_version(self):
        """Get the latest version of this dandiset"""
        return Dandiset.objects.filter(base_id=self.base_id, is_latest=True).first()
    
    def get_next_version(self):
        """Get the next version of this dandiset"""
        return self.newer_versions.first()
    
    def save(self, *args, **kwargs):
        # Extract base_id from dandi_id if not set
        if not self.base_id and self.dandi_id:
            if '/' in self.dandi_id:
                self.base_id = self.dandi_id.split('/')[0]
            else:
                self.base_id = self.dandi_id
                
        # Update is_latest flags when saving
        if self.is_latest:
            # Set all other versions of this dandiset to not be latest
            Dandiset.objects.filter(base_id=self.base_id).exclude(pk=self.pk).update(is_latest=False)
            
        super().save(*args, **kwargs)


class DandisetContributor(models.Model):
    """Many-to-many relationship between dandisets and contributors"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='dandiset_contributors')
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'contributor']


class DandisetAbout(models.Model):
    """About/subject matter for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='about')
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, blank=True, null=True)
    anatomy = models.ForeignKey(Anatomy, on_delete=models.CASCADE, blank=True, null=True)
    generic_type = models.ForeignKey(GenericType, on_delete=models.CASCADE, blank=True, null=True)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(disorder__isnull=False) & 
                    models.Q(anatomy__isnull=True) & 
                    models.Q(generic_type__isnull=True)
                ) | (
                    models.Q(disorder__isnull=True) & 
                    models.Q(anatomy__isnull=False) & 
                    models.Q(generic_type__isnull=True)
                ) | (
                    models.Q(disorder__isnull=True) & 
                    models.Q(anatomy__isnull=True) & 
                    models.Q(generic_type__isnull=False)
                ),
                name='only_one_about_type'
            )
        ]


class DandisetAccessRequirements(models.Model):
    """Access requirements for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='access_requirements')
    access_requirement = models.ForeignKey(AccessRequirements, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'access_requirement']


class DandisetRelatedResource(models.Model):
    """Related resources for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='related_resources')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'resource']


class DandisetEthicsApproval(models.Model):
    """Ethics approvals for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='ethics_approvals')
    ethics_approval = models.ForeignKey(EthicsApproval, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'ethics_approval']


class DandisetWasGeneratedBy(models.Model):
    """Activities that generated dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='was_generated_by')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, limit_choices_to={'schema_key': 'Project'})
    
    class Meta:
        unique_together = ['dandiset', 'activity']


class Participant(models.Model):
    """Participant/subject information"""
    identifier = models.CharField(max_length=100, help_text="Subject ID")
    species = models.ForeignKey(SpeciesType, on_delete=models.CASCADE, blank=True, null=True)
    sex = models.ForeignKey(SexType, on_delete=models.CASCADE, blank=True, null=True)
    age = models.JSONField(blank=True, null=True, help_text="Age information with value and unit")
    strain = models.ForeignKey(StrainType, on_delete=models.CASCADE, blank=True, null=True)
    schema_key = models.CharField(max_length=50, default="Participant")
    
    def __str__(self):
        return f"Participant {self.identifier}"


class Asset(models.Model):
    """A DANDI asset"""
    ENCODING_FORMAT_CHOICES = [
        ('application/x-nwb', 'NWB'),
        ('application/x-hdf5', 'HDF5'),
        ('image/tiff', 'TIFF'),
        ('video/mp4', 'MP4'),
        ('application/json', 'JSON'),
    ]
    
    # Core identifiers
    dandi_asset_id = models.CharField(max_length=100, unique=True, help_text="DANDI asset identifier")
    identifier = models.CharField(max_length=100, help_text="Asset identifier")
    
    # Schema information  
    schema_version = models.CharField(max_length=20, default="0.6.7")
    schema_key = models.CharField(max_length=50, default="Asset")
    
    # File information
    path = models.TextField(help_text="Path to the asset within the dandiset")
    content_size = models.BigIntegerField(help_text="Size of the asset in bytes")
    encoding_format = models.CharField(max_length=50, choices=ENCODING_FORMAT_CHOICES, 
                                     help_text="Media type, typically expressed using a MIME format")
    
    # Dates
    date_modified = models.DateTimeField(blank=True, null=True)
    date_published = models.DateTimeField(blank=True, null=True)
    blob_date_modified = models.DateTimeField(blank=True, null=True)
    
    # JSON fields
    digest = models.JSONField(help_text="Digest/checksum information")
    content_url = models.JSONField(default=list, help_text="URLs to access the content")
    variable_measured = models.JSONField(default=list, blank=True, help_text="Variables measured in this asset")
    
    # Relationships - Assets can belong to multiple dandisets through AssetDandiset
    dandisets = models.ManyToManyField(Dandiset, through='AssetDandiset', related_name='assets')
    published_by = models.ForeignKey(Activity, on_delete=models.SET_NULL, blank=True, null=True,
                                   limit_choices_to={'schema_key': 'PublishActivity'})
    
    # Sync tracking
    created_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                      related_name='assets_created', help_text="Sync operation that created this asset")
    last_modified_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                            related_name='assets_modified', help_text="Last sync operation that modified this asset")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['path']
    
    def __str__(self):
        return f"{self.dandi_asset_id}: {self.path}"


class AssetDandiset(models.Model):
    """Many-to-many relationship between assets and dandisets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='asset_dandisets')
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='dandiset_assets')
    
    # Optional metadata about the asset's relationship to this specific dandiset
    date_added = models.DateTimeField(auto_now_add=True, help_text="When this asset was added to this dandiset")
    is_primary = models.BooleanField(default=True, help_text="Whether this is the primary dandiset for this asset")
    
    class Meta:
        unique_together = ['asset', 'dandiset']
        verbose_name = "Asset-Dandiset Association"
        verbose_name_plural = "Asset-Dandiset Associations"
    
    def __str__(self):
        return f"{self.asset.dandi_asset_id} in {self.dandiset.dandi_id}"


class AssetAccess(models.Model):
    """Access requirements for assets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='access_requirements')
    access_requirement = models.ForeignKey(AccessRequirements, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['asset', 'access_requirement']


class AssetApproach(models.Model):
    """Approaches used in assets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='approach_relations')
    approach = models.ForeignKey(ApproachType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['asset', 'approach']


class AssetMeasurementTechnique(models.Model):
    """Measurement techniques used in assets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='measurement_technique_relations')
    measurement_technique = models.ForeignKey(MeasurementTechniqueType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['asset', 'measurement_technique']


class AssetWasAttributedTo(models.Model):
    """Participants/subjects that assets are attributed to"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='attributed_to')
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['asset', 'participant']


class AssetWasGeneratedBy(models.Model):
    """Activities/sessions that generated assets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='was_generated_by')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['asset', 'activity']


class SyncTracker(models.Model):
    """Track the last sync timestamps for incremental updates"""
    SYNC_TYPE_CHOICES = [
        ('full', 'Full Sync'),
        ('dandisets', 'Dandisets Only'),
        ('assets', 'Assets Only'),
    ]
    
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES, default='full')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed', help_text="Status of the sync operation")
    last_sync_timestamp = models.DateTimeField(help_text="When the last sync was completed")
    dandisets_synced = models.IntegerField(default=0, help_text="Number of dandisets synced")
    assets_synced = models.IntegerField(default=0, help_text="Number of assets synced")
    dandisets_updated = models.IntegerField(default=0, help_text="Number of dandisets updated")
    assets_updated = models.IntegerField(default=0, help_text="Number of assets updated")
    sync_duration_seconds = models.FloatField(default=0.0, help_text="Duration of sync in seconds")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if sync failed")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'
        verbose_name = "Synchronization Record"
        verbose_name_plural = "Synchronization Records"
    
    def __str__(self):
        return f"{self.sync_type} sync ({self.status}) at {self.last_sync_timestamp}"
