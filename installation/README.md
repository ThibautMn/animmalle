# Installation — étape 2

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

Avant `schema`, PostgreSQL doit être installé, joignable et doté d'un rôle
applicatif avec LOGIN. Ce rôle doit posséder la base existante et les droits DDL,
ou le droit CREATEDB si la base manque. La base de maintenance `postgres` doit
être accessible avec les mêmes identifiants. Le script ne crée pas de rôle et
n'installe ni ne démarre PostgreSQL. Ces prérequis devront être contrôlés à
l'étape 3 avant exécution. Le droit CREATEDB pourra être retiré après création.

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

La phase `restore` laisse la base intacte si le dump est absent. Si le dump est
présent, elle s'arrête sans l'importer : le dump connu est MariaDB, incompatible
avec une restauration PostgreSQL directe. L'étape 4 devra implémenter la
conversion, la vérification du schéma, le contrôle des données métier existantes,
une importation transactionnelle conservant les identifiants et le recalage des
séquences. Aucun `pg_restore` aveugle ni exécution du SQL MariaDB n'est prévu.

`deploy` et `all` s'arrêtent avant toute modification. Leur implémentation attend
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
