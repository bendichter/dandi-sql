from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.forms.models import BaseInlineFormSet
from .models import (
    Dandiset, Contributor, ContactPoint, Affiliation, SpeciesType,
    ApproachType, MeasurementTechniqueType, StandardsType, AssetsSummary,
    Activity, Software, Agent, Equipment, EthicsApproval, AccessRequirements,
    Resource, Anatomy, Disorder, GenericType, AssayType, SampleType,
    StrainType, SexType, DandisetContributor, DandisetAbout,
    DandisetAccessRequirements, DandisetRelatedResource, DandisetEthicsApproval,
    DandisetWasGeneratedBy, ContributorAffiliation, ActivityAssociation,
    ActivityEquipment, AssetsSummarySpecies, AssetsSummaryApproach,
    AssetsSummaryDataStandard, AssetsSummaryMeasurementTechnique,
    Asset, Participant, AssetDandiset, AssetAccess, AssetApproach, 
    AssetMeasurementTechnique, AssetWasAttributedTo, AssetWasGeneratedBy
)


class ReadOnlyAdminMixin:
    """Mixin to make admin interfaces read-only"""
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyTabularInline(admin.TabularInline):
    """Read-only tabular inline"""
    extra = 0
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


class DandisetContributorInline(ReadOnlyTabularInline):
    model = DandisetContributor


class DandisetAboutInline(ReadOnlyTabularInline):
    model = DandisetAbout


class DandisetAccessRequirementsInline(ReadOnlyTabularInline):
    model = DandisetAccessRequirements


class DandisetRelatedResourceInline(ReadOnlyTabularInline):
    model = DandisetRelatedResource


class LimitedAssetFormSet(BaseInlineFormSet):
    """Custom formset that limits the number of assets displayed"""
    
    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            qs = super().get_queryset()
            self._queryset = qs.select_related('asset').order_by('-date_added')[:10]
        return self._queryset


class DandisetAssetsInline(ReadOnlyTabularInline):
    model = AssetDandiset
    formset = LimitedAssetFormSet
    verbose_name = "Asset"
    verbose_name_plural = "Assets (first 10 shown)"
    fields = ('asset', 'is_primary', 'date_added')
    readonly_fields = ('asset', 'is_primary', 'date_added')
    show_change_link = True


class AssetsSummarySpeciesInline(ReadOnlyTabularInline):
    model = AssetsSummarySpecies


class AssetsSummaryApproachInline(ReadOnlyTabularInline):
    model = AssetsSummaryApproach


class AssetsSummaryDataStandardInline(ReadOnlyTabularInline):
    model = AssetsSummaryDataStandard


class AssetsSummaryMeasurementTechniqueInline(ReadOnlyTabularInline):
    model = AssetsSummaryMeasurementTechnique


@admin.register(Dandiset)
class DandisetAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['dandi_id', 'name', 'get_asset_count', 'is_latest', 'version', 'date_created', 'date_published']
    list_filter = ['date_created', 'date_published', 'license', 'is_latest', 'is_draft']
    search_fields = ['dandi_id', 'base_id', 'name', 'description', 'keywords']
    readonly_fields = ['created_at', 'updated_at']
    
    @admin.display(description='Asset Count', ordering='dandiset_assets__count')
    def get_asset_count(self, obj):
        """Get the number of assets in this dandiset"""
        return obj.dandiset_assets.count()
    
    def get_queryset(self, request):
        """Optimize queryset to prefetch asset counts"""
        return super().get_queryset(request).prefetch_related('dandiset_assets')
    
    inlines = [
        DandisetAssetsInline,
        DandisetContributorInline,
        DandisetAboutInline,
        DandisetAccessRequirementsInline,
        DandisetRelatedResourceInline,
    ]
    
    fieldsets = (
        ('Core Identifiers', {
            'fields': ('dandi_id', 'identifier', 'doi')
        }),
        ('Basic Information', {
            'fields': ('name', 'description', 'citation', 'version', 'schema_version', 'schema_key')
        }),
        ('Dates', {
            'fields': ('date_created', 'date_modified', 'date_published')
        }),
        ('URLs', {
            'fields': ('url', 'repository')
        }),
        ('Metadata', {
            'fields': ('license', 'keywords', 'study_target', 'protocol', 'acknowledgement', 'manifest_location')
        }),
        ('Relationships', {
            'fields': ('assets_summary', 'published_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Contributor)
class ContributorAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'schema_key', 'email', 'include_in_citation']
    list_filter = ['schema_key', 'include_in_citation', 'role_name']
    search_fields = ['name', 'email', 'identifier']


@admin.register(AssetsSummary)
class AssetsSummaryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['__str__', 'number_of_files', 'number_of_bytes', 'number_of_subjects']
    readonly_fields = ['number_of_bytes', 'number_of_files']
    
    inlines = [
        AssetsSummarySpeciesInline,
        AssetsSummaryApproachInline,
        AssetsSummaryDataStandardInline,
        AssetsSummaryMeasurementTechniqueInline,
    ]


@admin.register(Activity)
class ActivityAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'schema_key', 'start_date', 'end_date']
    list_filter = ['schema_key', 'start_date']
    search_fields = ['name', 'description', 'identifier']


@admin.register(ContactPoint)
class ContactPointAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['email', 'url']
    search_fields = ['email', 'url']


@admin.register(AccessRequirements)
class AccessRequirementsAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['status', 'embargoed_until', 'contact_point']
    list_filter = ['status', 'embargoed_until']


@admin.register(Resource)
class ResourceAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'relation', 'url', 'repository']
    list_filter = ['relation', 'resource_type']
    search_fields = ['name', 'url', 'identifier']


# Register all the base types
@admin.register(SpeciesType)
class SpeciesTypeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(ApproachType)
class ApproachTypeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(MeasurementTechniqueType)
class MeasurementTechniqueTypeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(StandardsType)
class StandardsTypeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(Anatomy)
class AnatomyAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(Disorder)
class DisorderAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


@admin.register(GenericType)
class GenericTypeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'identifier']
    search_fields = ['name', 'identifier']


