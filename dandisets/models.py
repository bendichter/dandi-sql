from django.db import models


class BaseType(models.Model):
    """Base class for enumerated types"""
    identifier = models.TextField(blank=True, null=True, help_text="The identifier can be any url or a compact URI")
    name = models.CharField(max_length=500, blank=True, null=True, help_text="The name of the item")
    
    class Meta:
        abstract = True
    
    def __str__(self):
        return self.name or self.identifier or str(self.pk)


class SpeciesType(BaseType):
    """Identifier for species of the sample"""
    
    class Meta(BaseType.Meta):
        verbose_name_plural = "Species"
        db_table_comment = "Species taxonomy information for experimental subjects"
    

class ApproachType(BaseType):
    """Identifier for approach used"""

    class Meta(BaseType.Meta):
        db_table_comment = "Experimental approaches used in studies (e.g., electrophysiology, microscopy, behavioral)"


class MeasurementTechniqueType(BaseType):
    """Identifier for measurement technique used"""

    class Meta(BaseType.Meta):
        db_table_comment = "Specific measurement techniques used in experiments (e.g., patch clamp, calcium imaging)"


class StandardsType(BaseType):
    """Identifier for data standard used"""

    class Meta(BaseType.Meta):
        db_table_comment = "Data format standards used (e.g., NWB, BIDS, OME-NGFF)"


class AssayType(BaseType):
    """OBI based identifier for the assay(s) used"""

    class Meta(BaseType.Meta):
        db_table_comment = "Ontology for Biomedical Investigations (OBI) based assay types used in experiments"


class SampleType(BaseType):
    """OBI based identifier for the sample type used"""

    class Meta(BaseType.Meta):
        db_table_comment = "OBI based sample types (e.g., tissue, cell culture, brain slice)"


class Anatomy(BaseType):
    """UBERON or other identifier for anatomical part studied"""

    class Meta(BaseType.Meta):
        db_table_comment = "Anatomical structures using UBERON or other ontology identifiers (e.g., hippocampus, cortex)"


class StrainType(BaseType):
    """Identifier for the strain of the sample"""
    
    class Meta(BaseType.Meta):
        db_table_comment = "Genetic strain information for experimental subjects"


class SexType(BaseType):
    """Identifier for the sex of the sample"""

    class Meta(BaseType.Meta):
        db_table_comment = "Biological sex information for experimental subjects"


class Disorder(BaseType):
    """Biolink, SNOMED, or other identifier for disorder studied"""
    dx_date = models.JSONField(blank=True, null=True, help_text="Dates of diagnosis")

    class Meta(BaseType.Meta):
        db_table_comment = "Medical disorders and conditions using Biolink, SNOMED, or other medical ontologies"


class GenericType(BaseType):
    """An object to capture any type for about"""

    class Meta(BaseType.Meta):
        db_table_comment = "Generic type for categorizing dataset subject matter that doesn't fit other specific types"


class ContactPoint(models.Model):
    """Contact point information"""
    email = models.EmailField(blank=True, null=True, help_text="Email address of contact")
    url = models.URLField(blank=True, null=True, help_text="A Web page to find information on how to contact")

    class Meta:
        db_table_comment = "Contact information for reaching people or organizations associated with datasets"
    
    def __str__(self):
        return self.email or self.url or "Contact Point"


class Affiliation(models.Model):
    """Affiliation information"""
    identifier = models.TextField(blank=True, null=True, help_text="A ror.org identifier for institutions")
    name = models.TextField(help_text="Name of organization")
    
    class Meta:
        db_table_comment = "Organizational affiliations for contributors (research institutions, universities, companies)"
    
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
    name = models.TextField(blank=True, null=True, help_text="Full name of the person or organization")
    email = models.EmailField(blank=True, null=True, help_text="Email address of the contributor")
    url = models.URLField(blank=True, null=True, help_text="Web page for the contributor (personal page, organization website)")
    award_number = models.TextField(blank=True, null=True, help_text="Identifier associated with a sponsored or gift award")
    schema_key = models.CharField(max_length=20, choices=SCHEMA_KEY_CHOICES, default='Contributor', help_text="Type of contributor (Person, Organization, or Contributor)")
    contact_point = models.JSONField(default=list, blank=True, help_text="Organization contact information")
    
    class Meta:
        db_table_comment = "People and organizations that contribute to datasets (authors, data collectors, maintainers, etc.)"
    
    def __str__(self):
        return f"{self.name} ({self.schema_key})"


