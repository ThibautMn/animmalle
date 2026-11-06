"""Fichiers hors ressources publiques ; médias, pages et révisions."""
import hashlib
import io
import json
import os
import re
import tempfile
import shutil
import subprocess
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
from xml.sax.saxutils import escape

import markdown
import nh3
from flask import current_app, abort
from werkzeug.utils import secure_filename


def paths():
    return current_app.extensions['settings']['paths']


def render(content):
    return nh3.clean(markdown.markdown(content), link_rel='noopener noreferrer')


def media_path(item):
    # Ne jamais interpréter le chemin absolu issu du dump comme un accès libre.
    name = Path(item.url).name
    if not name or not item.url:
        abort(404, description='Aucun fichier associé.')
    root = paths()['uploads']
    candidate = (root / name).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    abort(404, description='Fichier absent ; les médias historiques doivent être disponibles.')


def store_upload(file):
    name = secure_filename(file.filename or '')
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if extension not in current_app.extensions['settings']['backend']['allowed_extensions']:
        abort(422, description='Extension de fichier non autorisée.')
    root = paths()['uploads']
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            while chunk := file.stream.read(1024 * 1024):
                digest.update(chunk)
                stream.write(chunk)
        target = root / f'{digest.hexdigest()}_{name[:160]}'
        # lien atomique : aucun écrasement, y compris lors d'uploads concurrents.
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        return target.name
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def page_directory(name):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', name):
        abort(404)
    root = paths()['pages']
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        abort(404)
    return candidate


def read_page(name):
    directory = page_directory(name)
    source = directory / 'current.md'
    if source.is_file() and source.resolve().is_relative_to(directory):
        content = source.read_text(encoding='utf-8')
        return {'name': name, 'contenu': content, 'html': render(content)}
    abort(404, description='Page introuvable.')


def write_page(name, content):
    directory = page_directory(name)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        previous = read_page(name)['contenu']
    except Exception as error:
        from werkzeug.exceptions import NotFound
        if not isinstance(error, NotFound):
            raise
        previous = None
    if previous is not None:
        revision = datetime.now(timezone.utc).strftime('rev_%Y_%m_%d_%H%M%S_%f.md')
        (directory / revision).write_text(previous, encoding='utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, directory / 'current.md')
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return read_page(name)


def odt_document(title, sections):
    """Document ODF éditable sans dépendre des templates py3o historiques."""
    paragraphs = [f'<text:h text:outline-level="1">{escape(title)}</text:h>']
    for label, value in sections:
        paragraphs.append(f'<text:h text:outline-level="2">{escape(label)}</text:h>')
        # Conserver le Markdown source dans l'export : aucune perte de contenu.
        for line in str(value or '').splitlines():
            paragraphs.append(f'<text:p xml:space="preserve">{escape(line)}</text:p>')
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">'
               '<office:body><office:text>' + ''.join(paragraphs) + '</office:text></office:body></office:document-content>')
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('mimetype', 'application/vnd.oasis.opendocument.text', compress_type=ZIP_STORED)
        archive.writestr('content.xml', content, compress_type=ZIP_DEFLATED)
        archive.writestr('META-INF/manifest.xml', '<?xml version="1.0"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>')
    return output.getvalue()


def export_archive(title, data, materials, sections):
    from werkzeug.exceptions import NotFound
    output = io.BytesIO()
    missing = []
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr((secure_filename(title) or 'document') + '.odt', odt_document(title, sections))
        archive.writestr('donnees.json', json.dumps(data, ensure_ascii=False, indent=2))
        for item in {item.id: item for item in materials}.values():
            if not item.url:
                continue
            try:
                source = media_path(item)
                archive.write(source, f'medias/{item.id}_{source.name}')
            except NotFound:
                missing.append(item.id)
        archive.writestr('fichiers_absents.json', json.dumps(missing))
    output.seek(0)
    return output


def preview_file(item):
    """Renvoie un média natif ou un PDF temporaire, sans toucher à l'original."""
    source = media_path(item)
    mime = mimetypes.guess_type(source.name)[0] or 'application/octet-stream'
    if mime in {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf'} or mime.startswith(('audio/', 'video/')):
        return source, mime
    if source.suffix.lower() not in {'.odt', '.ods', '.odp', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf'}:
        abort(415, description='Aperçu indisponible pour ce format. Utilisez le téléchargement.')
    executable = shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:
        abort(503, description='LibreOffice doit être installé sur le serveur pour cet aperçu.')
    with tempfile.TemporaryDirectory(prefix='animmalle-preview-') as directory:
        root = Path(directory)
        profile = root / 'profile'
        user = profile / 'user'
        user.mkdir(parents=True)
        # Désactiver les macros dans le profil dédié à cette conversion.
        (user / 'registrymodifications.xcu').write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '</item></oor:items>', encoding='utf-8')
        try:
            subprocess.run(
                [executable, f'-env:UserInstallation={profile.as_uri()}', '--headless',
                 '--convert-to', 'pdf', '--outdir', str(root), str(source)],
                check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.SubprocessError, OSError):
            abort(422, description='La conversion du document a échoué. Utilisez le téléchargement.')
        output = root / (source.stem + '.pdf')
        if not output.is_file():
            abort(422, description='Aucun aperçu PDF produit. Utilisez le téléchargement.')
        return io.BytesIO(output.read_bytes()), 'application/pdf'
