from django import forms
from django.contrib import admin, messages

from . import services
from .models import APICredential, ChatMessage, EmbeddingSettings, OutputBundle, Project, SourceDocument


@admin.register(APICredential)
class APICredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'model', 'updated_at')
    readonly_fields = ('encrypted_key',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'updated_at')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('project', 'tab', 'role', 'created_at')
    list_filter = ('tab', 'role')


@admin.register(OutputBundle)
class OutputBundleAdmin(admin.ModelAdmin):
    list_display = ('project', 'tab', 'display_name', 'created_at')


@admin.action(description='Rescan ai_chat/source/ and reindex changed files')
def rescan_source_folder(modeladmin, request, queryset):
    # Ignores the selected rows on purpose — this always rescans the whole
    # folder, since that's the only way to also pick up brand-new files
    # (which by definition can't be "selected" yet) and files removed
    # from disk.
    result = services.index_sources()
    summary = (
        f"{len(result['added'])} added, {len(result['updated'])} updated, "
        f"{len(result['skipped'])} unchanged, {len(result['removed'])} removed, "
        f"{len(result['errors'])} errors."
    )
    level = messages.ERROR if result['errors'] else messages.SUCCESS
    modeladmin.message_user(request, summary, level)
    for path, error in result['errors']:
        modeladmin.message_user(request, f'{path}: {error}', messages.ERROR)


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    """Read-only — rows are populated by scanning ai_chat/source/ (via
    `python manage.py index_sources` or the action below), not created
    here. Admin manages the actual files on disk."""
    list_display = ('relative_path', 'status', 'chunk_count', 'indexed_at')
    list_filter = ('status',)
    readonly_fields = ('relative_path', 'file_hash', 'status', 'processing_error', 'chunk_count', 'indexed_at', 'updated_at')
    actions = [rescan_source_folder]

    def has_add_permission(self, request):
        return False


class EmbeddingSettingsForm(forms.ModelForm):
    api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Paste a new key to replace the stored one. Leave blank to keep the current key.',
    )

    class Meta:
        model = EmbeddingSettings
        fields = ['provider', 'model']

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_key = self.cleaned_data.get('api_key')
        if raw_key:
            instance.set_key(raw_key)
        if commit:
            instance.save()
        return instance


@admin.register(EmbeddingSettings)
class EmbeddingSettingsAdmin(admin.ModelAdmin):
    form = EmbeddingSettingsForm
    list_display = ('provider', 'model', 'has_key', 'updated_at')

    def has_key(self, obj):
        return bool(obj.encrypted_key)
    has_key.boolean = True
    has_key.short_description = 'Key set'

    def has_add_permission(self, request):
        # Singleton row — edit the existing one instead of adding another.
        return not EmbeddingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
