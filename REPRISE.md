# Point de reprise avant clear — 5 novembre 2026

## État actuel

Les étapes 1 à 4 sont terminées pour leur périmètre. L'utilisateur a autorisé
l'étape 4 par « on passe à la suite ». Le dump a été converti et importé dans
PostgreSQL : 3 894 lignes, neuf tables, huit séquences recalées. Une relance
réelle conserve les données. Ne pas enchaîner les étapes 5/6 sans demande.

- Étape 1 : modèles SQLAlchemy, migration initiale Alembic et étude de
  l'historique terminés. Références : `backend/README.md` et
  `backend/docs/reprise_historique.md`.
- Étape 2 : `installation/install.sh`, auxiliaire `installation/lib/database.py`,
  documentation et tests créés. Les phases sont distinctes : `dependencies`,
  `schema`, `restore`, `deploy`, `all`. Les phases de déploiement complet sont
  explicitement bloquées en attendant les implémentations backend/frontend.
- Étape 3 : l'utilisateur a exécuté `./installation/install.sh schema` depuis
  son terminal. La création du schéma PostgreSQL a été vérifiée ensuite par
  l'agent en lecture seule : connexion réussie, révision `0001_initial`, neuf
  tables métier présentes et vides, aucune table supplémentaire hors
  `alembic_version`, aucune différence Alembic entre schéma et modèles, types et
  valeurs par défaut compris. À ce stade seulement, aucun dump n’avait encore été restauré.

## Installation et secrets

Le venv du projet `.venv/` existe et contient les dépendances de
`backend/requirements.txt`. Il a été créé à l'étape 3 ; ne pas dépendre du venv
historique temporaire `/tmp/animmalle-models-venv` pour la suite.

Le fichier réel `installation/config_principal.yaml` a été créé depuis le modèle,
avec un mot de passe aléatoire, permissions 600. Il est ignoré par Git. Ne jamais
l'afficher, le versionner ou demander son mot de passe dans la conversation.

`schema` appelle `sudo -v` : l'utilisateur saisit le mot de passe sudo dans son
terminal. Pour localhost/127.0.0.1/::1 sur 5432, l'auxiliaire démarre PostgreSQL
via `sudo systemctl start postgresql`, puis utilise `sudo -u postgres psql` pour
créer le rôle configuré (`animmalle` par défaut) s'il manque, avec LOGIN et le
mot de passe YAML. La base absente est créée avec ce rôle comme propriétaire.
Le rôle n'a pas besoin de CREATEDB pour ce provisionnement local. Les rôles et
bases existants sont conservés sans changement de mot de passe ou de droits.
Les secrets SQL transitent par stdin, jamais dans les arguments ; les sorties
externes contenant potentiellement des secrets sont masquées en cas d'erreur.
Les migrations utilisent ensuite les identifiants applicatifs. Les serveurs
non locaux ou sur un autre port doivent être préprovisionnés.

## Vérifications réellement effectuées

- `bash -n installation/install.sh` : valide.
- `.venv/bin/python -m pip check` : aucune incompatibilité détectée.
- `.venv/bin/python -m unittest discover -s installation/tests -v` : neuf tests
  réussis, dont quatre tests de conversion ; commandes sudo/psql et Python simulées.
- `PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v` :
  quatre tests réussis.
- Comparaison réelle PostgreSQL/modèles : aucune différence ; vérification dans
  une transaction READ ONLY, hors sandbox après échec de connexion en sandbox.
- `git diff --check` : aucune erreur.

La relance réelle de la phase `schema` reste à vérifier ; ne pas la présenter
comme testée. La phase `restore`, elle, a été relancée avec succès après import. Le fonctionnement du provisionnement a été confirmé
par l'exécution utilisateur et l'état final de la base, pas par des logs complets
observés par l'agent.

## Étape 4 terminée et prochaine étape

