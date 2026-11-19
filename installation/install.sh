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
NVM_VERSION="${NVM_VERSION:-v0.40.3}"
NODE_MAJOR="${NODE_MAJOR:-24}"
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
node_compatible() {
  command -v node >/dev/null && command -v npm >/dev/null && node -e 'const [a,b,c] = process.versions.node.split(".").map(Number); process.exit((a === 22 && (b > 22 || b === 22 && c >= 3)) || (a === 24 && b >= 15) || a >= 26 ? 0 : 1)'
}
load_nvm() {
  [[ -s "$NVM_DIR/nvm.sh" ]] || return 1
  export NVM_DIR
  set +eu
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  local status=$?
  set -eu
  return $status
}
ensure_node() {
  # Node déjà utilisable (PATH, ou nvm déjà installé) : rien à faire.
  node_compatible && return 0
  load_nvm || true
  node_compatible && return 0
  if ! command -v nvm >/dev/null 2>&1; then
    command -v curl >/dev/null || fail 'curl est requis pour installer nvm (lancer la phase dependencies).'
    printf 'Installation de nvm %s dans %s\n' "$NVM_VERSION" "$NVM_DIR"
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | PROFILE=/dev/null bash
    load_nvm || fail 'nvm installé mais introuvable.'
  fi
  printf 'Installation de Node %s (LTS) via nvm\n' "$NODE_MAJOR"
  set +eu
  nvm install "$NODE_MAJOR" && nvm alias default "$NODE_MAJOR" >/dev/null && nvm use "$NODE_MAJOR" >/dev/null
  local status=$?
  set -eu
  [[ $status -eq 0 ]] || fail 'Échec de l’installation de Node via nvm.'
  node_compatible || fail "Node $NODE_MAJOR installé mais incompatible avec Nuxt (>= 24.15 requis)."
}
usage() {
  cat <<'HELP'
Usage : installation/install.sh PHASE
  dependencies  Préparer les dépendances backend, dont ffmpeg (vignettes vidéo) et poppler-utils (vignettes PDF) (Debian 12/13, Ubuntu 24.04)
  node          Installer nvm puis Node 24 LTS s'ils sont absents ou incompatibles (sans sudo, dans ~/.nvm)
  frontend      Installer Node si nécessaire, puis les dépendances verrouillées et construire Nuxt (Node >= 22.22.3 compatible)
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
  dependencies|node|frontend|prepare|schema|restore|deploy|all) ;;
  *) usage; exit 2 ;;
esac
[[ $EUID -ne 0 ]] || fail 'Lancer sous le compte applicatif, sans sudo.'
case "$1" in
  all)
    for phase in dependencies node frontend schema restore deploy; do
      "$SCRIPT_DIR/install.sh" "$phase"
    done
    ;;
  node)
    ensure_node
    printf 'Node %s et npm %s disponibles.\n' "$(node --version)" "$(npm --version)"
    ;;
  frontend)
    ensure_node
    cd "$PROJECT_DIR/frontend"
    npm ci
    npm run test
    npm run build
    ;;
  prepare|deploy)
    [[ -x "$VENV/bin/python" ]] || fail 'Préparer les dépendances backend.'
    command -v node >/dev/null || load_nvm || true
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
    sudo apt-get install -y python3 python3-venv ffmpeg poppler-utils curl ca-certificates
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail 'Python >= 3.11 requis.'
    [[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_DIR/backend/requirements.txt"
    "$VENV/bin/python" -m pip check
    if [[ -f "$SCRIPT_DIR/config_principal.yaml" ]]; then
      pg_host="$("$VENV/bin/python" -c 'import sys,yaml; print((yaml.safe_load(open(sys.argv[1])) or {}).get("postgresql",{}).get("host",""))' "$SCRIPT_DIR/config_principal.yaml" 2>/dev/null || true)"
      case "$pg_host" in
        localhost|127.0.0.1|::1)
          sudo apt-get install -y postgresql
          sudo systemctl enable --now postgresql
          ;;
      esac
    else
      printf '%s\n' 'config_principal.yaml absent : PostgreSQL local non installé (relancer dependencies après sa création).'
    fi
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
