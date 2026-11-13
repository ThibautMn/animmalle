"""Fichiers hors ressources publiques ; médias, pages et révisions."""
import hashlib
import io
import json
import os
import re
import tempfile
import shutil
import subprocess
import time
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
from xml.sax.saxutils import escape

import markdown
import nh3
from PIL import Image, ImageOps, ImageStat
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


PICTOGRAM_MAX_BYTES = 1024 * 1024


def pictogram_path(item, must_exist=True):
    """Chemin du PNG d'un terme (nommé d'après son libellé, comme dans l'ancienne version)."""
    root = paths()['pictograms'].resolve()
    source = (root / ((item.label or '') + '.png')).resolve()
    if not item.label or source.parent != root:
        abort(422, description='Libellé incompatible avec un nom de fichier.')
    if must_exist and not source.is_file():
        abort(404, description='Aucun pictogramme.')
    return source


def store_pictogram(item, file):
    target = pictogram_path(item, must_exist=False)
    data = file.stream.read(PICTOGRAM_MAX_BYTES + 1)
    if len(data) > PICTOGRAM_MAX_BYTES:
        abort(422, description='Pictogramme trop volumineux (1 Mo maximum).')
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        abort(422, description='Le pictogramme doit être une image PNG.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    os.replace(temporary, target)


def rename_pictogram(item, new_label, shared=False):
    """Suit le renommage d'un terme ; ne remplace jamais un fichier existant."""
    if item.label == new_label:
        return
    try:
        source = pictogram_path(item)
        old = Path(source)
        item_label, item.label = item.label, new_label
        try:
            target = pictogram_path(item, must_exist=False)
        finally:
            item.label = item_label
        if not target.exists():
            (shutil.copyfile if shared else os.rename)(old, target)
    except Exception:
        # pas de pictogramme ou nom invalide : rien à déplacer
        pass


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


THUMBNAIL_SIZE = (480, 360)
THUMBNAIL_QUALITY = 70


def thumbnail_directory():
    # Dossier distinct des originaux, qui ne sont jamais modifiés.
    configured = paths().get('thumbnails')
    return configured or paths()['uploads'].with_name(paths()['uploads'].name + '_vignettes')


def thumbnail_file(item):
    """Renvoie une vignette JPEG réduite, générée une fois puis mise en cache sur disque."""
    source = media_path(item)
    mime = mimetypes.guess_type(source.name)[0] or ''
    is_video = mime.startswith('video/')
    if not is_video and not mime.startswith('image/'):
        abort(415, description='Vignette indisponible pour ce format.')
    stat = source.stat()
    key = hashlib.sha256(f'{source.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    directory = thumbnail_directory()
    target = directory / f'{key}.jpg'
    if target.is_file():
        return target
    if is_video and not shutil.which('ffmpeg'):
        abort(503, description='ffmpeg doit être installé sur le serveur pour les vignettes vidéo.')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='animmalle-vignette-', dir=directory) as work:
        raw = Path(work) / 'image.jpg'
        try:
            if is_video:
                # Plusieurs instants : l'ouverture d'une vidéo est souvent noire (fondu d'entrée).
                for moment in ('0.1', '1', '3', '10'):
                    subprocess.run(
                        ['ffmpeg', '-v', 'error', '-y', '-ss', moment, '-i', str(source), '-frames:v', '1',
                         '-vf', f'scale={THUMBNAIL_SIZE[0]}:-2', str(raw)],
                        check=True, timeout=30, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if not raw.is_file():  # instant au-delà de la fin de la vidéo
                        break
                    with Image.open(raw) as candidate:
                        if ImageStat.Stat(candidate.convert('L')).mean[0] > 12:
                            break
                if not raw.is_file():
                    subprocess.run(
                        ['ffmpeg', '-v', 'error', '-i', str(source), '-frames:v', '1',
                         '-vf', f'scale={THUMBNAIL_SIZE[0]}:-2', str(raw)],
                        check=True, timeout=30, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                picture = Image.open(raw)
            else:
                picture = Image.open(source)
            with picture:
                picture = ImageOps.exif_transpose(picture)
                picture.thumbnail(THUMBNAIL_SIZE)
                if picture.mode in ('RGBA', 'LA', 'P'):
                    picture = picture.convert('RGBA')
                    background = Image.new('RGB', picture.size, 'white')
                    background.paste(picture, mask=picture.getchannel('A'))
                    picture = background
                else:
                    picture = picture.convert('RGB')
                picture.save(Path(work) / 'vignette.jpg', 'JPEG', quality=THUMBNAIL_QUALITY, optimize=True)
        except (subprocess.SubprocessError, OSError, Image.DecompressionBombError, ValueError):
            abort(422, description='Vignette impossible à générer. Utilisez l’aperçu ou le téléchargement.')
        os.replace(Path(work) / 'vignette.jpg', target)
    return target


FOREIGN_VIDEO_EXTENSIONS = {'.avi', '.wmv', '.mpg', '.mpeg', '.mkv', '.flv', '.3gp'}
PROBED_VIDEO_EXTENSIONS = {'.mp4', '.m4v', '.mov'}
MAX_NATIVE_BIT_RATE = 40_000_000
TRANSCODE_WAIT_SECONDS = 40
TRANSCODE_STALE_SECONDS = 1800
TRANSCODE_SCRIPT = (
    'ffmpeg -v error -nostdin -y -i "$1" -c:v libx264 -preset veryfast -crf 26 '
    '-vf "scale=min(1280\\,iw):-2" -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart -f mp4 "$2" '
    '&& mv "$2" "$3" || rm -f "$2"')


def needs_video_conversion(source):
    """Vrai si le navigateur ne peut pas lire la vidéo (conteneur AVI/WMV…, codec HEVC…, débit excessif)."""
    suffix = source.suffix.lower()
    if suffix in FOREIGN_VIDEO_EXTENSIONS:
        return True
    if suffix not in PROBED_VIDEO_EXTENSIONS or not shutil.which('ffprobe'):
        return False
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,bit_rate',
             '-of', 'csv=p=0', str(source)],
            check=True, timeout=15, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return False
    codec, _, bit_rate = result.stdout.strip().partition(',')
    if codec not in ('h264', 'vp8', 'vp9', 'av1'):
        return codec != ''
    # Un débit bien supérieur au niveau H.264 déclaré fait caler le décodeur du navigateur sur la première image.
    return bit_rate.strip().isdigit() and int(bit_rate) > MAX_NATIVE_BIT_RATE


def playable_video(source):
    """Renvoie une copie MP4 H.264 mise en cache ; la conversion longue continue en arrière-plan (503 d'ici là)."""
    if not shutil.which('ffmpeg'):
        abort(503, description='ffmpeg doit être installé sur le serveur pour lire ce format de vidéo.')
    stat = source.stat()
    key = hashlib.sha256(f'lecture:{source.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    directory = thumbnail_directory() / 'lecture'
    target = directory / f'{key}.mp4'
    if target.is_file():
        return target
    directory.mkdir(parents=True, exist_ok=True)
    part = directory / f'{key}.part'
    if part.exists():
        if time.time() - part.stat().st_mtime < TRANSCODE_STALE_SECONDS:
            abort(503, description='Conversion de la vidéo en cours ; réessayez dans quelques minutes.')
        part.unlink(missing_ok=True)
    try:
        process = subprocess.Popen(
            ['sh', '-c', TRANSCODE_SCRIPT, 'sh', str(source), str(part), str(target)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        abort(422, description='La conversion de la vidéo a échoué. Utilisez le téléchargement.')
    try:
        process.wait(timeout=TRANSCODE_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        abort(503, description='Conversion de la vidéo en cours ; réessayez dans quelques minutes.')
    if not target.is_file():
        abort(422, description='La conversion de la vidéo a échoué. Utilisez le téléchargement.')
    return target


def preview_file(item):
    """Renvoie un média natif ou un PDF temporaire, sans toucher à l'original."""
    source = media_path(item)
    mime = mimetypes.guess_type(source.name)[0] or 'application/octet-stream'
    if mime.startswith('video/') and needs_video_conversion(source):
        return playable_video(source), 'video/mp4'
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
