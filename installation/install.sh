#!/usr/bin/env bash
# Installateur AnimMalle par phases (voir installation/README.md).
# Principes, tirés des incidents des premières installations :
#  - tout contrôler avant d'agir (phase check, lancée aussi en tête de « all ») ;
#  - installer soi-même chaque prérequis manquant, détecté par paquet et non par le PATH ;
#  - une seule règle de lecture du YAML (lib/check.py), partagée par toutes les phases ;
#  - en cas d'échec, nommer la phase, la ligne et la commande ; journaliser dans installation/logs ;
#  - vérifier réellement le résultat (services actifs, API et Nuxt joignables via Nginx).
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/.venv"
CONFIG="$SCRIPT_DIR/config_principal.yaml"
PHASE="${1:-}"
# Un compte non root n'a souvent pas /usr/sbin dans son PATH (nginx, ss…).
PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"
export PATH

NVM_VERSION="${NVM_VERSION:-v0.40.3}"
NODE_MAJOR="${NODE_MAJOR:-24}"
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
PG_LOCAL=0
KEEPALIVE_PID=''
TEE_PID=''
SYSTEM_PACKAGES=(python3 python3-venv ffmpeg poppler-utils libreoffice-writer fonts-liberation curl ca-certificates nginx iproute2)

say() { printf '==> %s\n' "$*"; }
warn() { printf 'Attention : %s\n' "$*" >&2; }
fail() { printf 'ERREUR [%s] : %s\n' "${PHASE:-install}" "$*" >&2; exit 1; }
on_error() {
  local status=$? line=$1 command=$2
  printf 'ERREUR [%s] : la commande « %s » a échoué (code %s, install.sh ligne %s).\n' \
    "${PHASE:-install}" "$command" "$status" "$line" >&2
  [[ -n "${INSTALL_LOG:-}" ]] && printf 'Journal complet : %s\n' "$INSTALL_LOG" >&2
  exit "$status"
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

usage() {
  cat <<'HELP'
Usage : installation/install.sh PHASE
  check         Contrôler système, YAML et prérequis sans rien modifier (sans sudo)
  dependencies  Paquets système (Python, Nginx, ffmpeg, poppler-utils, LibreOffice Writer, curl, PostgreSQL si local), venv et dépendances backend
  node          Installer nvm puis Node 24 LTS s'ils sont absents ou incompatibles (sans sudo, dans ~/.nvm)
  frontend      Installer Node si nécessaire, puis les dépendances verrouillées, tests et build Nuxt
  schema        Créer rôle et base absents, puis appliquer Alembic (étape 3)
  restore       Reprendre les données du dump sur une base vide (étape 4)
  prepare       Générer Nginx/systemd dans installation/generated sans les appliquer
  deploy        Installer Nginx/systemd, redémarrer les services et vérifier le routage
  all           dependencies, check, node, frontend, schema, restore puis deploy
  --help        Afficher cette aide
Aucune phase n'est exécutée par défaut. Ne pas lancer avec sudo.
Supporté : Debian 12/13, Ubuntu 24.04. Journal : installation/logs/install-*.log
HELP
}

# --- Journal ---------------------------------------------------------------
cleanup() {
  [[ -z "$KEEPALIVE_PID" ]] || kill "$KEEPALIVE_PID" 2>/dev/null || true
  if [[ -n "$TEE_PID" ]]; then
    exec 1>&- 2>&-
    wait "$TEE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
start_log() {
  # Une seule journalisation pour « all » et ses sous-phases.
  if [[ -n "${INSTALL_LOG:-}" ]]; then
    say "Phase $PHASE"
    return 0
  fi
  mkdir -p "$SCRIPT_DIR/logs"
  INSTALL_LOG="$SCRIPT_DIR/logs/install-$(date +%Y%m%d-%H%M%S)-$PHASE.log"
  export INSTALL_LOG
  exec > >(tee -a "$INSTALL_LOG") 2>&1
  TEE_PID=$!
  say "Phase $PHASE — $(date '+%F %T') — journal : $INSTALL_LOG"
}

# --- Système ---------------------------------------------------------------
check_os() {
  [[ -r /etc/os-release ]] || fail 'Distribution non reconnue (/etc/os-release absent).'
  # shellcheck disable=SC1091
  ( . /etc/os-release; case "${ID:-}:${VERSION_ID:-}" in debian:12|debian:13|ubuntu:24.04) ;; *) exit 1 ;; esac ) \
    || fail 'Distributions prises en charge : Debian 12/13, Ubuntu 24.04.'
}
authenticate_sudo() {
  command -v sudo >/dev/null || fail 'sudo est requis pour les opérations système.'
  if ! sudo -n true 2>/dev/null; then
    say 'Authentification administrateur : saisir le mot de passe dans le terminal si sudo le demande.'
  fi
  sudo -v || fail 'Authentification sudo refusée.'
}
start_sudo_keepalive() {
  # Les phases longues (npm, build) dépassent le délai sudo : le renouveler en arrière-plan.
  ( while kill -0 "$$" 2>/dev/null; do sudo -n true || exit 0; sleep 50; done ) </dev/null >/dev/null 2>&1 &
  KEEPALIVE_PID=$!
}
package_installed() {
  # python3-venv est un métapaquet : python3.X-venv suffit.
  [[ "$1" != python3-venv ]] || ! python3 -c 'import ensurepip, venv' 2>/dev/null || return 0
  [[ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$1" 2>/dev/null)" == ii* ]]
}
# Tout serveur PostgreSQL (Debian ou dépôt PGDG, quelle que soit la version) convient :
# ne jamais installer le métapaquet « postgresql » à côté d'un serveur existant (second cluster).
postgres_server_installed() {
  dpkg-query -W -f='${Package} ${db:Status-Abbrev}\n' 'postgresql-[0-9]*' 2>/dev/null | grep -Eq '^postgresql-[0-9]+ ii'
}
# Vérifie qu'un cluster local en ligne écoute sur le port du YAML.
postgres_cluster_online() {
  command -v pg_lsclusters >/dev/null || return 1
  pg_lsclusters -h 2>/dev/null | awk -v port="$1" '$3 == port && $4 ~ /^online/ { found = 1 } END { exit !found }'
}
ensure_postgres() {
  if postgres_server_installed; then
    say 'Serveur PostgreSQL local déjà installé : conservé tel quel.'
  else
    ensure_packages postgresql
  fi
  sudo systemctl enable --now postgresql
  postgres_cluster_online "$PG_PORT" \
    || fail "aucun cluster PostgreSQL en ligne sur le port $PG_PORT (voir « pg_lsclusters ») : aligner postgresql.port du YAML ou démarrer le cluster."
}
ensure_packages() {
  local missing=() package
  for package in "$@"; do package_installed "$package" || missing+=("$package"); done
  if (( ${#missing[@]} == 0 )); then
    say "Paquets système présents : $*"
    return 0
  fi
  say "Installation des paquets manquants : ${missing[*]}"
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

# --- Configuration ---------------------------------------------------------
check_config_file() {
  [[ -f "$CONFIG" ]] || fail 'installation/config_principal.yaml absent : le créer depuis config_principal.example.yaml puis « chmod 600 ».'
  [[ -O "$CONFIG" ]] || fail 'installation/config_principal.yaml doit appartenir au compte courant.'
  local mode
  mode="$(stat -c %a "$CONFIG")"
  [[ "$mode" == 600 || "$mode" == 400 ]] || fail "installation/config_principal.yaml a les permissions $mode : lancer « chmod 600 $CONFIG »."
}
require_venv() {
  [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c 'import yaml, sqlalchemy' 2>/dev/null \
    || fail 'Environnement Python absent ou incomplet : lancer la phase dependencies.'
}
# Valide le YAML (database : connexion ; full : tout, y compris le rendu Nginx/systemd).
# Exporte PG_LOCAL=1 si PostgreSQL est sur cette machine. Retourne 1 si le YAML est invalide.
check_config() {
  local output key value
  output="$("$VENV/bin/python" "$SCRIPT_DIR/lib/check.py" "$1")" || return 1
  while IFS='=' read -r key value; do
    case "$key" in PG_LOCAL|PG_PORT) printf -v "$key" '%s' "$value"; export "${key?}" ;; esac
  done <<<"$output"
}
require_config() {
  check_config "$1" || fail 'corriger installation/config_principal.yaml (message ci-dessus).'
}

# --- Node ------------------------------------------------------------------
node_compatible() {
  command -v node >/dev/null && command -v npm >/dev/null && node -e 'const [a,b,c] = process.versions.node.split(".").map(Number); process.exit((a === 22 && (b > 22 || b === 22 && c >= 3)) || (a === 24 && b >= 15) || a >= 26 ? 0 : 1)'
}
load_nvm() {
  [[ -s "$NVM_DIR/nvm.sh" ]] || return 1
  export NVM_DIR
  local status
  set +eu; trap - ERR
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  status=$?
  # Un Node système incompatible peut masquer celui de nvm : sélectionner la version par défaut de nvm.
  nvm use default >/dev/null 2>&1
  set -eu; trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR
  return $status
}
# Trouve un Node compatible (PATH puis nvm) sans rien installer ; exporte ANIMMALLE_NODE.
resolve_node() {
  node_compatible || { load_nvm || true; }
  node_compatible || return 1
  ANIMMALLE_NODE="$(command -v node)"
  export ANIMMALLE_NODE
}
ensure_node() {
  resolve_node && return 0
  if ! [[ -s "$NVM_DIR/nvm.sh" ]]; then
    command -v curl >/dev/null || fail 'curl est requis pour installer nvm (lancer la phase dependencies).'
    say "Installation de nvm $NVM_VERSION dans $NVM_DIR"
    local installer
    installer="$(mktemp)"
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" -o "$installer" \
      || fail 'Téléchargement de nvm impossible (accès à raw.githubusercontent.com requis, proxy HTTP éventuel via https_proxy).'
    PROFILE=/dev/null bash "$installer"
    rm -f "$installer"
  fi
  load_nvm || fail 'nvm installé mais introuvable.'
  say "Installation de Node $NODE_MAJOR (LTS) via nvm"
  local status
  set +eu; trap - ERR
  nvm install "$NODE_MAJOR" && nvm alias default "$NODE_MAJOR" >/dev/null && nvm use "$NODE_MAJOR" >/dev/null
  status=$?
  set -eu; trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR
  (( status == 0 )) || fail 'Échec de l’installation de Node via nvm.'
  resolve_node || fail "Node $NODE_MAJOR installé mais incompatible avec Nuxt (>= 24.15 requis)."
}

# --- Contrôles en lecture seule -------------------------------------------
port_in_use() {
  command -v ss >/dev/null && [[ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]]
}
phase_check() {
  # Rapporte tous les points d'un coup. Erreurs (YAML) : code 1. Avertissements : corrigés par dependencies/node.
  local errors=0 warnings=0 package
  check_os
  say 'Système pris en charge.'
  for package in "${SYSTEM_PACKAGES[@]}"; do
    package_installed "$package" || { warn "paquet $package absent (phase dependencies)."; warnings=1; }
  done
  check_config_file
  require_venv
  if check_config database; then
    if [[ "$PG_LOCAL" == 1 ]]; then
      if ! postgres_server_installed; then
        warn 'serveur PostgreSQL local absent (phase dependencies).'; warnings=1
      elif ! postgres_cluster_online "$PG_PORT"; then
        warn "aucun cluster PostgreSQL en ligne sur le port $PG_PORT (pg_lsclusters)."; errors=1
      else
        say "PostgreSQL local en ligne sur le port $PG_PORT."
      fi
    else
      say 'PostgreSQL distant : il doit accepter la connexion du YAML ; la base est créée si le rôle a CREATEDB.'
    fi
  else
    errors=1
  fi
  if (( errors == 0 )) && check_config full; then
    say 'YAML valide (base, backend, OIDC/LDAP, Nginx, Gunicorn, Nuxt).'
  else
    warn 'le déploiement (phases prepare/deploy/all) sera refusé tant que ce point n’est pas corrigé.'
    errors=1
  fi
  if resolve_node; then
    say "Node compatible : $ANIMMALLE_NODE ($(node --version))."
  else
    warn 'Node compatible absent (phase node).'; warnings=1
  fi
  # Ports internes déjà pris par un autre programme que nos services.
  local ports port service
  ports="$("$VENV/bin/python" - "$CONFIG" <<'PY' 2>/dev/null || true
import sys, yaml
c = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
print(str(c['gunicorn']['bind']).rsplit(':', 1)[-1], 'animmalle-backend')
print(c['nuxt']['port'], 'animmalle-frontend')
PY
)"
  while read -r port service; do
    [[ -n "$port" ]] || continue
    if port_in_use "$port" && ! systemctl is-active --quiet "$service" 2>/dev/null; then
      warn "le port $port est déjà utilisé par un autre programme que $service."; errors=1
    fi
  done <<<"$ports"
  if (( errors )); then
    fail 'contrôle en échec : corriger les erreurs ci-dessus puis relancer « install.sh check ».'
  elif (( warnings )); then
    say 'Contrôle terminé : YAML valide ; prérequis manquants installés par les phases dependencies et node.'
  else
    say 'Contrôle terminé : aucun problème détecté.'
  fi
}

# --- Phases ----------------------------------------------------------------
phase_dependencies() {
  check_os
  authenticate_sudo
  ensure_packages "${SYSTEM_PACKAGES[@]}"
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail 'Python >= 3.11 requis.'
  if ! { [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c '' 2>/dev/null; }; then
    say "Création de l'environnement Python $VENV"
    python3 -m venv --clear "$VENV"
  fi
  "$VENV/bin/python" -m pip install --disable-pip-version-check -q -r "$PROJECT_DIR/backend/requirements.txt"
  "$VENV/bin/python" -m pip check
  if [[ -f "$CONFIG" ]]; then
    check_config_file
    require_config database
    [[ "$PG_LOCAL" != 1 ]] || ensure_postgres
  else
    warn 'config_principal.yaml absent : PostgreSQL local non installé (relancer dependencies après sa création).'
  fi
  say 'Dépendances système et backend prêtes.'
}
phase_node() {
  ensure_node
  say "Node $(node --version) et npm $(npm --version) disponibles : $ANIMMALLE_NODE"
}
phase_frontend() {
  ensure_node
  [[ -f "$PROJECT_DIR/frontend/package-lock.json" ]] || fail 'frontend/package-lock.json absent.'
  cd "$PROJECT_DIR/frontend"
  npm ci --no-audit --no-fund
  npm run test
  npm run build
  [[ -f .output/server/index.mjs ]] || fail 'Build Nuxt terminé sans .output/server/index.mjs.'
  say 'Frontend construit.'
}
phase_schema() {
  require_venv
  check_config_file
  require_config database
  # sudo n'est nécessaire que pour administrer un PostgreSQL local.
  [[ "$PG_LOCAL" != 1 ]] || authenticate_sudo
  "$VENV/bin/python" "$SCRIPT_DIR/lib/database.py" schema
}
phase_restore() {
  require_venv
  check_config_file
  require_config database
  "$VENV/bin/python" "$SCRIPT_DIR/lib/database.py" restore
}
phase_prepare() {
  require_venv
  check_config_file
  resolve_node || fail 'Node compatible introuvable : lancer la phase node.'
  "$VENV/bin/python" "$SCRIPT_DIR/lib/deploy.py" prepare
}
phase_deploy() {
  require_venv
  check_config_file
  resolve_node || fail 'Node compatible introuvable : lancer la phase node.'
  [[ -f "$PROJECT_DIR/frontend/.output/server/index.mjs" ]] || fail 'Frontend non construit : lancer la phase frontend.'
  require_config full
  authenticate_sudo
  ensure_packages nginx curl
  "$VENV/bin/python" "$SCRIPT_DIR/lib/deploy.py" apply
}
phase_all() {
  check_os
  check_config_file
  authenticate_sudo
  start_sudo_keepalive
  local phase
  for phase in dependencies check node frontend schema restore deploy; do
    "$SCRIPT_DIR/install.sh" "$phase" || fail "phase $phase en échec : corriger puis relancer « install.sh $phase » et les suivantes, ou « install.sh all » (relance sans risque)."
  done
  say 'Installation complète terminée.'
}

# --- Point d'entrée ---------------------------------------------------------
[[ $# -eq 1 ]] || { usage; exit 2; }
case "$PHASE" in
  --help|-h) usage; exit 0 ;;
  check|dependencies|node|frontend|prepare|schema|restore|deploy|all) ;;
  *) usage; exit 2 ;;
esac
[[ $EUID -ne 0 ]] || fail 'Lancer sous le compte applicatif, sans sudo.'
start_log
"phase_$PHASE"
