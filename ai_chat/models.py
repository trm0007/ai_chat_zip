import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

TAB_CHOICES = [
    ('build_model', 'Build Model'),
    ('run_analysis', 'Run Analysis'),
    ('post_processing', 'Post Processing'),
    ('design', 'Design'),
]

PROVIDER_CHOICES = [
    ('anthropic', 'Anthropic'),
    ('openai', 'OpenAI'),
    ('google', 'Google'),
    ('mistral', 'Mistral'),
]

# Anthropic has no public embeddings endpoint, so it's excluded here — the
# embedding provider is configured separately from each user's own chat
# provider (see EmbeddingSettings below).
EMBEDDING_PROVIDER_CHOICES = [
    ('openai', 'OpenAI'),
    ('google', 'Google'),
    ('mistral', 'Mistral'),
]


def _fernet():
    """Derive a stable Fernet key from the project's SECRET_KEY so API
    keys are never stored in the database in plain text."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class APICredential(models.Model):
    """One saved provider/model/key per user (matches the sidebar 'Provide
    your key' card — saving again simply overwrites the previous key)."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_credential'
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    model = models.CharField(max_length=100)
    encrypted_key = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def set_key(self, raw_key):
        self.encrypted_key = _fernet().encrypt(raw_key.encode()).decode()

    def get_key(self):
        try:
            return _fernet().decrypt(self.encrypted_key.encode()).decode()
        except InvalidToken:
            return ''

    def masked_key(self):
        key = self.get_key()
        if not key:
            return ''
        if len(key) <= 8:
            return '•' * len(key)
        return key[:4] + '•' * 10 + key[-4:]

    def __str__(self):
        return f'{self.user} · {self.provider}/{self.model}'


class Project(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_projects')
    name = models.CharField(max_length=150, default='Untitled project')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class ChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'user'), ('assistant', 'assistant')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='messages')
    tab = models.CharField(max_length=20, choices=TAB_CHOICES)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)
    attachment_names = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.project_id}/{self.tab} · {self.role}'


def output_upload_path(instance, filename):
    return (
        f'ai_chat_outputs/user_{instance.project.user_id}/'
        f'project_{instance.project_id}/{instance.tab}/{filename}'
    )


class OutputBundle(models.Model):
    """A zip of every file the AI generated for one reply, scoped to a
    single project + tab so tabs never share downloads."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='bundles')
    tab = models.CharField(max_length=20, choices=TAB_CHOICES)
    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name='bundles', null=True, blank=True
    )
    zip_file = models.FileField(upload_to=output_upload_path)
    file_names = models.JSONField(default=list, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def display_name(self):
        return self.zip_file.name.rsplit('/', 1)[-1]


class SourceDocument(models.Model):
    """Tracks one file the admin manually placed in the source/ folder
    (pdf/docx/xlsx/pptx/dxf/json/txt/md/csv — everything except
    tab1.md…tab4.md, which are read directly as per-tab instructions
    instead of being indexed). Populated by `python manage.py
    index_sources`, which scans the folder and keeps this table in sync
    with whatever's actually on disk."""
    STATUS_CHOICES = [
        ('pending', 'Not processed yet'),
        ('processed', 'Processed'),
        ('error', 'Error'),
    ]

    relative_path = models.CharField(max_length=500, unique=True)
    file_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    processing_error = models.TextField(blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    indexed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['relative_path']

    def __str__(self):
        return self.relative_path


class SourceChunk(models.Model):
    """One embedded chunk of a SourceDocument's extracted text, used for
    similarity search against a user's question."""
    document = models.ForeignKey(SourceDocument, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = models.JSONField()

    class Meta:
        ordering = ['document_id', 'chunk_index']

    def __str__(self):
        return f'{self.document} #{self.chunk_index}'


class EmbeddingSettings(models.Model):
    """Singleton: which provider/key/model embeds source documents and
    user questions for retrieval. Kept separate from each user's own
    per-chat APICredential, since indexing happens admin-side once and
    every later query's embedding must stay comparable to it — mixing in
    whichever provider a given user happens to be chatting with would
    silently break retrieval."""
    provider = models.CharField(max_length=20, choices=EMBEDDING_PROVIDER_CHOICES, default='openai')
    model = models.CharField(max_length=100, default='text-embedding-3-small')
    encrypted_key = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_key(self, raw_key):
        self.encrypted_key = _fernet().encrypt(raw_key.encode()).decode()

    def get_key(self):
        try:
            return _fernet().decrypt(self.encrypted_key.encode()).decode()
        except InvalidToken:
            return ''

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f'Embedding settings · {self.provider}/{self.model}'