# Asset-related inlines
class AssetAccessInline(ReadOnlyTabularInline):
    model = AssetAccess


class AssetApproachInline(ReadOnlyTabularInline):
    model = AssetApproach


class AssetMeasurementTechniqueInline(ReadOnlyTabularInline):
    model = AssetMeasurementTechnique


class AssetWasAttributedToInline(ReadOnlyTabularInline):
    model = AssetWasAttributedTo


class AssetWasGeneratedByInline(ReadOnlyTabularInline):
    model = AssetWasGeneratedBy


class AssetDandisetInline(ReadOnlyTabularInline):
    model = AssetDandiset
    extra = 0


@admin.register(Asset)
class AssetAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['dandi_asset_id', 'path', 'get_dandisets', 'content_size', 'encoding_format', 'date_published']
    list_filter = ['encoding_format', 'date_published']
    search_fields = ['dandi_asset_id', 'path', 'identifier']
    readonly_fields = ['created_at', 'updated_at']
    
    @admin.display(description='Dandisets')
    def get_dandisets(self, obj):
        """Get a comma-separated list of dandisets this asset belongs to"""
        return ", ".join([ds.dandi_id for ds in obj.dandisets.all()])
    
    inlines = [
        AssetDandisetInline,
        AssetAccessInline,
        AssetApproachInline,
        AssetMeasurementTechniqueInline,
        AssetWasAttributedToInline,
        AssetWasGeneratedByInline,
    ]
    
    fieldsets = (
        ('Core Identifiers', {
            'fields': ('dandi_asset_id', 'identifier')
        }),
        ('File Information', {
            'fields': ('path', 'content_size', 'encoding_format', 'digest', 'content_url')
        }),
        ('Schema Information', {
            'fields': ('schema_version', 'schema_key')
        }),
        ('Dates', {
            'fields': ('date_modified', 'date_published', 'blob_date_modified')
        }),
        ('Metadata', {
            'fields': ('variable_measured',)
        }),
        ('Relationships', {
            'fields': ('published_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(AssetDandiset)
class AssetDandisetAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['asset', 'dandiset', 'is_primary', 'date_added']
    list_filter = ['is_primary', 'date_added', 'dandiset']
    search_fields = ['asset__dandi_asset_id', 'asset__path', 'dandiset__dandi_id', 'dandiset__name']


@admin.register(Participant)
class ParticipantAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['identifier', 'species', 'sex', 'schema_key']
    list_filter = ['species', 'sex', 'strain']
    search_fields = ['identifier']


# Register other supporting models
admin.site.register(Affiliation)
admin.site.register(Software)
admin.site.register(Agent)
admin.site.register(Equipment)
admin.site.register(EthicsApproval)
admin.site.register(AssayType)
admin.site.register(SampleType)
admin.site.register(StrainType)
admin.site.register(SexType)


# Customize admin site headers
admin.site.site_header = "DANDI SQL Database Administration"
admin.site.site_title = "DANDI SQL Admin"
admin.site.index_title = "Welcome to DANDI SQL Database Administration"