class ContributorAffiliation(models.Model):
    """Many-to-many relationship between contributors and affiliations"""
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE, help_text="The contributor linked to this affiliation")
    affiliation = models.ForeignKey(Affiliation, on_delete=models.CASCADE, help_text="The organization the contributor is affiliated with")
    
    class Meta:
        unique_together = ['contributor', 'affiliation']
        db_table_comment = "Links contributors to their institutional affiliations"


class Software(models.Model):
    """Software information"""
    identifier = models.TextField(blank=True, null=True, help_text="RRID of the software from scicrunch.org")
    name = models.TextField(help_text="Name of the software")
    version = models.CharField(max_length=100, help_text="Version number or string of the software")
    url = models.URLField(blank=True, null=True, help_text="Web page for the software")
    
    class Meta:
        db_table_comment = "Software tools and applications used in data collection, analysis, or processing"
    
    def __str__(self):
        return f"{self.name} v{self.version}"


class Agent(models.Model):
    """Agent information"""
    identifier = models.TextField(blank=True, null=True, help_text="Identifier for an agent")
    name = models.TextField(help_text="Name of the agent")
    url = models.URLField(blank=True, null=True, help_text="Web page for the agent")
    
    class Meta:
        db_table_comment = "Generic agents (entities that can perform actions) in the data provenance"
    
    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Equipment information"""
    identifier = models.TextField(blank=True, null=True, help_text="Unique identifier for the equipment")
    name = models.CharField(max_length=150, help_text="A name for the equipment")
    description = models.TextField(blank=True, null=True, help_text="The description of the equipment")
    
    class Meta:
        db_table_comment = "Laboratory and research equipment used in experiments and data collection"
    
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
    
    identifier = models.TextField(blank=True, null=True, help_text="Unique identifier for the activity")
    name = models.CharField(max_length=150, help_text="The name of the activity")
    description = models.TextField(blank=True, null=True, help_text="The description of the activity")
    start_date = models.DateTimeField(blank=True, null=True, help_text="When the activity started")
    end_date = models.DateTimeField(blank=True, null=True, help_text="When the activity ended")
    schema_key = models.CharField(max_length=20, choices=SCHEMA_KEY_CHOICES, default='Activity', help_text="Type of activity (Activity, Project, Session, or PublishActivity)")
    
    # Direct relationships - much cleaner than the complex ActivityAssociation model
    contributors = models.ManyToManyField(Contributor, blank=True, related_name='activities', help_text="People or organizations associated with this activity")
    software = models.ManyToManyField(Software, blank=True, related_name='activities', help_text="Software tools used in this activity")
    agents = models.ManyToManyField(Agent, blank=True, related_name='activities', help_text="Generic agents involved in this activity")
    equipment = models.ManyToManyField(Equipment, blank=True, related_name='activities', help_text="Equipment and instruments used in this activity")
    
    class Meta:
        db_table_comment = "Research activities, projects, sessions, and publishing activities in the data provenance"
    
    def __str__(self):
        return f"{self.name} ({self.schema_key})"


class EthicsApproval(models.Model):
    """Information about ethics committee approval for project"""
    identifier = models.TextField(help_text="Approved Protocol identifier, often a number or alphanumeric string")
    contact_point = models.ForeignKey(ContactPoint, on_delete=models.SET_NULL, blank=True, null=True, help_text="Information about the ethics approval committee")
    
    class Meta:
        db_table_comment = "Ethics committee approvals for research projects involving human or animal subjects"
    
    def __str__(self):
        return f"Ethics Approval: {self.identifier}"


class AccessRequirements(models.Model):
    """Information about access options for the dataset"""
    ACCESS_STATUS_CHOICES = [
        ('dandi:OpenAccess', 'Open Access'),
        ('dandi:EmbargoedAccess', 'Embargoed Access'),
    ]
    
    status = models.CharField(max_length=30, choices=ACCESS_STATUS_CHOICES, help_text="The access status of the item")
    contact_point = models.ForeignKey(ContactPoint, on_delete=models.SET_NULL, blank=True, null=True, help_text="Who or where to look for information about access")
    description = models.TextField(blank=True, null=True, help_text="Information about access requirements when embargoed or restricted")
    embargoed_until = models.DateField(blank=True, null=True, help_text="Date on which embargo ends")
    
    class Meta:
        db_table_comment = "Access restrictions and requirements for datasets (open access, embargoed, etc.)"
    
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
    
    identifier = models.TextField(blank=True, null=True, help_text="Unique identifier for the resource (DOI, URL, etc.)")
    name = models.TextField(blank=True, null=True, help_text="A title of the resource")
    url = models.URLField(blank=True, null=True, help_text="URL of the resource")
    repository = models.CharField(max_length=200, blank=True, null=True, help_text="Name of the repository in which the resource is housed")
    relation = models.CharField(max_length=30, choices=RELATION_CHOICES, help_text="How the resource is related to the dataset")
    resource_type = models.CharField(max_length=50, blank=True, null=True, help_text="The type of resource (Dataset, Software, Publication, etc.)")
    
    class Meta:
        db_table_comment = "External resources related to datasets (publications, code repositories, other datasets, etc.)"
    
    def __str__(self):
        return self.name or self.url or f"Resource {self.pk}"


class AssetsSummary(models.Model):
    """Summary over assets contained in a dandiset"""
    number_of_bytes = models.BigIntegerField(help_text="Total size of all assets in bytes")
    number_of_files = models.IntegerField(help_text="Total number of files/assets in the dandiset")
    number_of_subjects = models.IntegerField(blank=True, null=True, help_text="Total number of experimental subjects")
    number_of_samples = models.IntegerField(blank=True, null=True, help_text="Total number of biological samples")
    number_of_cells = models.IntegerField(blank=True, null=True, help_text="Total number of cells recorded from")
    variable_measured = models.JSONField(default=list, blank=True, help_text="List of variables/measurements recorded")
    
    class Meta:
        verbose_name_plural = "Assets summaries"
        db_table_comment = "Statistical summaries of the assets contained within a dataset (file counts, subjects, etc.)"
    
    def __str__(self):
        return f"Assets summary: {self.number_of_files} files, {self.number_of_bytes} bytes"


class AssetsSummarySpecies(models.Model):
    """Species associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='species_relations')
    species = models.ForeignKey(SpeciesType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'species']
        verbose_name_plural = "Assets summary species"
        db_table_comment = "Links asset summaries to the species involved in the datasets"


