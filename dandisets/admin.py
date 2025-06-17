from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse, path
from django.forms.models import BaseInlineFormSet
from django.contrib import messages
from django.core.management import call_command
from django.utils.html import format_html
from django.template.response import TemplateResponse
import io
import sys
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
    AssetMeasurementTechnique, AssetWasAttributedTo, AssetWasGeneratedBy,
    SyncTracker
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
    list_filter = ['date_created', 'date_published', 'license', 'is_latest', 'is_draft', 'created_by_sync', 'last_modified_by_sync']
    search_fields = ['dandi_id', 'base_id', 'name', 'description', 'keywords']
    readonly_fields = ['created_at', 'updated_at', 'created_by_sync', 'last_modified_by_sync']
    actions = ['sync_from_dandi_archive']
    
    @admin.display(description='Asset Count', ordering='dandiset_assets__count')
    def get_asset_count(self, obj):
        """Get the number of assets in this dandiset"""
        return obj.dandiset_assets.count()
    
    def get_queryset(self, request):
        """Optimize queryset to prefetch asset counts"""
        return super().get_queryset(request).prefetch_related('dandiset_assets')
    
    @admin.action(description='Sync all dandisets from DANDI archive')
    def sync_from_dandi_archive(self, request, queryset):
        """Sync dandiset metadata and assets from the DANDI archive.
        
        Performs incremental sync of all dandisets from the DANDI archive.
        Selection is ignored - always syncs all dandisets.
        """
        # Note: We ignore the queryset parameter since this action works on all data
        output = io.StringIO()
        
        try:
            # Always perform incremental sync of all dandisets
            call_command(
                'sync_dandi_incremental',
                verbose=True,
                no_progress=True,
                stdout=output
            )
            
            output_text = output.getvalue()
            if output_text:
                # Extract summary statistics from output
                lines = output_text.split('\n')
                summary_lines = []
                in_summary = False
                
                for line in lines:
                    if 'SYNC SUMMARY' in line:
                        in_summary = True
                    elif in_summary and line.strip():
                        summary_lines.append(line.strip())
                    elif in_summary and not line.strip():
                        break
                
                if summary_lines:
                    messages.success(
                        request,
                        format_html(
                            "Successfully synced all dandisets from DANDI archive:<br/><pre>{}</pre>",
                            '\n'.join(summary_lines[:8])  # Show first 8 lines of summary
                        )
                    )
                else:
                    messages.success(request, "Successfully synced all dandisets from DANDI archive")
            else:
                messages.success(request, "Successfully synced all dandisets from DANDI archive")
                
        except Exception as e:
            messages.error(request, f"Error syncing from DANDI archive: {str(e)}")
        finally:
            output.close()
    
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
        ('Sync Tracking', {
            'fields': ('created_by_sync', 'last_modified_by_sync'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Contributor)
class ContributorAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'schema_key', 'email', 'identifier', 'get_dandiset_count']
    list_filter = ['schema_key']
    search_fields = ['name', 'email', 'identifier']
    
    @admin.display(description='Dandisets Count')
    def get_dandiset_count(self, obj):
        """Get the number of dandisets this contributor is associated with"""
        return obj.dandisetcontributor_set.count()
    
    def get_queryset(self, request):
        """Optimize queryset to prefetch dandiset relationships"""
        return super().get_queryset(request).prefetch_related('dandisetcontributor_set')


@admin.register(DandisetContributor)
class DandisetContributorAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ['contributor', 'dandiset', 'get_roles', 'include_in_citation']
    list_filter = ['include_in_citation', 'dandiset__base_id']
    search_fields = ['contributor__name', 'contributor__email', 'dandiset__name', 'dandiset__dandi_id']
    
    @admin.display(description='Roles')
    def get_roles(self, obj):
        """Display roles as comma-separated string"""
        if obj.role_name:
            return ', '.join(obj.role_name) if isinstance(obj.role_name, list) else str(obj.role_name)
        return 'No roles'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('contributor', 'dandiset')


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
    list_filter = ['encoding_format', 'date_published', 'created_by_sync', 'last_modified_by_sync']
    search_fields = ['dandi_asset_id', 'path', 'identifier']
    readonly_fields = ['created_at', 'updated_at', 'created_by_sync', 'last_modified_by_sync']
    
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
        ('Sync Tracking', {
            'fields': ('created_by_sync', 'last_modified_by_sync'),
            'classes': ('collapse',)
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


@admin.register(SyncTracker)
class SyncTrackerAdmin(admin.ModelAdmin):
    list_display = [
        'last_sync_timestamp', 
        'sync_type', 
        'status',
        'get_duration_display',
        'dandisets_updated', 
        'assets_updated',
        'get_efficiency_display'
    ]
    list_filter = ['sync_type', 'status', 'last_sync_timestamp']
    readonly_fields = [
        'sync_type', 
        'status',
        'last_sync_timestamp', 
        'dandisets_synced', 
        'assets_synced',
        'dandisets_updated', 
        'assets_updated', 
        'sync_duration_seconds',
        'error_message',
        'created_at',
        'get_duration_display',
        'get_efficiency_display'
    ]
    ordering = ['-created_at']
    
    # Override the read-only permissions but keep them for individual records
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    @admin.display(description='Duration', ordering='sync_duration_seconds')
    def get_duration_display(self, obj):
        """Display sync duration in a human-readable format"""
        seconds = obj.sync_duration_seconds
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            return f"{seconds/60:.1f} minutes"
        else:
            return f"{seconds/3600:.1f} hours"
    
    @admin.display(description='Efficiency')
    def get_efficiency_display(self, obj):
        """Display sync efficiency metrics"""
        if obj.sync_duration_seconds > 0:
            total_items = obj.dandisets_synced + obj.assets_synced
            if total_items > 0:
                items_per_second = total_items / obj.sync_duration_seconds
                return f"{items_per_second:.1f} items/sec"
        return "N/A"
    
    def get_urls(self):
        """Add custom URLs for the sync functionality"""
        urls = super().get_urls()
        custom_urls = [
            path('sync/', self.admin_site.admin_view(self.sync_view), name='%s_%s_sync' % (self.model._meta.app_label, self.model._meta.model_name)),
        ]
        return custom_urls + urls
    
    def sync_view(self, request):
        """Custom view to handle sync without requiring item selection"""
        if request.method == 'POST':
            output = io.StringIO()
            
            try:
                # Always perform incremental sync of all dandisets
                call_command(
                    'sync_dandi_incremental',
                    verbose=True,
                    no_progress=True,
                    stdout=output
                )
                
                output_text = output.getvalue()
                if output_text:
                    # Extract summary statistics from output
                    lines = output_text.split('\n')
                    summary_lines = []
                    in_summary = False
                    
                    for line in lines:
                        if 'SYNC SUMMARY' in line:
                            in_summary = True
                        elif in_summary and line.strip():
                            summary_lines.append(line.strip())
                        elif in_summary and not line.strip():
                            break
                    
                    if summary_lines:
                        messages.success(
                            request,
                            format_html(
                                "Successfully synced all dandisets from DANDI archive:<br/><pre>{}</pre>",
                                '\n'.join(summary_lines[:8])  # Show first 8 lines of summary
                            )
                        )
                    else:
                        messages.success(request, "Successfully synced all dandisets from DANDI archive")
                else:
                    messages.success(request, "Successfully synced all dandisets from DANDI archive")
                    
            except Exception as e:
                messages.error(request, f"Error syncing from DANDI archive: {str(e)}")
            finally:
                output.close()
                
            # Redirect back to the changelist
            return HttpResponseRedirect(reverse('admin:dandisets_synctracker_changelist'))
        
        # For GET requests, show confirmation page
        context = {
            'title': 'Sync from DANDI Archive',
            'opts': self.model._meta,
            'has_permission': True,
            'app_label': self.model._meta.app_label,
        }
        return TemplateResponse(request, 'admin/dandisets/synctracker/sync_confirm.html', context)
    
    change_list_template = 'admin/dandisets/synctracker/change_list.html'
    
    fieldsets = (
        ('Sync Information', {
            'fields': ('sync_type', 'status', 'last_sync_timestamp', 'created_at')
        }),
        ('Statistics', {
            'fields': (
                ('dandisets_synced', 'dandisets_updated'),
                ('assets_synced', 'assets_updated'),
            )
        }),
        ('Performance', {
            'fields': (
                'sync_duration_seconds',
                'get_duration_display',
                'get_efficiency_display'
            )
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )


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


# Create a custom admin site for better organization
class DandiAdminSite(admin.AdminSite):
    site_header = "DANDI SQL Database Administration"
    site_title = "DANDI SQL Admin"
    index_title = "Welcome to DANDI SQL Database Administration"
    
    def index(self, request, extra_context=None):
        """Custom index page that groups models by category"""
        extra_context = extra_context or {}
        
        # Custom groupings for the admin index
        extra_context['sync_models'] = [
            ('dandisets', 'SyncTracker'),
        ]
        extra_context['data_models'] = [
            ('dandisets', 'Dandiset'),
            ('dandisets', 'Asset'),
            ('dandisets', 'AssetDandiset'),
            ('dandisets', 'Participant'),
        ]
        extra_context['metadata_models'] = [
            ('dandisets', 'Contributor'),
            ('dandisets', 'AssetsSummary'),
            ('dandisets', 'Activity'),
            ('dandisets', 'ContactPoint'),
            ('dandisets', 'AccessRequirements'),
            ('dandisets', 'Resource'),
        ]
        extra_context['taxonomy_models'] = [
            ('dandisets', 'SpeciesType'),
            ('dandisets', 'ApproachType'),
            ('dandisets', 'MeasurementTechniqueType'),
            ('dandisets', 'StandardsType'),
            ('dandisets', 'Anatomy'),
            ('dandisets', 'Disorder'),
            ('dandisets', 'GenericType'),
        ]
        
        return super().index(request, extra_context)


# Create the custom admin site instance
admin_site = DandiAdminSite(name='dandi_admin')

# Re-register all models with the custom admin site
admin_site.register(Dandiset, DandisetAdmin)
admin_site.register(SyncTracker, SyncTrackerAdmin)
admin_site.register(Asset, AssetAdmin)
admin_site.register(AssetDandiset, AssetDandisetAdmin)
admin_site.register(Participant, ParticipantAdmin)
admin_site.register(Contributor, ContributorAdmin)
admin_site.register(DandisetContributor, DandisetContributorAdmin)
admin_site.register(AssetsSummary, AssetsSummaryAdmin)
admin_site.register(Activity, ActivityAdmin)
admin_site.register(ContactPoint, ContactPointAdmin)
admin_site.register(AccessRequirements, AccessRequirementsAdmin)
admin_site.register(Resource, ResourceAdmin)
admin_site.register(SpeciesType, SpeciesTypeAdmin)
admin_site.register(ApproachType, ApproachTypeAdmin)
admin_site.register(MeasurementTechniqueType, MeasurementTechniqueTypeAdmin)
admin_site.register(StandardsType, StandardsTypeAdmin)
admin_site.register(Anatomy, AnatomyAdmin)
admin_site.register(Disorder, DisorderAdmin)
admin_site.register(GenericType, GenericTypeAdmin)

# Register other supporting models
admin_site.register(Affiliation)
admin_site.register(Software)
admin_site.register(Agent)
admin_site.register(Equipment)
admin_site.register(EthicsApproval)
admin_site.register(AssayType)
admin_site.register(SampleType)
admin_site.register(StrainType)
admin_site.register(SexType)

# Keep the default admin site as well for compatibility
admin.site.site_header = "DANDI SQL Database Administration"
admin.site.site_title = "DANDI SQL Admin"
admin.site.index_title = "Welcome to DANDI SQL Database Administration"
