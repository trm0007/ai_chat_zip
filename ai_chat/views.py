import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from . import services
from .models import TAB_CHOICES, APICredential, ChatMessage, Project

VALID_TABS = {key for key, _ in TAB_CHOICES}


def _project_payload(project):
    return {'id': project.id, 'name': project.name, 'updated_at': project.updated_at.isoformat()}


def _message_payload(msg):
    return {
        'id': msg.id,
        'role': msg.role,
        'content': msg.content,
        'attachment_names': msg.attachment_names,
        'created_at': msg.created_at.isoformat(),
        'files': [
            {'id': b.id, 'name': b.display_name, 'file_count': len(b.file_names)}
            for b in msg.bundles.all()
        ],
    }


@login_required
@require_http_methods(['GET', 'POST'])
def credential_view(request):
    credential = APICredential.objects.filter(user=request.user).first()

    if request.method == 'GET':
        if not credential:
            return JsonResponse({'saved': False})
        return JsonResponse({
            'saved': True,
            'provider': credential.provider,
            'model': credential.model,
            'masked_key': credential.masked_key(),
        })

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    provider = (payload.get('provider') or '').strip()
    model = (payload.get('model') or '').strip()
    api_key = (payload.get('api_key') or '').strip()

    if provider not in dict(APICredential._meta.get_field('provider').choices) or not model or not api_key:
        return JsonResponse({'error': 'provider, model and api_key are all required.'}, status=400)

    credential = credential or APICredential(user=request.user)
    credential.provider = provider
    credential.model = model
    credential.set_key(api_key)
    credential.save()

    return JsonResponse({
        'saved': True,
        'provider': credential.provider,
        'model': credential.model,
        'masked_key': credential.masked_key(),
    })


@login_required
@require_http_methods(['POST'])
def models_view(request):
    """Returns the model dropdown list for a provider. POST (not GET) so a
    typed-in-but-not-yet-saved API key never ends up in a URL/query string
    or server access log.

    Resolution order for the key used to fetch a *live* list:
      1. api_key in the request body (user is typing a new key)
      2. this user's already-saved credential, if it's for the same provider
      3. none -> static MODEL_CATALOG fallback (see services.py)
    """
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        payload = {}

    provider = (payload.get('provider') or '').strip()
    tier = (payload.get('tier') or 'all').strip()
    api_key = (payload.get('api_key') or '').strip()

    if not api_key:
        credential = APICredential.objects.filter(user=request.user, provider=provider).first()
        if credential:
            api_key = credential.get_key()

    models, meta = services.get_models_for_provider(provider, tier, api_key=api_key)
    return JsonResponse({'models': models, 'source': meta['source'], 'error': meta['error']})


@login_required
@require_http_methods(['GET', 'POST'])
def projects_view(request):
    if request.method == 'GET':
        projects = Project.objects.filter(user=request.user)
        return JsonResponse({'projects': [_project_payload(p) for p in projects]})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        payload = {}
    name = (payload.get('name') or '').strip() or 'Untitled project'
    project = Project.objects.create(user=request.user, name=name)
    return JsonResponse({'project': _project_payload(project)}, status=201)


def _get_owned_project(request, project_id):
    return get_object_or_404(Project, id=project_id, user=request.user)


@login_required
@require_http_methods(['DELETE'])
def delete_project_view(request, project_id):
    project = _get_owned_project(request, project_id)
    for bundle in project.bundles.all():
        bundle.zip_file.delete(save=False)
    project.delete()
    return JsonResponse({'deleted': True})


@login_required
@require_http_methods(['DELETE'])
def clear_project_history_view(request, project_id):
    """Wipes chat history + generated files for every tab of this project,
    but keeps the project itself."""
    project = _get_owned_project(request, project_id)
    for bundle in project.bundles.all():
        bundle.zip_file.delete(save=False)
    project.messages.all().delete()
    return JsonResponse({'cleared': True})