class AssetsSummaryApproach(models.Model):
    """Approaches associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='approach_relations')
    approach = models.ForeignKey(ApproachType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'approach']
        verbose_name_plural = "Assets summary approaches"
        db_table_comment = "Links asset summaries to the experimental approaches used in the datasets"


class AssetsSummaryDataStandard(models.Model):
    """Data standards associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='data_standard_relations')
    data_standard = models.ForeignKey(StandardsType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'data_standard']
        verbose_name_plural = "Assets summary data standards"
        db_table_comment = "Links asset summaries to the data format standards used in the datasets"


class AssetsSummaryMeasurementTechnique(models.Model):
    """Measurement techniques associated with assets summary"""
    assets_summary = models.ForeignKey(AssetsSummary, on_delete=models.CASCADE, related_name='measurement_technique_relations')
    measurement_technique = models.ForeignKey(MeasurementTechniqueType, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['assets_summary', 'measurement_technique']
        verbose_name_plural = "Assets summary measurement techniques"
        db_table_comment = "Links asset summaries to the measurement techniques used in the datasets"


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
    schema_version = models.CharField(max_length=20, default="0.6.4", help_text="Version of the DANDI schema used for this dandiset")
    
    # Basic metadata
    name = models.CharField(max_length=500, help_text="A title associated with the Dandiset")
    description = models.TextField(max_length=10000, help_text="A description of the Dandiset")
    
    # Dates
    date_created = models.DateTimeField(blank=True, null=True, help_text="When the dandiset was originally created")
    date_modified = models.DateTimeField(blank=True, null=True, help_text="Last modification date and time")
    date_published = models.DateTimeField(blank=True, null=True, help_text="When the dandiset was published")
    
    # License
    license = models.JSONField(default=list, help_text="Licenses associated with the item (CC0, CC-BY-4.0, etc.)")
    
    # Citation and version
    citation = models.TextField(blank=True, null=True, help_text="Automatically generated citation for this dandiset")
    
    # URLs
    url = models.URLField(blank=True, null=True, help_text="permalink to the item")
    repository = models.URLField(blank=True, null=True, help_text="location of the item")
    doi = models.CharField(max_length=200, blank=True, null=True, help_text="Digital Object Identifier for this dandiset")
    
    # JSON fields for arrays
    keywords = models.JSONField(default=list, blank=True, help_text="Keywords used to describe this content")
    study_target = models.JSONField(default=list, blank=True, help_text="Objectives or specific questions of the study")
    protocol = models.JSONField(default=list, blank=True, help_text="A list of persistent URLs describing the protocol")
    acknowledgement = models.TextField(blank=True, null=True, help_text="Any acknowledgments not covered by contributors")
    manifest_location = models.JSONField(default=list, blank=True, help_text="URLs to dandiset manifest files")
    
    # Relationships
    assets_summary = models.OneToOneField(AssetsSummary, on_delete=models.SET_NULL, blank=True, null=True, help_text="Statistical summary of the assets in this dandiset")
    published_by = models.ForeignKey(Activity, on_delete=models.SET_NULL, blank=True, null=True, 
                                   limit_choices_to={'schema_key': 'PublishActivity'}, help_text="Publishing activity that made this dandiset public")
    
    # Direct relationships - much cleaner than DandisetAbout with complex constraints
    disorders = models.ManyToManyField(Disorder, blank=True, related_name='dandisets', help_text="Medical disorders and conditions studied in this dataset")
    anatomy = models.ManyToManyField(Anatomy, blank=True, related_name='dandisets', help_text="Anatomical structures studied in this dataset")
    generic_types = models.ManyToManyField(GenericType, blank=True, related_name='dandisets', help_text="Generic subject matter categories for this dataset")
    
    # Sync tracking
    created_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                      related_name='dandisets_created', help_text="Sync operation that created this dandiset")
    last_modified_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                            related_name='dandisets_modified', help_text="Last sync operation that modified this dandiset")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this record was created in the local database")
    updated_at = models.DateTimeField(auto_now=True, help_text="When this record was last updated in the local database")
    
    class Meta:
        ordering = ['base_id', '-version_order']
        unique_together = [('base_id', 'version')]
        db_table_comment = "DANDI datasets - the main repository entities that contain collections of neuroscience data files"
    
    def __str__(self):
        return f"{self.dandi_id}: {self.name}"
    
    def get_all_versions(self):
        """Get all versions of this dandiset ordered by version"""
        return Dandiset.objects.filter(base_id=self.base_id).order_by('version_order')
    
    def get_latest_version(self):
        """Get the latest version of this dandiset"""
        return Dandiset.objects.filter(base_id=self.base_id, is_latest=True).first()
    
    
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
    """Many-to-many relationship between dandisets and contributors with role information"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='dandiset_contributors')
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE)
    
    # Role-specific fields that vary by dandiset
    role_name = models.JSONField(default=list, blank=True, help_text="Role(s) of the contributor in this specific dandiset")
    include_in_citation = models.BooleanField(default=True, help_text="Include contributor in citation for this dandiset")
    
    class Meta:
        unique_together = ['dandiset', 'contributor']
        db_table_comment = "Links datasets to their contributors with specific roles and citation preferences"
    
    def __str__(self):
        roles = ', '.join(self.role_name) if self.role_name else 'No roles'
        return f"{self.contributor.name} - {roles} in {self.dandiset.base_id}"




class DandisetAccessRequirements(models.Model):
    """Access requirements for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='access_requirements')
    access_requirement = models.ForeignKey(AccessRequirements, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'access_requirement']
        db_table_comment = "Links datasets to their access restrictions and requirements"


