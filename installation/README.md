# Installation — étapes 2 à 6

État courant : backend et frontend implémentés. Voir la section « Déploiement —
étape 6 » en fin de document. Les sections précédentes conservent le journal
des opérations réellement effectuées aux étapes antérieures.

`install.sh` est créé mais **n'a pas été exécuté**. Les phases sont explicites,
sans action par défaut. Les chemins sont résolus depuis le script, quel que soit
le répertoire courant. Ne pas lancer le script lui-même avec `sudo`.

Commandes préparées pour les prochaines étapes, à lancer uniquement après leur
autorisation :

```sh
./installation/install.sh dependencies
./installation/install.sh schema
./installation/install.sh restore
```

La phase `dependencies` prend en charge Debian 12/13 et Ubuntu 24.04 avec apt.
Elle utilise `sudo` pour installer Python et son module venv ; sudo gère lui-même
le mot de passe. Le venv `.venv/` appartient au compte applicatif. Pip réconcilie
les versions avec `backend/requirements.txt`, puis contrôle leur compatibilité.
Aucune nouvelle bibliothèque n'est introduite à cette étape. Les versions sont
celles documentées à l'étape 1 ; aucune installation n'a été vérifiée ici.

Avant `schema`, PostgreSQL et son client `psql` doivent être installés.
La phase appelle `sudo -v` : sudo demande le mot de passe dans le terminal.
Pour une connexion locale (`localhost`, `127.0.0.1` ou `::1`) sur 5432,
elle démarre le service via `sudo systemctl start postgresql`, puis utilise
`sudo -u postgres psql` avec le socket `/var/run/postgresql` et le port 5432.
Le compte système postgres et son accès administratif local doivent fonctionner.
Le rôle du YAML (`animmalle` par défaut) est créé avec LOGIN et le mot de passe
configuré seulement s'il manque. La base absente est créée avec ce rôle comme
propriétaire ; aucun privilège superutilisateur ou CREATEDB ne lui est accordé.
Les rôles et bases existants sont conservés, sans changement de mot de passe,
de propriétaire ou de droits. Un mot de passe existant différent du YAML fera
donc échouer la connexion et nécessitera une correction explicite.
Le secret SQL transite par l'entrée standard de psql ; sa sortie est capturée
et n'est jamais affichée en cas d'erreur. Ne pas activer la journalisation SQL
complète pendant le provisionnement. Le mot de passe sudo reste géré par sudo.

Pour un serveur distant ou un autre port, le rôle doit être préprovisionné avec
LOGIN, les droits de propriétaire et, si la base manque, CREATEDB. La base de
maintenance postgres doit alors être accessible avec ces identifiants. Aucun
provisionnement via sudo local n'est tenté sur ce serveur.
Les migrations s'exécutent sous le compte applicatif avec les identifiants YAML.

Copier manuellement `config_principal.example.yaml` en `config_principal.yaml`,
renseigner la connexion et protéger le fichier : propriétaire égal au compte
applicatif, permissions 600 (ou 400). Le script ne remplace pas la configuration.
La configuration réelle reste ignorée par Git et ne doit jamais être publiée.

La phase `schema` crée seulement la base absente, refuse les bases système,
refuse des tables publiques préexistantes sans `alembic_version`, puis exécute
`alembic upgrade head`. Les identifiants sont lus directement du YAML par le
chargeur backend. Aucun secret n'est placé dans les arguments de commande.
Les messages des pilotes et la sortie des migrations sont masqués en cas
d'échec pour éviter leur divulgation. Le script ne supprime aucune base et ne
restaure aucune donnée. La création de base et les migrations sont deux opérations
séparées : en cas d'échec des migrations, la base créée peut subsister ; corriger
la cause avant de relancer. Éviter les exécutions concurrentes.

La phase `restore` laisse la base intacte si le dump est absent. Elle convertit
les données du format MariaDB étudié, sans exécuter le SQL source. Voir la
validation de l'étape 4 ci-dessous ; aucun `pg_restore` n'est utilisé.