La phase restore appelle `installation/lib/restore.py` : analyse du dump sans
exécuter son SQL, contrôles des données et du schéma cible, verrouillage des
tables, refus d'import sur base remplie, import et comparaison ligne par ligne,
recalage transactionnel des séquences avec ALTER SEQUENCE RESTART.

Validation : neuf tests installation et quatre tests backend réussis. Test réel
PostgreSQL d'import puis rollback, avec restauration vérifiée des tables vides
et des séquences initiales. Import définitif ensuite réussi ; relance réelle
sans nouvel import. Détails dans `installation/README.md`. Aucun secret affiché.
Les accès PostgreSQL ont nécessité une exécution hors sandbox.

Comptes importés : animation 105, commentaire 19, mat_peda 452, sequence 560,
thesaurus 85, rel_anim_sequence 560, rel_anim_tag 936,
rel_mat_peda_sequence 489, rel_mat_peda_thematique 688.
Les huit prochains identifiants ont été contrôlés pendant le test transactionnel,
notamment 94 pour thesaurus. Les séquences sont recalées au maximum de l'id
suivant et de l'AUTO_INCREMENT du dump.

Le convertisseur est limité au format MariaDB étudié ; il ne doit pas être
présenté comme un importeur SQL universel. Il conserve les valeurs, garde les
contraintes actives et utilise ALTER SEQUENCE RESTART pour permettre aussi
l'annulation du recalage. Aucun nouveau paquet, sudo, changement Nginx, code API
ou frontend n'a été nécessaire. Les fichiers médias référencés ne sont pas
inclus dans le dump et n'ont pas été copiés.

Prochaine étape sur demande explicite : étape 5, terminer le backend. La base
contient maintenant les données historiques : ne plus la considérer vide et ne
pas utiliser de downgrade destructeur. Préserver les données et les médias.

## Espace de travail

Préserver les déplacements/suppressions historiques et ne pas modifier
`ancien_animalle/`, ignoré par Git. Lire les AGENTS.md concernés. Aucun commit
n'a été créé par l'agent. Au moment de ce clear, Git indique :

- Modifiés : `REPRISE.md`, `installation/README.md`, `installation/install.sh`,
  `installation/lib/database.py`.
- Non suivis : `installation/lib/restore.py`,
  `installation/tests/test_restore.py`.

Conserver ces changements. Le YAML réel, le dump et le venv restent ignorés.
La demande « je vais faire un clear. note l'avancement » autorise uniquement
cette sauvegarde documentaire ; elle ne démarre pas l'étape 5.

## Mise à jour — étape 5 (5 novembre 2026)

La demande suivante « ok on passe à la suite » a autorisé l’étape 5.
Le backend Flask est implémenté : fabrique, configuration YAML validée,
sessions LDAP ou comptes locaux hachés, CSRF et CORS, API animations/séquences,
commentaires, médias/outils, thésaurus, pages versionnées, statistiques,
autocomplétion, pictogrammes et exports ZIP/ODT. Notifications SMTP facultatives.
Les modèles ont été déplacés de `animmalle/models/__init__.py` vers
`animmalle/models.py` à la suite de la remarque utilisateur ; les imports restent
`from animmalle.models import ...`. Aucun changement de schéma ni migration nouvelle.

Versions ajoutées : Flask 3.1.3, Marshmallow 4.4.0, Gunicorn 26.2.0, ldap3 2.9.1,
Markdown 3.11.2, nh3 0.3.7, vérifiées sur PyPI et installées dans `.venv`.
Python 3.11 minimum désormais (installation/install.sh adapté).
Documentation complète des routes, droits et différences dans `backend/README.md`.

Vérifications finales :

- 18 tests backend locaux réussis (SQLite temporaire, migration hors ligne).
- 14 tests API réussis sur PostgreSQL dans des schémas isolés, avec application
  de la migration initiale, commits par savepoints et rollback final de chaque
  schéma. Empreinte des neuf tables de `public` identique avant/après et aucun
  schéma temporaire résiduel ; les données historiques sont intactes.