class DandisetRelatedResource(models.Model):
    """Related resources for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='related_resources')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'resource']
        db_table_comment = "Links datasets to external related resources (publications, code, other datasets)"


class DandisetEthicsApproval(models.Model):
    """Ethics approvals for dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='ethics_approvals')
    ethics_approval = models.ForeignKey(EthicsApproval, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['dandiset', 'ethics_approval']
        db_table_comment = "Links datasets to their ethics committee approvals"


class DandisetWasGeneratedBy(models.Model):
    """Activities that generated dandisets"""
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='was_generated_by')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, limit_choices_to={'schema_key': 'Project'})
    
    class Meta:
        unique_together = ['dandiset', 'activity']
        db_table_comment = "Links datasets to the research projects that generated them"


class Participant(models.Model):
    """Participant/subject information"""
    identifier = models.CharField(max_length=100, help_text="Subject ID")
    species = models.ForeignKey(SpeciesType, on_delete=models.CASCADE, blank=True, null=True, help_text="Species of the experimental subject")
    sex = models.ForeignKey(SexType, on_delete=models.CASCADE, blank=True, null=True, help_text="Biological sex of the experimental subject")
    age = models.JSONField(blank=True, null=True, help_text="Age information with value and unit")
    strain = models.ForeignKey(StrainType, on_delete=models.CASCADE, blank=True, null=True, help_text="Genetic strain of the experimental subject")
    
    class Meta:
        db_table_comment = "Research participants and experimental subjects with demographic and biological information"
    
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
    schema_version = models.CharField(max_length=20, default="0.6.7", help_text="Version of the DANDI schema used for this asset")
    
    # File information
    content_size = models.BigIntegerField(help_text="Size of the asset in bytes")
    encoding_format = models.CharField(max_length=50, choices=ENCODING_FORMAT_CHOICES, 
                                     help_text="Media type, typically expressed using a MIME format")
    
    # Dates
    date_modified = models.DateTimeField(blank=True, null=True, help_text="When the asset metadata was last modified")
    date_published = models.DateTimeField(blank=True, null=True, help_text="When the asset was published")
    blob_date_modified = models.DateTimeField(blank=True, null=True, help_text="When the actual file content was last modified")
    
    # JSON fields
    digest = models.JSONField(help_text="Digest/checksum information")
    content_url = models.JSONField(default=list, help_text="URLs to access the content")
    variable_measured = models.JSONField(default=list, blank=True, help_text="Variables measured in this asset")
    
    # Relationships - Assets can belong to multiple dandisets through AssetDandiset
    dandisets = models.ManyToManyField(Dandiset, through='AssetDandiset', related_name='assets', help_text="Dandisets that contain this asset")
    published_by = models.ForeignKey(Activity, on_delete=models.SET_NULL, blank=True, null=True,
                                   limit_choices_to={'schema_key': 'PublishActivity'}, help_text="Publishing activity that made this asset public")
    
    # Direct many-to-many relationships - much cleaner than intermediate models
    access_requirements = models.ManyToManyField(AccessRequirements, blank=True, related_name='assets', help_text="Access restrictions and requirements for this asset")
    approaches = models.ManyToManyField(ApproachType, blank=True, related_name='assets', help_text="Experimental approaches used to collect this asset's data")
    measurement_techniques = models.ManyToManyField(MeasurementTechniqueType, blank=True, related_name='assets', help_text="Specific measurement techniques used to collect this asset's data")
    participants = models.ManyToManyField(Participant, blank=True, related_name='assets', help_text="Research subjects or participants this asset's data was collected from")
    activities = models.ManyToManyField(Activity, blank=True, related_name='generated_assets', help_text="Experimental sessions or activities that generated this asset")
    
    # Sync tracking
    created_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                      related_name='assets_created', help_text="Sync operation that created this asset")
    last_modified_by_sync = models.ForeignKey('SyncTracker', on_delete=models.SET_NULL, blank=True, null=True,
                                            related_name='assets_modified', help_text="Last sync operation that modified this asset")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this record was created in the local database")
    updated_at = models.DateTimeField(auto_now=True, help_text="When this record was last updated in the local database")
    
    class Meta:
        ordering = ['dandi_asset_id']
        db_table_comment = "Individual data files within datasets (NWB files, images, videos, etc.)"
    
    def __str__(self):
        return f"{self.dandi_asset_id}"


