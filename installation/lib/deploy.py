"""Prépare les unités et le proxy ; applique uniquement sur demande explicite."""
import getpass
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]


def render(config, root=ROOT, node=None, user=None):
    node = node or shutil.which('node')
    user = user or getpass.getuser()
    if not node:
        raise ValueError('Node est requis.')
    # Ces chemins sont incorporés dans des directives systemd, sans shell.
    for value in (str(root), node, user):
        if not re.fullmatch(r'[a-zA-Z0-9_./@-]+', value):
            raise ValueError('Chemins et compte de service : caractères non pris en charge.')
    front = urlsplit(config['public']['frontend_url'])
    api = urlsplit(config['public']['api_url'])
    for url in (front, api):
        if url.scheme not in ('http', 'https') or not url.hostname or not re.fullmatch(r'[a-zA-Z0-9.-]+', url.netloc) or url.path not in ('', '/') or url.query or url.fragment:
            raise ValueError('Origines publiques sans port explicite requises pour Nginx.')
    # Même nom DNS pour le frontend et l'API : un seul bloc serveur, /api/ vers Gunicorn, le reste vers Nuxt.
    same_host = front.hostname == api.hostname
    if front.scheme != api.scheme:
        raise ValueError('Les deux origines doivent utiliser le même schéma HTTP(S).')
    cfg = config['nginx']
    upstream_tls = cfg.get('upstream_tls', False)
    listen = cfg.get('listen', '127.0.0.1:8080')
    if not re.fullmatch(r'(?:127\.0\.0\.1|0\.0\.0\.0):[0-9]{1,5}', listen) or not 1 <= int(listen.rsplit(':', 1)[1]) <= 65535:
        raise ValueError('nginx.listen invalide.')
    allow = cfg.get('upstream_allow', [])
    if upstream_tls and not listen.startswith('127.0.0.1:'):
        # Proxy TLS amont sur une autre machine : adresses autorisées obligatoires, tout le reste est refusé.
        if not isinstance(allow, list) or not allow:
            raise ValueError('Un relais TLS amont distant exige nginx.upstream_allow (adresses ou réseaux autorisés).')
        try:
            allow = [str(ipaddress.ip_network(str(a), strict=False)) for a in allow]
        except ValueError:
            raise ValueError('nginx.upstream_allow invalide.') from None
    else:
        allow = []
    access = ''.join(f'\n    allow {a};' for a in allow) + ('\n    deny all;' if allow else '')
    nuxt = config['nuxt']
    port = nuxt['port']
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('nuxt.port doit être compris entre 1024 et 65535.')
    bind = config['gunicorn']['bind']
    if not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', bind):
        raise ValueError('Gunicorn doit écouter sur 127.0.0.1 pour ce déploiement.')
    if int(bind.split(':')[1]) == port:
        raise ValueError('Gunicorn et Nuxt doivent utiliser des ports distincts.')
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
                if not re.fullmatch(r'/[a-zA-Z0-9_./-]+', cfg.get(key, '')):
                    raise ValueError('Chemins de certificat TLS Nginx requis.')
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


def command(*args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f'Échec de {args[0]} : vérifier la configuration et les journaux système.')


def main():
    if sys.argv[1:] not in (['prepare'], ['apply']):
        raise ValueError('Utilisation : deploy.py prepare|apply')
    # La validation backend ne divulgue pas les secrets.
    sys.path.insert(0, str(ROOT / 'backend'))
    from animmalle.config import load_settings
    config = load_settings()
    # Conserver les sections propres au déploiement, non normalisées par Flask.
    raw = yaml.safe_load((ROOT / 'installation/config_principal.yaml').read_text())
    config.update({key: raw[key] for key in ('nginx', 'nuxt')})
    content = render(config)
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
        raise ValueError('Construire le frontend avant le déploiement.')
    nginx = Path('/etc/nginx/conf.d/animmalle.conf')
    # Sauvegarde avant remplacement ; restaurée si nginx -t refuse la configuration.
    backup = Path('/etc/nginx/conf.d/animmalle.conf.previous')
    existed = nginx.exists()
    if existed:
        command('sudo', 'cp', '-p', str(nginx), str(backup))
    command('sudo', 'install', '-m', '644', str(target / 'animmalle.conf'), str(nginx))
    try:
        command('sudo', 'nginx', '-t')
    except RuntimeError:
        if existed:
            command('sudo', 'cp', '-p', str(backup), str(nginx))
        else:
            command('sudo', 'unlink', str(nginx))
        raise
    for name in ('animmalle-backend.service', 'animmalle-frontend.service'):
        destination = Path('/etc/systemd/system') / name
        if destination.exists():
            command('sudo', 'cp', '-p', str(destination), str(destination) + '.previous')
        command('sudo', 'install', '-m', '644', str(target / name), str(destination))
    command('sudo', 'systemctl', 'daemon-reload')
    command('sudo', 'systemctl', 'enable', '--now', 'animmalle-backend', 'animmalle-frontend')
    command('sudo', 'systemctl', 'restart', 'animmalle-backend', 'animmalle-frontend')
    command('sudo', 'systemctl', 'reload', 'nginx')
    print('Services applicatifs redémarrés et Nginx rechargé.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Déploiement arrêté : vérifier le YAML, les prérequis et les journaux système. Aucun secret affiché.', file=sys.stderr)
        sys.exit(1)
