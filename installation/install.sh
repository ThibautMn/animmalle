#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/.venv"

fail() { printf '%s\n' "$*" >&2; exit 1; }
authenticate_sudo() {
  command -v sudo >/dev/null || fail 'sudo est requis pour préparer PostgreSQL local.'
  printf '%s\n' 'Authentification administrateur : saisir le mot de passe dans le terminal si sudo le demande.'
  sudo -v
}
usage() {
  cat <<'HELP'
Usage : installation/install.sh PHASE
  dependencies  Préparer les dépendances backend, dont ffmpeg (vignettes vidéo) et poppler-utils (vignettes PDF) (Debian 12/13, Ubuntu 24.04)
  frontend      Installer les dépendances verrouillées et construire Nuxt (Node >= 22.22.3 compatible)
  prepare       Générer Nginx/systemd sans les appliquer
  schema        Créer la base absente et appliquer Alembic (étape 3)
  restore       Reprendre les données du dump MariaDB sur une base vide (étape 4)
  deploy        Installer Nginx/systemd et redémarrer les services applicatifs
  all           dependencies, frontend, schema, restore puis deploy
  --help        Afficher cette aide
Aucune phase n'est exécutée par défaut. Ne pas lancer avec sudo.
HELP
}
[[ $# -eq 1 ]] || { usage; exit 2; }
case "$1" in
  --help|-h) usage; exit 0 ;;
  dependencies|frontend|prepare|schema|restore|deploy|all) ;;
  *) usage; exit 2 ;;
esac
[[ $EUID -ne 0 ]] || fail 'Lancer sous le compte applicatif, sans sudo.'
case "$1" in
  all)
    for phase in dependencies frontend schema restore deploy; do
      "$SCRIPT_DIR/install.sh" "$phase"
    done
    ;;
  frontend)
    command -v node >/dev/null || fail 'Installer Node 24 LTS (>= 24.15), puis relancer.'
    command -v npm >/dev/null || fail 'npm est requis.'
    node -e 'const [a,b,c] = process.versions.node.split(".").map(Number); process.exit((a === 22 && (b > 22 || b === 22 && c >= 3)) || (a === 24 && b >= 15) || a >= 26 ? 0 : 1)' || fail 'Node incompatible avec Nuxt ; utiliser Node 24 LTS >= 24.15.'
    cd "$PROJECT_DIR/frontend"
    npm ci
    npm run test
    npm run build
    ;;
  prepare|deploy)
    [[ -x "$VENV/bin/python" ]] || fail 'Préparer les dépendances backend.'
    if [[ "$1" == deploy ]]; then
      authenticate_sudo
      command -v nginx >/dev/null || fail 'Installer Nginx avant deploy.'
      "$VENV/bin/python" "$SCRIPT_DIR/lib/deploy.py" apply
    else
      "$VENV/bin/python" "$SCRIPT_DIR/lib/deploy.py" prepare
    fi
    ;;
  dependencies)
    [[ -r /etc/os-release ]] || fail 'Distribution non reconnue.'
    source /etc/os-release
    case "${ID:-}:${VERSION_ID:-}" in
      debian:12|debian:13|ubuntu:24.04) ;;
      *) fail 'Distributions prises en charge : Debian 12/13, Ubuntu 24.04.' ;;
    esac
    authenticate_sudo
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv ffmpeg poppler-utils
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail 'Python >= 3.11 requis.'
    [[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_DIR/backend/requirements.txt"
    "$VENV/bin/python" -m pip check
    printf '%s\n' 'Dépendances backend préparées. Utiliser la phase frontend pour Nuxt.'
    ;;
  schema|restore)
    [[ -x "$VENV/bin/python" ]] || fail 'Préparer les dépendances avec la phase dependencies.'
    if [[ "$1" == schema ]]; then
      authenticate_sudo
    fi
    "$VENV/bin/python" "$SCRIPT_DIR/lib/database.py" "$1"
    ;;
esac