class AssetDandiset(models.Model):
    """Many-to-many relationship between assets and dandisets"""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='asset_dandisets')
    dandiset = models.ForeignKey(Dandiset, on_delete=models.CASCADE, related_name='dandiset_assets')
    
    # Path is stored here since the same asset can have different paths in different dandisets
    path = models.TextField(help_text="Path to the asset within this specific dandiset")
    
    # Optional metadata about the asset's relationship to this specific dandiset
    date_added = models.DateTimeField(auto_now_add=True, help_text="When this asset was added to this dandiset")
    is_primary = models.BooleanField(default=True, help_text="Whether this is the primary dandiset for this asset")
    
    class Meta:
        unique_together = ['asset', 'dandiset']
        verbose_name = "Asset-Dandiset Association"
        verbose_name_plural = "Asset-Dandiset Associations"
        db_table_comment = "Links individual data files to the datasets they belong to, including file paths"
    
    def __str__(self):
        return f"{self.asset.dandi_asset_id} ({self.path}) in {self.dandiset.dandi_id}"




class SyncTracker(models.Model):
    """Track the last sync timestamps for incremental updates"""
    SYNC_TYPE_CHOICES = [
        ('full', 'Full Sync'),
        ('dandisets', 'Dandisets Only'),
        ('assets', 'Assets Only'),
        ('lindi', 'LINDI Metadata Only'),
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
    lindi_metadata_processed = models.IntegerField(default=0, help_text="Number of LINDI metadata records processed")
    sync_duration_seconds = models.FloatField(default=0.0, help_text="Duration of sync in seconds")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if sync failed")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'
        verbose_name = "Synchronization Record"
        verbose_name_plural = "Synchronization Records"
        db_table_comment = "Tracks synchronization operations from the DANDI Archive API to keep local data up-to-date"
    
    def __str__(self):
        return f"{self.sync_type} sync ({self.status}) at {self.last_sync_timestamp}"


class LindiMetadata(models.Model):
    """Store LINDI metadata for NWB assets"""
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name='lindi_metadata')
    structure_metadata = models.JSONField(help_text="Filtered LINDI structure (no base64 data or large arrays)")
    lindi_url = models.URLField(help_text="URL to the original LINDI file")
    processed_at = models.DateTimeField(auto_now_add=True)
    processing_version = models.CharField(max_length=20, default="1.0")
    sync_tracker = models.ForeignKey(SyncTracker, on_delete=models.SET_NULL, blank=True, null=True,
                                   related_name='lindi_metadata_created', help_text="Sync operation that processed this LINDI metadata")
    
    class Meta:
        verbose_name = "LINDI Metadata"
        verbose_name_plural = "LINDI Metadata"
        ordering = ['-processed_at']
        db_table_comment = "Stores LINDI (Linked Data Interface) metadata for efficient access to NWB file structure without downloading"
    
    def __str__(self):
        return f"LINDI metadata for {self.asset.dandi_asset_id}"
    
    @property
    def dandiset_id(self):
        """Get the dandiset ID from the associated asset"""
        first_dandiset = self.asset.dandisets.first()
        if first_dandiset:
            return first_dandiset.base_id
        return None
    
    @property
    def asset_id(self):
        """Get the asset ID"""
        return self.asset.dandi_asset_id
