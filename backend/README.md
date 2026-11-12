# Backend Flask

L’étape 5 fournit une API JSON Flask, les validations et sérialisations Marshmallow,
les services SQLAlchemy, les sessions authentifiées et un point d’entrée Gunicorn.
Les neuf tables et la migration `0001_initial` restent inchangées. Les données
restaurées aux étapes précédentes sont conservées. Le frontend est implémenté à l’étape 6 (voir `frontend/README.md`).

Organisation : `animmalle/models.py` définit les modèles, `schemas.py` les contrats
JSON, `services.py` les transactions métier, `routes.py` les routes, `auth.py`
l’authentification, `files.py` les fichiers et exports, `notifications.py` les mails,
et `__init__.py` la fabrique `create_app()`. Aucun import ne se connecte à la base.
Aucun démarrage applicatif ne crée de table : seul Alembic gère le schéma.
L’étude du schéma historique reste dans [reprise_historique.md](docs/reprise_historique.md).

## Configuration et lancement

Python **3.11 minimum** ; dépendances fixées dans `requirements.txt`. Versions
stables vérifiées sur les métadonnées PyPI le 5 novembre 2026 :
[Flask 3.1.3](https://pypi.org/project/Flask/3.1.3/),
[Marshmallow 4.4.0](https://pypi.org/project/marshmallow/4.4.0/),
[Gunicorn 26.2.0](https://pypi.org/project/gunicorn/26.2.0/),
[ldap3 2.9.1](https://pypi.org/project/ldap3/2.9.1/),
[Markdown 3.11.2](https://pypi.org/project/Markdown/3.11.2/) et
[nh3 0.3.7](https://pypi.org/project/nh3/0.3.7/).
Les quatre dépendances modèles/migrations déjà fixées sont conservées.
nh3 remplace Bleach pour nettoyer le HTML après rendu Markdown ;
[Bleach annonce la fin de sa maintenance](https://pypi.org/project/bleach/).

Compléter **le YAML réel existant**, en préservant sa section PostgreSQL, avec les
sections de `installation/config_principal.example.yaml`. Le backend les valide
au démarrage. Le fichier réel n’a pas été modifié à cette étape : les adresses
publiques et les paramètres LDAP doivent correspondre au déploiement réel.
Ne pas recopier les valeurs d’exemple telles quelles, ni écraser le mot de passe
PostgreSQL restauré. Le YAML reste privé avec des permissions 600.

- `backend` : secret aléatoire (32 caractères minimum), cookies, durée de session,
  taille maximale des requêtes et extensions autorisées.
- `public` : origines frontend/API, sans chemin ; CORS autorise uniquement le
  frontend déclaré, avec credentials. Les API sont sous `/api`.
- `auth` : LDAP par défaut, groupes administrateurs ; alternative locale explicite
  avec hachages Werkzeug, sans compte ni mot de passe fourni par défaut. Utiliser
  les noms historiques exacts pour conserver les droits d’auteur. Les cookies
  contiennent des données signées, pas de mot de passe. Les groupes sont figés
  jusqu’à la prochaine connexion ou l’expiration de session.
- `auth.ldap` : LDAPS, StartTLS ou LDAP sans chiffrement selon les clés suivantes.
  Avec `ssl: false`, `start_tls: false` permet explicitement LDAP sans chiffrement
  (port 389) ; les mots de passe transitent alors en clair. Sans cette clé,
  StartTLS reste actif. Avec `ssl: true`, LDAPS est utilisé indépendamment de
  `start_tls`. La CA doit être reconnue pour les modes TLS.
  `service_bind_dn` et `service_password`
  permettent l’autocomplétion des utilisateurs de l’annuaire ; sinon les auteurs
  déjà présents servent de suggestions. Aucune requête LDAP anonyme.
- `paths` : chemins relatifs à la racine du dépôt ou absolus. Les nouveaux fichiers
  et pages sont écrits hors de l’historique, dans des dossiers ignorés par Git.
- `proxy` : nombres exacts de relais de confiance par en-tête, zéro par défaut.
  Gunicorn doit être isolé derrière Nginx avant d’augmenter ces valeurs.
- `gunicorn` : bind, workers et timeout ; lecture directe du YAML.
- `mail` : notification des éditions de pages, désactivée par défaut ; destinataires
  administrateurs explicites. Une panne SMTP ne fait pas perdre l’édition et la
  réponse indique `notification: failed`.

Pour des domaines de sites différents, configurer `cookie_samesite: 'None'` et
`cookie_secure: true` avec HTTPS. Pour du développement HTTP local, désactiver
explicitement `cookie_secure`. Le cookie reste HttpOnly. Les changements YAML
nécessitent un redémarrage des workers.

Commandes depuis la racine, une fois le YAML complété :

```sh
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/gunicorn -c backend/gunicorn.conf.py
```

La deuxième commande démarre un serveur : elle est fournie pour l’exploitation,
**elle n’a pas été exécutée**. Aucun service système ni Nginx n’a été installé ou
rechargé à l’étape 5 ; le déploiement complet attend les choix Nuxt de l’étape 6.

## Certificat LDAP interne

Pour un annuaire sans TLS, configurer `ssl: false`, `start_tls: false`,
`port: 389` dans `auth.ldap`, puis redémarrer Flask. Ces paramètres s’appliquent
à la connexion utilisateur et à l’autocomplétion. Le YAML privé a été ajusté
sur ces trois clés uniquement, en préservant les autres valeurs.
Validation : 22 tests backend réussis, dont l’authentification et la recherche
LDAP sans négociation TLS (annuaire simulé) et la validation du nouveau booléen.
La connexion avec un compte réel reste à vérifier après redémarrage.

Si la connexion échoue avec `CERTIFICATE_VERIFY_FAILED` et
`unable to get local issuer certificate`, fournir la chaîne d’autorités PEM
approuvée par l’administrateur de l’annuaire dans `auth.ldap.ca_certs_file` du
YAML central. Le chemin peut être absolu ou relatif à la racine du dépôt.
Cette clé est facultative ; absente ou vide, elle conserve la confiance système.
Ne fournir aucune clé privée et conserver ce fichier local hors Git. La validation
du certificat et du nom du serveur reste obligatoire. Redémarrer Flask après
modification du YAML ; le débogueur utilise `--no-reload`.

Diagnostic du 5 novembre 2026 : connexion TCP à l’annuaire configuré réussie,
échec StartTLS avant authentification faute d’autorité locale reconnue. Aucun
identifiant envoyé. L’authentification réelle reste à vérifier après fourniture
du certificat d’autorité. La fermeture d’une connexion TLS en échec ne masque
plus la réponse 503 si le socket est déjà fermé.
Validation : les 20 tests backend passent avec
`PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v`,
dont les cas de fermeture après échec TLS et d’autorité personnalisée avec
validation obligatoire du certificat. `git diff --check` sans erreur.

## Contrat API

Les corps sont des objets JSON, sauf uploads multipart. Champs inconnus refusés,
erreurs JSON `{ "error": { "code": "…", "message": "…", "fields": {} } }`
(`fields` seulement pour la validation). Codes : 401 sans session, 403 sans droit
ou CSRF, 404 absent, 409 conflit de contrainte, 413 trop volumineux, 422 validation,
503 base/annuaire indisponible. Aucun chemin de stockage ni secret n’est sérialisé.

Avant connexion : `GET /api/auth/session` crée le cookie et renvoie `csrf_token`.
Envoyer ce token dans `X-CSRF-Token` pour **toute** mutation, connexion comprise,
avec le cookie (`credentials: 'include'` côté navigateur). `POST /api/auth/login`
attend `{ "login": "…", "password": "…" }` et renvoie un nouveau token ; remplacer
l’ancien dans le client. `POST /api/auth/logout` ferme la session.

| Routes sous `/api` | Comportement |
| --- | --- |
| `GET /health` | Disponibilité PostgreSQL, sans information de connexion |
| `GET /auth/session`, `POST /auth/login`, `POST /auth/logout` | Session et CSRF |
| `GET, POST /animations` | Recherche et création |
| `GET, PUT, DELETE /animations/{id}` | Consultation, remplacement complet, suppression |
| `POST /animations/{id}/validate` | Validation administrateur |
| `PUT /animations/{id}/author` | Réattribution administrateur, corps `{ "auteurs": "…" }` |
| `GET, POST /animations/{id}/comments` | Commentaires, auteur/date calculés côté serveur |
| `DELETE /animations/{id}/comments/{comment_id}` | Auteur du commentaire ou administrateur |
| `GET /animations/{id}/download` | Archive ZIP avec ODT et médias disponibles |
| `GET, POST /materials` | Médias et outils facilitateurs |
| `GET, PUT, DELETE /materials/{id}` | Consultation ; modification/suppression administrateur |
| `POST /materials/{id}/file` | Ajout/remplacement de pièce jointe administrateur |
| `GET /materials/{id}/file` | Pièce jointe en téléchargement authentifié |
| `GET /materials/{id}/download` | Fiche ODT et pièce jointe en ZIP |
| `GET, POST /thesaurus`, `PUT, DELETE /thesaurus/{id}` | Lecture ; administration des mots-clés |
| `GET /thesaurus/{id}/pictogram` | PNG du terme (thématiques, lieux, saisons), si présent |
| `PUT /thesaurus/{id}/pictogram` | Administrateur : ajoute ou remplace le PNG (champ multipart `file`, 1 Mo max). Le fichier est `<libellé>.png` ; renommer le terme renomme le fichier |
| `DELETE /thesaurus/{id}/pictogram` | Administrateur : retire le PNG (supprimer le terme le retire aussi) |
| `GET, PUT /pages/{name}` | Markdown, HTML nettoyé, documents ; édition administrateur |
| `GET /authors?q=…`, `GET /users?q=…` | Suggestions d’auteurs et utilisateurs (2 caractères pour users) |
| `GET /stats` | Séries cumulées historiques selon la dernière date de modification |

Les listes animations/materials acceptent `page` (défaut 1), `page_size` (1–200,
défaut 50), `tag` répété. Elles renvoient `items`, `total`, `page`, `page_size` et
une pertinence numérique `{matched, requested}` ; au moins un tag doit correspondre.
Animations : `auteur`, `statut` (1 validée, 2 complète à valider, 3 brouillon).
Materials : `kind=media|outil`, `type` répété. Thésaurus : filtre `reference`,
valeur vide pour les catégories.

Les noms de champs correspondent aux colonnes SQLAlchemy avec les suffixes `_id`
pour les FK. Consulter `schemas.py` pour le contrat complet. Exemple de création :

```json
{
  "titre": "Découverte du milieu", "statut": 3,
  "fk_duree_id": null, "tags": [], "sequences": []
}
```

`PUT /animations/{id}` remplace la fiche et la liste ordonnée des séquences.
Une séquence existante conserve son `id`, une nouvelle l’omet. Une séquence retirée
est supprimée si elle n’a plus d’autre animation. Les séquences partagées ne sont
pas modifiables directement ; les références à une autre animation sont refusées.
`materiel` est une liste d’identifiants de matériaux. Les familles attendues sont
`ref.duree` pour l’animation ; `ref.duree_seq`, `ref.modalites`, `ref.approches` et
`ref.type_seq` pour les séquences. La durée de l’animation est ajoutée à ses tags.
Toute la modification se fait dans une transaction, annulée au premier échec.

Un auteur peut créer, modifier et supprimer ses fiches non validées ; seul un
administrateur peut valider ou modifier une fiche validée. Les brouillons restent
visibles à leur auteur et aux administrateurs, y compris par URL directe. Cela
corrige les accès insuffisamment contrôlés et les mutations par GET de l’historique.
La suppression d’une fiche supprime ses commentaires et associations ; celle d’un
matériau détache ses associations, en conservant le fichier physique. Les mots-clés
encore référencés ne sont pas supprimables.

Création d’un média avec fichier : `POST /materials` multipart, champ `data` contenant
l’objet JSON (`nom`, `fk_type_mat_id`, `thematiques`…), champ `file` facultatif.
C’est accessible à tout utilisateur connecté, sans permettre de remplacer le
fichier d’une notice existante. Les fichiers sont nommés par SHA-256 et nom sécurisé,
sans écrasement. Les doublons de contenu/nom partagent le fichier ; si la transaction
SQL échoue après stockage, un fichier non référencé peut rester, sans perte de données.
Les outils utilisent `fk_type_mat_id` de famille `ref.type_outil`, avec difficulté,
variante, matériel et type de pièce jointe facultatifs.

## Reprise des fichiers et différences d’export

Les pages et leurs éditions sont conservées dans `backend/pages`,
avec une révision horodatée du contenu précédent et remplacement atomique du
Markdown courant. Le HTML est toujours recalculé et nettoyé avant réponse. Les
révisions historiques sont conservées avec les pages dans `backend/pages`.

Les ressources historiques ont été déplacées dans `backend/` : médias dans
`uploads/`, pages et révisions dans `pages/`, pictogrammes dans
`pictograms/`. Les clés YAML `uploads`, `pages` et `pictograms`
pointent désormais vers ces dossiers, exclus de Git et à sauvegarder avec les
nouveaux uploads et pages. Leur lecture ne dépend plus de `ancien_animalle/`.

Les médias ne sont pas dans le dump SQL. Le backend lit leur nom de fichier
uniquement dans le dossier uploads configuré ; un chemin arbitraire du
dump ne peut pas servir de fichier. Un fichier absent donne 404 ; les ZIP listent
les identifiants absents dans `fichiers_absents.json`.

Les exports produisent un ODT ODF 1.2 éditable et un `donnees.json` complet, avec
les pièces jointes disponibles. Ils sont générés en mémoire, avec échappement XML,
sans fichier temporaire partagé entre téléchargements. La mise en page py3o et
les pictogrammes incorporés dans l’ancien modèle ne sont pas reproduits : le
Markdown source est conservé dans l’ODT, et les pictogrammes restent accessibles
via l’API. Cette différence de présentation n’affecte pas les données métier.

## Validation exécutée

Depuis la racine, dans le venv du projet :

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m unittest discover -s installation/tests -v
.venv/bin/python -m pip check
bash -n installation/install.sh
git diff --check
```

Les tests API ordinaires utilisent une base SQLite jetable avec les FK actives,
les migrations sont aussi contrôlées hors ligne. Pour la validation PostgreSQL :

```sh
ANIMMALLE_TEST_POSTGRES=1 PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p test_api.py -v
```

Cette commande lit la connexion du YAML, crée un schéma aléatoire par test dans
une transaction, y applique la migration initiale, puis annule schéma et données.
Les commits des routes utilisent des savepoints. Aucun test n’écrit dans `public` ;
une empreinte des neuf tables restaurées et l’inventaire des schémas temporaires
sont comparés avant/après. Le rôle doit pouvoir créer un schéma dans la base.
Les tests fichiers utilisent des dossiers temporaires. LDAP et SMTP sont simulés :
aucun annuaire réel ni envoi de mail n’a été testé. ldap3 émet deux avertissements
de dépréciation pyasn1, sans échec ; 2.9.1 est sa dernière version stable PyPI.

Résultats de l’étape : 18 tests backend locaux, 14 workflows sur PostgreSQL et neuf
tests installation réussis ; `pip check`, syntaxe Bash et diff sans erreur.
Les accès PostgreSQL et PyPI ont nécessité une autorisation hors sandbox.
La validation HTTP passe par le client Flask, sans serveur réseau.

Restent à vérifier en environnement : configuration réelle des origines et cookies,
connexion LDAP/CA, SMTP si activé, disponibilité des médias, ouverture des ODT dans
la suite bureautique cible, puis intégration frontend et déploiement Nginx/Nuxt.


## Adaptation pour le frontend — étape 6

Le CORS expose `Content-Disposition` à l’origine frontend autorisée afin que les
uploads téléchargés via ofetch conservent leur nom et leur extension. Aucun droit,
schéma ou contenu métier modifié. Le test session/CSRF/CORS vérifie cet en-tête.
Les 18 tests backend SQLite ont été relancés avec succès à l’étape 6 ; pas de
nouvel accès PostgreSQL. La configuration réelle et le déploiement restent à valider.

## Déplacement des ressources historiques — 5 novembre 2026

Les trois dossiers ont été déplacés sans écrasement : 448 entrées pour les
médias, 60 pour les pages et révisions, 17 pour les pictogrammes. Les inodes,
tailles et dates de modification ont été comparés avant et après déplacement
sur le même système de fichiers : aucune différence. Les chemins des deux YAML
et les exclusions Git ont été vérifiés. Les 14 tests API SQLite ont réussi avec
`PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p test_api.py -v` ;
`git diff --check` est sans erreur. Aucune base ni aucun serveur n’a été modifié.
La correspondance exhaustive entre les médias et les références en base reste
à vérifier avant la suppression complète du code historique.

Les dossiers médias et pages sont désormais unifiés dans `backend/uploads/` et
`backend/pages/`. Les clés et la logique de lecture de secours `legacy_*` ont été
supprimées. Les 448 entrées médias et 60 entrées pages ont été déplacées sans
écrasement, avec contrôle des inodes et tailles. Les révisions restent conservées.
Validation après unification : 18 tests backend réussis avec
`PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v`,
contrôle des trois chemins des deux YAML et `git diff --check` sans erreur.

Modification du thésaurus : `PUT /api/thesaurus/{id}` accepte uniquement le
`label` (1 à 80 caractères), pour un administrateur authentifié avec CSRF.
Les identifiants, codes et références sont conservés.

### Aperçus de pièces jointes

`GET /api/materials/<id>/preview` renvoie les images PNG/JPEG/GIF/WebP,
les PDF, les médias audio et vidéo, ou convertit les documents ODT/ODS/ODP,
DOC/DOCX, XLS/XLSX, PPT/PPTX et RTF en PDF. La route suit l’authentification
existante et n’expose pas les chemins des fichiers.

La conversion nécessite l’exécutable système `libreoffice` ou `soffice` dans
le PATH du service backend, avec les modules Writer/Calc/Impress correspondants.
Aucune bibliothèque Python UNO supplémentaire n’est nécessaire.
Chaque conversion utilise un répertoire et un profil temporaires distincts,
avec les macros désactivées et un délai maximal de 60 secondes. Les originaux
sont conservés ; les aperçus ne sont pas mis en cache. Un format non pris en
charge renvoie 415, un LibreOffice absent 503 et une conversion impossible 422.
Référence : https://help.libreoffice.org/latest/en-US/text/shared/guide/pdf_params.html

### Vignettes des médias

`GET /api/materials/<id>/thumbnail` renvoie une vignette JPEG (480×360 max, qualité 70) pour les images et les
vidéos ; elle est générée au premier appel puis mise en cache dans `paths.thumbnails` (facultatif, par défaut le
dossier `uploads` suffixé par `_vignettes`, ignoré par Git et régénérable). Les originaux ne sont jamais modifiés.
Les images utilisent Pillow (`requirements.txt`) ; les vidéos nécessitent l’exécutable système `ffmpeg`
(503 s’il est absent, 422 en cas d’échec, 415 pour un autre format). La réponse porte `Cache-Control: private,
max-age=86400`. Vérifié : tests unitaires `cd backend && ../.venv/bin/python -m unittest tests.test_api tests.test_schema`
(28 tests OK, `ffmpeg` simulé) et, sur les médias historiques, 31 Mo → 22 Ko, 20 Mo → 34 Ko, 16 Mo → 17 Ko
(0,3 s au premier appel). Vignettes vidéo vérifiées avec `ffmpeg` sur des vidéos historiques de 300 à 360 Mo (3 à 21 Ko, 0,3 à 1 s) ; l’image est prise à 0,1 s, puis à 1, 3 et 10 s si elle est quasi noire.

Validation : 24 tests backend réussis via
`PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v`,
dont aperçu PDF natif, conversion simulée et erreurs de conversion/disponibilité.
Une conversion réelle ODT vers PDF avec LibreOffice a également réussi sur un
document temporaire, hors du bac à sable qui empêchait son démarrage.