À l’étape 2, `deploy` et `all` s’arrêtaient avant toute modification. Leur implémentation attendait alors
les étapes 5/6 : manifestes et verrouillage frontend, point d'entrée Gunicorn,
mode Nuxt, clés YAML de production et topologie de proxy. Le déploiement devra
installer les dépendances frontend compatibles, générer Nginx pour les adresses
frontend/API distinctes, limiter la confiance dans les en-têtes transmis,
sauvegarder la configuration existante et valider Nginx avant rechargement.
Aucune configuration Nginx provisoire n'est installée par ce script.

## Vérifications réellement effectuées

- `bash -n installation/install.sh` : syntaxe valide, sans exécution du script.
- Analyse AST de `installation/lib/database.py` : syntaxe valide, sans import ni
  connexion à PostgreSQL.
- Les quatre tests backend hors ligne passent dans le venv temporaire de l'étape 1.
- `git diff --check` : aucune erreur d'espacement.

Aucun sudo, installation, serveur, création de base ou import n'a été exécuté.
Les distributions annoncées, les droits réels, les migrations PostgreSQL et les
relances sur une base existante restent à vérifier à l'étape 3. Le script n'est
pas encore un installateur complet de production.

## Tentative de l'étape 3 — 5 novembre 2026

L'étape 3 est autorisée. Le venv du projet a été créé et les dépendances backend
installées ; `pip check` et les quatre tests backend hors ligne réussissent.
La phase `schema` a été lancée mais s'arrête avant connexion : le YAML réel est
absent. PostgreSQL 17/main est installé mais arrêté ; sudo exige une saisie
interactive indisponible pour l'agent. Aucune base, donnée ou configuration
système n'a été modifiée. Fournir le YAML protégé et un serveur PostgreSQL
joignable avant de reprendre cette phase. La validation PostgreSQL réelle et
la vérification des relances restent à faire ; aucun dump n'a été restauré.

## Authentification sudo interactive

Depuis un terminal, lancer sans préfixe sudo :

```sh
./installation/install.sh schema
```

Saisir le mot de passe lorsque sudo le demande. Si l'authentification échoue,
le script s'arrête avant les opérations sur la base. Un ticket sudo encore
valide peut éviter une nouvelle demande de mot de passe. Le YAML protégé et
le serveur PostgreSQL restent nécessaires ; le rôle local absent est créé automatiquement.

Validation de cette modification : syntaxe Bash valide, trois tests de parcours
avec sudo/Python simulés et quatre tests backend hors ligne réussis. Commande
des nouveaux tests : `.venv/bin/python -m unittest discover -s installation/tests -v`.
Aucun vrai sudo, démarrage de service ou accès à la base dans ces tests.

Validation du provisionnement local : deux tests supplémentaires vérifient les
commandes envoyées, la protection du secret et le traitement des erreurs avec
sudo/psql simulés. Les cinq tests installation et quatre tests backend passent.
Aucun provisionnement réel n'a été exécuté lors de cette modification.

## Validation réelle du schéma — après exécution utilisateur

Vérification PostgreSQL en transaction de lecture seule : connexion réussie,
révision `0001_initial`, neuf tables métier attendues présentes et vides,
aucune table supplémentaire hors version Alembic. La comparaison Alembic avec
les modèles, types et valeurs par défaut activés, ne relève aucune différence.
L'étape 3 est validée pour la création du schéma ; la relance réelle de
l'installateur n'a pas été testée par l'agent. Aucun dump n'a été restauré.


## Étape 4 — reprise effectuée le 5 novembre 2026

`./installation/install.sh restore` importe maintenant le dump MariaDB étudié
via `lib/restore.py`, sans dépendance supplémentaire ni exécution de ses ordres
CREATE/DROP/USE/SET. Le parseur accepte les INSERT VALUES de cet export, leurs
échappements MariaDB et les apostrophes doublées ; ce n'est pas un convertisseur
SQL universel. Un format différent doit être étudié avant utilisation.

Avant connexion : contrôle des neuf tables, colonnes, types, dates, longueurs,
NULL, identifiants, unicités et références. Sur PostgreSQL : verrouillage exclusif
des tables métier (attente limitée à dix secondes), contrôle que la base est à la
dernière révision des migrations (lue dans `backend/migrations`, plus une valeur
fixe), de l'inventaire et des différences Alembic avec les modèles.
Si une table contient des données, aucun import n'est effectué. Exécuter cette
phase hors utilisation applicative : les verrous bloquent aussi les lectures.

