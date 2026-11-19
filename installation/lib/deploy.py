"""Prépare les unités et le proxy ; applique uniquement sur demande explicite."""
import getpass
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
NGINX = Path('/usr/sbin/nginx')
NGINX_SITE = Path('/etc/nginx/conf.d/animmalle.conf')
SERVICES = ('animmalle-backend', 'animmalle-frontend')


def origins(config):
    front = urlsplit(config['public']['frontend_url'])
    api = urlsplit(config['public']['api_url'])
    for url in (front, api):
        if url.scheme not in ('http', 'https') or not url.hostname or not re.fullmatch(r'[a-zA-Z0-9.-]+', url.netloc) or url.path not in ('', '/') or url.query or url.fragment:
            raise ValueError('public.frontend_url et public.api_url : origines http(s)://nom sans port, chemin ni paramètre.')
    if front.scheme != api.scheme:
        raise ValueError('public.frontend_url et public.api_url doivent utiliser le même schéma HTTP(S).')
    return front, api


def nginx_listen(config):
    cfg = config['nginx']
    listen = cfg.get('listen', '127.0.0.1:8080')
    if not isinstance(listen, str) or not re.fullmatch(r'(?:127\.0\.0\.1|0\.0\.0\.0):[0-9]{1,5}', listen) or not 1 <= int(listen.rsplit(':', 1)[1]) <= 65535:
        raise ValueError('nginx.listen invalide : 127.0.0.1:PORT ou 0.0.0.0:PORT.')
    return listen


def render(config, root=ROOT, node=None, user=None):
    node = node or shutil.which('node')
    user = user or getpass.getuser()
    if not node:
        raise ValueError('Node est requis (phase node).')
    # Ces chemins sont incorporés dans des directives systemd, sans shell.
    for value in (str(root), node, user):
        if not re.fullmatch(r'[a-zA-Z0-9_./@-]+', value):
            raise ValueError('Chemin du dépôt, de Node ou compte de service : caractères non pris en charge (espaces, accents…).')
    front, api = origins(config)
    # Même nom DNS pour le frontend et l'API : un seul bloc serveur, /api/ vers Gunicorn, le reste vers Nuxt.
    same_host = front.hostname == api.hostname
    cfg = config['nginx']
    upstream_tls = cfg.get('upstream_tls', False)
    if type(upstream_tls) is not bool:
        raise ValueError('nginx.upstream_tls doit valoir true ou false.')
    listen = nginx_listen(config)
    allow = cfg.get('upstream_allow', [])
    if upstream_tls and not listen.startswith('127.0.0.1:'):
        # Proxy TLS amont sur une autre machine : adresses autorisées obligatoires, tout le reste est refusé.
        if not isinstance(allow, list) or not allow:
            raise ValueError('Un relais TLS amont distant exige nginx.upstream_allow (adresses ou réseaux autorisés).')
        try:
            allow = [str(ipaddress.ip_network(str(a), strict=False)) for a in allow]
        except ValueError:
            raise ValueError('nginx.upstream_allow invalide.') from None
        # La boucle locale reste autorisée pour la vérification post-déploiement.
        allow = ['127.0.0.1'] + [a for a in allow if a != '127.0.0.1/32']
    else:
        allow = []
    access = ''.join(f'\n    allow {a};' for a in allow) + ('\n    deny all;' if allow else '')
    nuxt = config['nuxt']
    port = nuxt.get('port')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('nuxt.port doit être compris entre 1024 et 65535.')
    bind = config['gunicorn']['bind']
    if not isinstance(bind, str) or not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', bind):
        raise ValueError('gunicorn.bind doit être 127.0.0.1:PORT pour ce déploiement.')
    if int(bind.split(':')[1]) == port:
        raise ValueError('Gunicorn et Nuxt doivent utiliser des ports distincts.')
    if int(listen.rsplit(':', 1)[1]) in (port, int(bind.split(':')[1])):
        raise ValueError('nginx.listen doit utiliser un port distinct de Gunicorn et de Nuxt.')
    blocks = []
    nuxt_target = f'127.0.0.1:{port}'
    if same_host:
        servers = [(front, [('/api/', bind), ('/', nuxt_target)])]
    else:
        servers = [(front, [('/', nuxt_target)]), (api, [('/api/', bind), ('/', None)])]
    for url, locations in servers:
        tls = ''
        if url.scheme == 'https' and not upstream_tls:
            for key in ('certificate', 'certificate_key'):
                if not re.fullmatch(r'/[a-zA-Z0-9_./-]+', cfg.get(key) or ''):
                    raise ValueError('nginx.certificate et nginx.certificate_key requis lorsque Nginx termine TLS.')
            tls = f"\n    ssl_certificate {cfg['certificate']};\n    ssl_certificate_key {cfg['certificate_key']};\n    ssl_protocols TLSv1.2 TLSv1.3;"
        listen_line = listen + (' ssl' if tls else '')
        # L'origine publique est validée ; on écrase les en-têtes fournis par le client.
        scheme = url.scheme if upstream_tls else '$scheme'
        parts = []
        for location, target in locations:
            if target is None:  # nom API distinct : seul /api/ est servi
                parts.append(f'    location {location} {{ return 404; }}')
                continue
            parts.append(f'''    location {location} {{
        proxy_pass http://{target};
        proxy_http_version 1.1;
        proxy_set_header Host {url.hostname};
        proxy_set_header X-Forwarded-Host {url.hostname};
        proxy_set_header X-Forwarded-Proto {scheme};
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Port {443 if url.scheme == 'https' else 80};
        proxy_set_header Connection "";
        proxy_read_timeout 90s;
    }}''')
        header = f'''server {{
    listen {listen_line};
    server_name {url.hostname};{tls}{access}
    client_max_body_size {config['backend']['max_upload_mb']}m;
'''
        blocks.append(header + '\n'.join(parts) + '\n}')

    def unit(description, working, command, environment=''):
        return f'''[Unit]
Description={description}
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={root}/{working}
ExecStart={command}
{environment}Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
'''
    return {
        'animmalle.conf': '\n\n'.join(blocks) + '\n',
        'animmalle-backend.service': unit('AnimMalle API', '', f'{root}/.venv/bin/gunicorn -c {root}/backend/gunicorn.conf.py'),
        'animmalle-frontend.service': unit('AnimMalle Nuxt', 'frontend', f'{node} {root}/frontend/.output/server/index.mjs', f'Environment=NITRO_HOST=127.0.0.1\nEnvironment=NITRO_PORT={port}\n'),
    }


