# Point de reprise — 5 novembre 2026

L'étape 1 est terminée : modèles SQLAlchemy, migration initiale Alembic et étude
des modèles et du dump MariaDB historiques. Voir `backend/README.md` et
`backend/docs/reprise_historique.md`.

L'étape 2 est terminée dans son périmètre : `installation/install.sh`, auxiliaire
`installation/lib/database.py` et documentation `installation/README.md`.
Le script n'a pas été exécuté. Il distingue dépendances backend, création du
schéma et restauration. La restauration d'un dump présent et le déploiement
complet sont bloqués explicitement dans l'attente des étapes 4 à 6.

Vérifications : syntaxe Bash, analyse AST Python, quatre tests backend hors ligne
et `git diff --check`. Aucun serveur, sudo, installation, création de base ou
restauration n'a été lancé. Les tests utilisent le venv temporaire existant
`/tmp/animmalle-models-venv`.

La prochaine étape est l'étape 3 : utiliser le script pour créer la base
PostgreSQL et appliquer les migrations. Attendre la demande explicite avant de
commencer. Contrôler d'abord le YAML local, les droits du rôle PostgreSQL et la
présence du serveur ; voir les prérequis dans `installation/README.md`.

Préserver les modifications locales et les suppressions/déplacements historiques.
Ne pas modifier `ancien_animalle/`. Aucun commit n'a été créé.

## Étape 3 autorisée — tentative du 5 novembre 2026

L'utilisateur a demandé de poursuivre : l'étape 3 est désormais autorisée mais
reste inachevée. Le venv du projet `.venv/` a été créé, les dépendances de
`backend/requirements.txt` installées, `pip check` et les quatre tests backend
hors ligne réussis. Le téléchargement a nécessité une exécution hors sandbox
après un échec de résolution réseau dans la sandbox.

Constats : `installation/config_principal.yaml` absent ; le cluster PostgreSQL
17/main local est arrêté (`pg_lsclusters`). `sudo -n pg_lsclusters`, tenté avec
approbation d'escalade, échoue car un mot de passe interactif est nécessaire.
`./installation/install.sh schema` a été réellement exécuté : arrêt en erreur
avant toute connexion faute de YAML. Aucune base ni donnée n'a été modifiée.

Attente : l'utilisateur doit rendre PostgreSQL disponible et renseigner le YAML
local protégé (permissions 600), avec un rôle propriétaire de la base ou doté de
CREATEDB si elle manque. Ne pas transmettre le mot de passe dans la conversation.
Ensuite reprendre directement l'étape 3, déjà autorisée : exécuter la phase
schema, vérifier la révision, la conformité du schéma aux modèles, l'absence de
données métier et une relance sans modification. Ne pas démarrer l'étape 4.
Les modifications préexistantes de `.gitignore` sont conservées.

## Ajustement demandé : sudo interactif

La phase `schema` appelle désormais `sudo -v` et permet la saisie du mot de
passe par l'utilisateur dans son terminal. Après validation du YAML, pour
une connexion locale sur 5432, l'auxiliaire démarre PostgreSQL via
`sudo systemctl start postgresql`. Les migrations restent non privilégiées.
Commande utilisateur : `./installation/install.sh schema` (sans sudo devant).
Le YAML et le rôle PostgreSQL doivent toujours être renseignés/provisionnés.
Trois tests simulant les commandes externes et les quatre tests backend passent ;
syntaxe Bash valide. La base et le service réels n'ont pas été modifiés.
L'étape 3 reste à terminer après exécution interactive et vérification du schéma.

## Création automatique du rôle local

À la demande de l'utilisateur, la phase schema crée désormais le rôle du YAML
(animmalle par défaut) et sa base via sudo -u postgres psql pour localhost:5432.
Le rôle obtient LOGIN et le mot de passe YAML ; la base lui appartient.
Rôles et bases existants restent inchangés. Aucun droit CREATEDB n'est nécessaire
pour ce nouveau rôle local. Les serveurs distants restent préprovisionnés.
Cinq tests installation avec commandes simulées et quatre tests backend passent,
syntaxe Bash valide. Aucun vrai sudo ou accès PostgreSQL n'a été exécuté.
Reprendre via ./installation/install.sh schema depuis un terminal utilisateur,
puis vérifier le schéma réel. L'étape 4 reste en attente d'autorisation.

## Étape 3 : vérification PostgreSQL après exécution utilisateur

Après confirmation de l'utilisateur, vérification réelle en lecture seule hors
sandbox (connexion refusée depuis la sandbox) : connexion réussie, révision
Alembic `0001_initial`, neuf tables métier présentes, aucune table supplémentaire
hors alembic_version, aucune donnée métier et aucune différence entre le schéma
et les modèles (types et valeurs par défaut compris).
La création du schéma de l'étape 3 est validée. Le script n'a pas été relancé
par l'agent ; l'idempotence sur PostgreSQL réel reste à vérifier séparément.
Aucun dump n'a été restauré. Attendre la demande explicite de l'étape 4 avant
la conversion et l'alimentation depuis le dump MariaDB.