L'import conserve toutes les valeurs et compare chaque ligne relue avec la
source avant validation. Les huit séquences utilisent ALTER SEQUENCE RESTART,
transactionnel, au maximum de l'id suivant et de l'AUTO_INCREMENT exporté
(notamment 94 pour le thésaurus). Les contraintes restent actives. Toute erreur
annule données et recalage des séquences ; aucune table n'est supprimée.

Vérifications réellement exécutées :

- Neuf tests installation, dont quatre tests de conversion : échappements,
  Unicode, chaînes vides/NULL, commentaires, entrées incorrectes, doublons et
  références orphelines. Quatre tests backend réussis.
- Test PostgreSQL réel : import complet dans une transaction, comparaison de
  toutes les lignes, vérification des huit prochains identifiants, refus d'un
  second import, puis rollback. Les neuf tables sont redevenues vides et les
  séquences ont retrouvé leur état initial.
- Import définitif avec `./installation/install.sh restore` : 3 894 lignes
  enregistrées et vérifiées dans les neuf tables. Relance réelle réussie :
  « Base déjà alimentée : aucune restauration effectuée. »
- Syntaxe Bash et `git diff --check` valides. Les accès réels PostgreSQL ont été
  exécutés hors sandbox, après échec de connexion en sandbox.

Répartition : 105 animations, 19 commentaires, 452 matériels pédagogiques,
560 séquences, 85 entrées du thésaurus et 2 673 associations.
Le dump, le YAML réel et les données restent hors Git. Aucun sudo, changement
Nginx, API ou frontend n'a été nécessaire à cette étape. Les médias référencés
ne sont pas des fichiers contenus dans le dump et ne sont pas copiés ici.
Les étapes 5 et 6 attendent une nouvelle demande explicite.

## Étape 5 : backend API

L’API Flask, Marshmallow et le point d’entrée Gunicorn sont implémentés ; voir
[backend/README.md](../backend/README.md) pour les contrats, la configuration et
les validations. Python 3.11 minimum est désormais requis par les versions stables
retenues. La phase `dependencies` installe également les dépendances API.

Le YAML exemple est enrichi (backend, public, auth, proxy, gunicorn, paths et mail).
Compléter les sections du YAML réel existant avant exploitation, en préservant
ses identifiants PostgreSQL ; aucun secret réel n’a été modifié par l’étape 5.
Les médias et pages, importés ou nouveaux, utilisent les mêmes dossiers. Les
ressources ont été déplacées dans `backend/uploads`, `backend/pages` et
`backend/pictograms`, conformément aux chemins YAML réel et exemple. Ces dossiers
locaux sont exclus de Git et doivent être inclus dans les sauvegardes.

À la fin de l’étape 5, `deploy` et `all` restaient bloqués jusqu’aux choix
frontend de l’étape 6. Aucun serveur, sudo, changement Nginx, restauration ou migration des
tables métier n’a été lancé à l’étape 5. Les tests PostgreSQL créent uniquement des
schémas temporaires annulés, avec contrôle des données publiques avant/après.


## Déploiement — étape 6

Le frontend est une application Nuxt CSR avec serveur Node Nitro. Il lit le YAML
central au démarrage et n’expose que l’adresse publique API. Voir
[le frontend](../frontend/README.md) pour les versions et les vérifications.
L’installateur comporte maintenant les phases suivantes, sans phase par défaut :

| Phase | Opération |
| --- | --- |
| `dependencies` | Python/venv, dépendances backend et PostgreSQL local si `postgresql.host` est local (apt/sudo) |
| `node` | Installe nvm (`NVM_VERSION`, défaut v0.40.3) dans `~/.nvm` puis Node 24 LTS (`NODE_MAJOR`) s’ils sont absents ou incompatibles ; sans sudo |
| `frontend` | Appelle la logique de la phase `node` si besoin, puis `npm ci`, tests unitaires et build Nuxt |
| `schema` | Provisionnement non destructeur et Alembic |
| `restore` | Import contrôlé seulement sur base vide |
| `prepare` | Rendu Nginx/systemd dans `installation/generated`, sans sudo |
| `deploy` | Applique les fichiers préparés puis redémarre les services |
| `all` | Enchaîne dependencies, node, frontend, schema, restore, deploy |

