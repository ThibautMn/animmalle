#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/.venv"

fail() { printf '%s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'HELP'
Usage : installation/install.sh PHASE
  dependencies  Préparer les dépendances backend (Debian 12/13, Ubuntu 24.04)
  schema        Créer la base absente et appliquer Alembic (étape 3)
  restore       Vérifier la possibilité de reprise du dump (étape 4 à implémenter)
  deploy        Déploiement Nginx/Gunicorn/Nuxt (étapes 5/6 à implémenter)
  all           Installation complète (indisponible avant les étapes suivantes)
  --help        Afficher cette aide
Aucune phase n'est exécutée par défaut. Ne pas lancer avec sudo.
HELP
}
[[ $# -eq 1 ]] || { usage; exit 2; }
case "$1" in
  --help|-h) usage; exit 0 ;;
  dependencies|schema|restore|deploy|all) ;;
  *) usage; exit 2 ;;
esac
[[ $EUID -ne 0 ]] || fail 'Lancer sous le compte applicatif, sans sudo.'
case "$1" in
  deploy|all)
    fail 'Déploiement indisponible : backend, frontend et configuration de production attendus aux étapes 5 et 6. Aucune modification effectuée.' ;;
  dependencies)
    [[ -r /etc/os-release ]] || fail 'Distribution non reconnue.'
    source /etc/os-release
    case "${ID:-}:${VERSION_ID:-}" in
      debian:12|debian:13|ubuntu:24.04) ;;
      *) fail 'Distributions prises en charge : Debian 12/13, Ubuntu 24.04.' ;;
    esac
    command -v sudo >/dev/null || fail 'sudo est requis pour les paquets système.'
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || fail 'Python >= 3.10 requis.'
    [[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_DIR/backend/requirements.txt"
    "$VENV/bin/python" -m pip check
    printf '%s\n' 'Dépendances backend préparées. Dépendances frontend différées : manifeste absent.'
    ;;
  schema|restore)
    [[ -x "$VENV/bin/python" ]] || fail 'Préparer les dépendances avec la phase dependencies.'
    "$VENV/bin/python" "$SCRIPT_DIR/lib/database.py" "$1"
    ;;
esac