- Neuf tests installation réussis, pip check sans incompatibilité, syntaxe Bash
  et git diff --check valides.
- LDAP et SMTP simulés uniquement. Les deux avertissements pyasn1/ldap3 sont
  documentés. Aucun serveur lancé, aucune commande sudo, aucun changement Nginx.

Le YAML réel reste celui des étapes précédentes : il faut compléter ses sections
applicatives depuis l’exemple, sans remplacer ses identifiants PostgreSQL.
Les adresses publiques, LDAP/CA, SMTP éventuel et médias réels restent à vérifier
en environnement. Les fichiers historiques n’ont pas été modifiés ; les nouvelles
pages et uploads iront dans des dossiers backend ignorés. La présentation ODT est
simplifiée par rapport à py3o (Markdown conservé, pictogrammes via API).

L’étape 6 (frontend) n’est pas commencée ; attendre une nouvelle demande explicite.
Le déploiement complet reste bloqué dans install.sh en attendant les choix Nuxt.
Aucun commit créé. Préserver toutes les modifications locales, notamment celles
préexistantes de ce document. Le YAML, le dump et le venv restent privés et ignorés.

## Dernier point avant clear — 5 novembre 2026

L’utilisateur a demandé la suppression du dossier `backend/animmalle/models/`
devenu inutile après le déplacement vers `backend/animmalle/models.py`.
Vérification : il ne contenait plus que `__pycache__/__init__.cpython-311.pyc`.
Le dossier et ce cache ont été supprimés ; le module `models.py` est conservé.
Aucun nouveau test n’a été lancé pour ce nettoyage de cache.

Au dernier contrôle, `git status --short` indique uniquement `M REPRISE.md`.
Ne pas reprendre comme état actuel les anciennes listes de fichiers modifiés
figurant plus haut. Aucun commit n’a été créé par l’agent.

La demande « je vais faire un clear » autorise la sauvegarde du contexte,
pas le démarrage de l’étape 6. À la reprise, lire ce document et les AGENTS.md.
Le backend est implémenté et validé selon le bilan de l’étape 5 ci-dessus ;
la configuration réelle et les vérifications d’intégration qui y sont listées
restent à effectuer. Attendre la demande explicite pour passer au frontend.


## Étape 6 — implémentation frontend (5 novembre 2026)

Autorisation explicite : « on passe à l’étape 6 ». Le frontend Nuxt/Vue est créé
avec PrimeVue 4.5.5, Pinia et ofetch, sans Axios. Recherche paginée d’animations,
création/édition avec séquences ordonnées et médias, statuts, validation et
réattribution administrateur, commentaires, médiathèque/outils avec import et
remplacement de fichier, téléchargements/aperçus, pages Markdown, thésaurus et
statistiques. Voir frontend/README.md pour les détails et limites.

Choix de rendu : CSR (`ssr: false`) avec serveur Node Nitro derrière Nginx.
Lecture du YAML central au démarrage Node, exposition uniquement de public.api_url
sous apiBase. Le YAML réel n’a pas été modifié : il faut encore compléter ses
sections applicatives depuis l’exemple, en conservant PostgreSQL. Node 18 par
défaut est incompatible ; Node 24.18.0 est disponible sous
/home/thibaut/.nvm/versions/node/v24.18.0/bin. npm 11.16.0. Nuxt 4.6.4,
Vue 3.5.45, Vite 8.3.6, Pinia 4.1.0, @pinia/nuxt 1.0.3, ofetch 1.5.1,
yaml 2.9.1 ; dépendances exactes et package-lock.json. Playwright 1.64.1 utilise
Chromium système ; Prettier 3.9.10 a appliqué les conventions JS demandées.

