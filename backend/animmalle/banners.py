"""Bannières de la page d'accueil : images de backend/bannières et hauteur de cadrage de chacune."""
import json
import os
import secrets
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

BANNERS_DIR = Path(__file__).resolve().parents[1] / 'bannières'
POSITIONS = 'positions.json'
FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}
MIMES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
MAX_PIXELS = 40_000_000


def names():
    if not BANNERS_DIR.is_dir():
        return []
    return sorted(p.name for p in BANNERS_DIR.iterdir() if p.is_file() and p.suffix.lower() in MIMES)


def path_of(name):
    """Chemin d'une bannière existante, ou None (aucun nom venant du client n'atteint le disque tel quel)."""
    return BANNERS_DIR / name if name in names() else None


def mime(name):
    return MIMES[Path(name).suffix.lower()]


def _positions():
    try:
        data = json.loads((BANNERS_DIR / POSITIONS).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    target = BANNERS_DIR / POSITIONS
    temp = target.with_name(f'.{POSITIONS}.{secrets.token_hex(4)}')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temp, target)


def position(name):
    """Hauteur du cadrage en pourcentage (0 = haut de l'image, 100 = bas) ; 50 par défaut."""
    value = _positions().get(name, 50)
    return value if isinstance(value, int) and 0 <= value <= 100 else 50


def listing():
    return [{'name': name, 'position': position(name)} for name in names()]


def set_position(name, value):
    data = _positions()
    data[name] = value
    _write({k: v for k, v in data.items() if k in names()})


def remove(name):
    (BANNERS_DIR / name).unlink()
    data = _positions()
    if data.pop(name, None) is not None:
        _write(data)


def store(file):
    """Enregistre une image téléversée sous un nom unique ; retourne ce nom ou None si ce n'est pas une image."""
    try:
        with Image.open(file.stream) as picture:
            suffix = FORMATS.get(picture.format)
            if not suffix or picture.width * picture.height > MAX_PIXELS:
                return None
            picture.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        return None
    stem = secure_filename(Path(file.filename or '').stem)[:60] or 'banniere'
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    file.stream.seek(0)
    for _ in range(20):
        name = f'{stem}_{secrets.token_hex(3)}{suffix}'
        try:
            with open(BANNERS_DIR / name, 'xb') as out:
                out.write(file.stream.read())
            return name
        except FileExistsError:
            file.stream.seek(0)
    return None