@login_required
@require_http_methods(['GET'])
def tab_view(request, project_id, tab_key):
    if tab_key not in VALID_TABS:
        return JsonResponse({'error': 'Unknown tab.'}, status=404)
    project = _get_owned_project(request, project_id)
    messages = project.messages.filter(tab=tab_key).prefetch_related('bundles')
    return JsonResponse({
        'project': _project_payload(project),
        'tab': tab_key,
        'messages': [_message_payload(m) for m in messages],
    })


@login_required
@require_http_methods(['POST'])
def send_message_view(request, project_id, tab_key):
    if tab_key not in VALID_TABS:
        return JsonResponse({'error': 'Unknown tab.'}, status=404)

    project = _get_owned_project(request, project_id)

    credential = APICredential.objects.filter(user=request.user).first()
    if not credential:
        return JsonResponse({'error': 'Save a provider, model and API key first.'}, status=400)

    text = (request.POST.get('message') or '').strip()
    uploads = request.FILES.getlist('attachments')
    attachment_names = [f.name for f in uploads]
    if not text and not attachment_names:
        return JsonResponse({'error': 'Message is empty.'}, status=400)

    user_content = text
    if attachment_names:
        user_content += ('\n\n' if text else '') + 'Attached files: ' + ', '.join(attachment_names)

    user_msg = ChatMessage.objects.create(
        project=project, tab=tab_key, role='user', content=user_content,
        attachment_names=attachment_names,
    )

    history_qs = project.messages.filter(tab=tab_key).order_by('created_at')
    history = [{'role': m.role, 'content': m.content} for m in history_qs]

    try:
        raw_reply = services.call_ai(
            provider=credential.provider,
            model=credential.model,
            api_key=credential.get_key(),
            system_prompt=services.build_system_prompt(tab_key, text),
            history=history,
        )
    except services.AIProviderError as exc:
        raw_reply = f"I couldn't reach the model provider: {exc}"
    except Exception as exc:  # noqa: BLE001 - never let an unexpected error 500 the request
        raw_reply = f"Something went wrong talking to the model provider: {exc}"

    visible_reply, file_directives = services.extract_file_directives(raw_reply)
    if not visible_reply and not file_directives:
        visible_reply = "I don't have a response for that."

    assistant_msg = ChatMessage.objects.create(
        project=project, tab=tab_key, role='assistant', content=visible_reply,
    )

    bundle = None
    if file_directives:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        bundle = services.save_output_bundle(
            project=project, tab=tab_key, message=assistant_msg,
            files=file_directives, zip_basename=f'{project.id}-{tab_key}-{stamp}.zip',
        )

    project.save(update_fields=['updated_at'])

    return JsonResponse({
        'user_message': _message_payload(user_msg),
        'assistant_message': _message_payload(assistant_msg),
        'bundle': (
            {'id': bundle.id, 'name': bundle.display_name, 'file_count': len(bundle.file_names)}
            if bundle else None
        ),
    })


@login_required
@require_http_methods(['GET'])
def download_bundle_view(request, bundle_id):
    from .models import OutputBundle
    bundle = get_object_or_404(OutputBundle, id=bundle_id)
    if bundle.project.user_id != request.user.id:
        return HttpResponseForbidden('Not your file.')
    return FileResponse(bundle.zip_file.open('rb'), as_attachment=True, filename=bundle.display_name)


@login_required
@require_http_methods(['PATCH', 'DELETE'])
def message_detail_view(request, message_id):
    """Edit or delete a single chat message. Scoped to project__user so a
    user can only ever touch their own messages."""
    message = get_object_or_404(ChatMessage, id=message_id, project__user=request.user)

    if request.method == 'DELETE':
        for bundle in message.bundles.all():
            bundle.zip_file.delete(save=False)
        message.delete()
        return JsonResponse({'deleted': True})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    content = (payload.get('content') or '').strip()
    if not content:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    message.content = content
    message.save(update_fields=['content'])
    return JsonResponse({'message': _message_payload(message)})