Le backend expose désormais Content-Disposition dans son CORS pour permettre
au client de conserver le nom des fichiers. Aucun modèle ni schéma changé.
L’installateur dispose des phases frontend, prepare, deploy et all ; deploy.py
prépare les unités systemd et Nginx, sauvegarde les fichiers existants et valide
Nginx avant rechargement. Aucune de ces phases n’a été exécutée ici ; pas de sudo,
base, restauration ou déploiement système à l’étape 6. Les serveurs Nuxt des tests
sont temporaires et utilisent l’exemple sans secret, avec API simulée.

Vérifications : construction de production réussie ; tests unitaires frontend
(configuration publique et données des formulaires), trois parcours Chromium
(connexion/CSRF/animation/séquence/commentaire, multipart/téléchargement/page,
droits/erreur/mobile). Captures locales ignorées sous frontend/test-results/.
18 tests backend SQLite et 12 tests installation réussis, syntaxe Bash et diff
valides. Aucun accès PostgreSQL historique. Les tests navigateur nécessitent une
autorisation hors sandbox pour écouter sur 127.0.0.1 et lancer Chromium.

Limites : intégration réseau avec la véritable configuration LDAP/cookies HTTPS,
médias réels et Nginx non testée. npm audit signale 12 alertes transitives faibles
ou modérées (Nitro/deepmerge/glob/minimatch) ; pas d’override majeur imposé.
Aucun secret imprimé, aucun changement historique, aucun commit créé.
Préserver les modifications préexistantes de REPRISE.md.

## Point final avant clear — après l’étape 6

L’utilisateur annonce « je vais faire un clear ». Cette demande autorise la
sauvegarde du contexte uniquement, sans démarrer le déploiement.
Les anciens paragraphes annonçant que l’étape 6 n’est pas commencée sont dépassés
par le bilan de l’étape 6 et ce point final.

Dernière validation de l’étape 6 : build Nuxt réussi ; quatre tests unitaires
frontend répartis dans deux fichiers ; trois parcours Chromium réussis sur la
version finale (4,6 s), avec API simulée ; 18 tests backend SQLite et 12 tests
installation réussis. Syntaxe Bash et git diff --check valides. Les tests
navigateur vérifient aussi le nom du téléchargement et l’absence de
centralConfigPath/postgresql dans le HTML. Captures :
frontend/test-results/animation.png et accueil-mobile.png, ignorées par Git.
Les anciens avertissements ldap3/pyasn1 et NO_COLOR/FORCE_COLOR n’empêchent pas
les tests. Pas de serveur de test laissé en fonctionnement.

Pour relancer depuis frontend/, sélectionner Node compatible :
PATH=/home/thibaut/.nvm/versions/node/v24.18.0/bin:$PATH
Puis npm test, npm run build et npm run test:browser. Chromium système utilisé.
Les tests navigateur lancent Nuxt sur 127.0.0.1:3107 et lisent l’exemple YAML sans
secrets via NUXT_CENTRAL_CONFIG_PATH ; ils ne testent pas l’intégration réseau
réelle avec Flask/LDAP/PostgreSQL. Le YAML central réel reste incomplet pour
l’exploitation : préserver ses identifiants PostgreSQL en ajoutant les sections
applicatives nécessaires. Ne pas afficher son contenu dans la conversation.

Restent à faire sur demande : compléter la configuration réelle, vérifier les
médias historiques et l’authentification, puis préparer/revoir et éventuellement
appliquer le déploiement Nginx/systemd. Aucun déploiement effectué à l’étape 6.
Les 12 alertes npm transitives (six faibles, six modérées) restent documentées.
Références : frontend/README.md, backend/README.md, installation/README.md.

État Git relu lors de ce clear : uniquement M REPRISE.md. Les anciennes listes
de fichiers modifiés ne décrivent donc plus l’état actuel. Aucun commit créé par
l’agent ; ne pas déduire de cet état qu’un commit utilisateur est à refaire.
Préserver toutes les modifications et données locales ; ne pas toucher à
ancien_animalle/, aux identifiants réels ni à la base restaurée.