def command(*args, show_output=False):
    """Exécute une commande système ; l'étape en échec est nommée (les arguments ne contiennent aucun secret)."""
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        detail = f'\n{result.stdout.strip()}' if show_output and result.stdout.strip() else ''
        raise RuntimeError(f'Échec de « {" ".join(args)} ».{detail}')
    return result.stdout


def http_status(url, resolve=None, insecure=False):
    args = ['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '10']
    if resolve:
        args += ['--resolve', resolve]
    if insecure:
        args.append('-k')
    result = subprocess.run(args + [url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return int(result.stdout) if result.stdout.isdigit() else 0


def wait_for(description, check, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        status = check()
        if status:
            print(f'  OK  {description}')
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f'{description} : aucune réponse correcte après {timeout} s.')
        time.sleep(2)


def verify(config):
    """Vérifie réellement les services et le routage Nginx après déploiement."""
    print('Vérification du déploiement :')
    for service in SERVICES:
        def active(service=service):
            return subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0
        try:
            wait_for(f'service {service} actif', active, timeout=30)
        except RuntimeError:
            raise RuntimeError(f'Le service {service} ne démarre pas : consulter « sudo journalctl -u {service} -n 50 --no-pager ».') from None
    bind = config['gunicorn']['bind']
    port = config['nuxt']['port']
    wait_for(f'API Gunicorn http://{bind}/api/health', lambda: http_status(f'http://{bind}/api/health') == 200)
    wait_for(f'Nuxt http://127.0.0.1:{port}/', lambda: 200 <= http_status(f'http://127.0.0.1:{port}/') < 400)
    front, api = origins(config)
    listen_port = int(nginx_listen(config).rsplit(':', 1)[1])
    direct_tls = front.scheme == 'https' and not config['nginx'].get('upstream_tls', False)
    scheme = 'https' if direct_tls else 'http'
    for url, path in ((api, '/api/health'), (front, '/')):
        target = f'{scheme}://{url.hostname}:{listen_port}{path}'
        resolve = f'{url.hostname}:{listen_port}:127.0.0.1'
        expected = (lambda s: s == 200) if path == '/api/health' else (lambda s: 200 <= s < 400)
        wait_for(f'Nginx {url.hostname}{path} (via 127.0.0.1:{listen_port})',
                 lambda: expected(http_status(target, resolve, insecure=direct_tls)), timeout=20)


def warn_default_site(config):
    listen = nginx_listen(config)
    default = Path('/etc/nginx/sites-enabled/default')
    if listen.startswith('0.0.0.0:') and default.exists():
        print('Attention : le site Nginx « default » est actif. Une requête dont Host ne correspond pas aux noms '
              'publics y aboutira. Le désactiver si besoin : sudo unlink /etc/nginx/sites-enabled/default')


def install_units(target):
    for name in (f'{s}.service' for s in SERVICES):
        destination = Path('/etc/systemd/system') / name
        if destination.exists():
            command('sudo', 'cp', '-p', str(destination), str(destination) + '.previous')
        command('sudo', 'install', '-m', '644', str(target / name), str(destination))


def install_nginx(target):
    """Sauvegarde, remplace et valide ; restaure la configuration précédente si nginx -t échoue."""
    backup = NGINX_SITE.with_name(NGINX_SITE.name + '.previous')
    existed = NGINX_SITE.exists()
    if existed:
        command('sudo', 'cp', '-p', str(NGINX_SITE), str(backup))
    command('sudo', 'install', '-m', '644', str(target / 'animmalle.conf'), str(NGINX_SITE))
    try:
        command('sudo', str(NGINX), '-t', show_output=True)
    except RuntimeError:
        if existed:
            command('sudo', 'cp', '-p', str(backup), str(NGINX_SITE))
        else:
            command('sudo', 'rm', '-f', str(NGINX_SITE))
        raise


def main():
    if sys.argv[1:] not in (['prepare'], ['apply']):
        raise ValueError('Utilisation : deploy.py prepare|apply')
    sys.path.insert(0, str(ROOT / 'backend'))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from animmalle.config import CONFIG_PATH
    from check import load_deploy_config

    config = load_deploy_config(CONFIG_PATH)
    # Le script Bash transmet le Node compatible retenu (nvm ou système) : jamais un Node arbitraire du PATH.
    content = render(config, node=os.environ.get('ANIMMALLE_NODE'))
    target = ROOT / 'installation/generated'
    target.mkdir(mode=0o700, exist_ok=True)
    for name, value in content.items():
        path = target / name
        path.write_text(value)
        path.chmod(0o600)
    if sys.argv[1] == 'prepare':
        print('Configurations préparées dans installation/generated ; aucune modification système.')
        return
    if not (ROOT / 'frontend/.output/server/index.mjs').is_file():
        raise ValueError('Frontend non construit : lancer la phase frontend avant deploy.')
    if not NGINX.is_file():
        raise ValueError('Nginx absent : lancer la phase dependencies.')
    print('Installation de la configuration Nginx et validation (nginx -t).', flush=True)
    install_nginx(target)
    warn_default_site(config)
    print('Installation des unités systemd et redémarrage des services.', flush=True)
    install_units(target)
    command('sudo', 'systemctl', 'daemon-reload')
    command('sudo', 'systemctl', 'enable', *SERVICES)
    command('sudo', 'systemctl', 'restart', *SERVICES)
    command('sudo', 'systemctl', 'enable', 'nginx')
    # reload échoue si Nginx est arrêté : reload-or-restart couvre les deux cas.
    command('sudo', 'systemctl', 'reload-or-restart', 'nginx')
    verify(config)
    print('Services applicatifs redémarrés, Nginx rechargé et routage vérifié.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        # Messages rédigés par ce script ou sortie de nginx -t : aucun secret.
        print(f'Déploiement arrêté : {error}', file=sys.stderr)
        sys.exit(1)
    except KeyError as error:
        print(f'Déploiement arrêté : clé {error} absente du YAML (voir config_principal.example.yaml).', file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f'Déploiement arrêté ({type(error).__module__}.{type(error).__name__}) : vérifier le YAML, les prérequis '
              'et les journaux système. Aucun secret affiché.', file=sys.stderr)
        sys.exit(1)