Les phases frontend/prepare/deploy/all **n’ont pas été exécutées via le script**
à cette étape. npm install, tests et build ont été exécutés directement ; la
préparation du déploiement est testée avec des configurations synthétiques.
Aucun sudo, rechargement Nginx, démarrage de service applicatif permanent,
migration ou restauration exécuté à l’étape 6.

Compléter le YAML réel existant depuis l’exemple, en conservant les identifiants
PostgreSQL. `nuxt.port` définit le port Node local ; `gunicorn.bind` doit être
`127.0.0.1:PORT`, différent du port Node. Node doit être dans le PATH au moment de
la préparation : le chemin absolu est incorporé dans l’unité systemd. Le compte
applicatif courant devient le compte de service ; il doit lire le YAML protégé,
écrire dans les dossiers backend configurés et traverser le chemin du dépôt.
Les chemins de déploiement doivent être sans espace ni caractères spéciaux.

Nginx, systemd et PostgreSQL sont des prérequis système. Node est installé via nvm
sous le compte applicatif si absent ou incompatible (le script nvm officiel est téléchargé
sur GitHub, version épinglée). Le chemin absolu de Node sous `~/.nvm` est incorporé dans
l’unité systemd. L’installateur ne crée aucun certificat. Seule la phase
`dependencies` installe Python via apt. Les deux noms DNS publics distincts doivent
pointer vers l’infrastructure de déploiement. Le générateur prend en charge des
origines sans port explicite, sous le même schéma HTTP ou HTTPS.

Deux topologies :

- Relais TLS amont local : `nginx.upstream_tls: true`, Nginx écoute exclusivement
  sur `127.0.0.1:8080` et le relais de la même machine route les deux noms publics
  vers Nginx en conservant Host. Nginx impose le schéma des origines du YAML.
  Une terminaison amont sur une autre machine demande une adaptation explicite
  des interfaces et du filtrage réseau ; elle n’est pas générée automatiquement.
- TLS terminé par Nginx : `upstream_tls: false`, `listen: 0.0.0.0:443`, chemins
  `certificate` et `certificate_key` existants et lisibles par Nginx. Les deux
  domaines doivent être couverts par le certificat. Pour un environnement HTTP
  isolé, utiliser des origines HTTP et un port Nginx adapté.

Le frontend est proxifié vers Nuxt, exclusivement `/api/` vers Gunicorn sur le
nom API ; les autres chemins du nom API répondent 404. Aucun dossier du dépôt,
upload, YAML ou dump n’est servi directement par Nginx. Les en-têtes Host,
X-Forwarded-Host/Proto/Port/For sont écrasés par Nginx. Configurer la section
backend `proxy` à **un** relais de confiance pour ces en-têtes seulement si
Gunicorn est effectivement isolé sur la boucle locale. X-Forwarded-For contient
l’adresse vue par Nginx : avec un relais amont, l’IP d’origine n’est pas conservée.

`prepare` valide les paramètres, puis produit des fichiers sans secrets.
`deploy` sauvegarde le fichier Nginx existant en `.previous`, installe le nouveau,
exécute `nginx -t` et restaure le précédent si cette validation échoue. Les unités
systemd précédentes sont aussi sauvegardées. La validation globale Nginx peut
échouer à cause d’un autre site : consulter les journaux et corriger avant relance.
Les sorties des commandes système sont masquées en cas d’erreur pour éviter une
exposition accidentelle ; les journaux restent consultables depuis le terminal.

Après validation, deploy installe/active `animmalle-backend.service` et
`animmalle-frontend.service`, les redémarre, puis recharge Nginx. Il ne restaure
pas automatiquement les services si un démarrage échoue après cette validation :
consulter `journalctl -u animmalle-backend -u animmalle-frontend` et les sauvegardes.
La configuration réelle reste à compléter et le déploiement complet n’a pas été
validé sur la machine. Les 12 tests installation passent, dont trois sur le rendu
Nginx/systemd (routage, secrets exclus, contraintes TLS et entrées invalides).
