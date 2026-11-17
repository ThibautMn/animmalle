# Étude historique et migration initiale

## Sources et périmètre

Étape 1 explicitement autorisée le 5 novembre 2026. Lecture des cinq modules
Peewee de `ancien_animalle/models/`, de leurs utilitaires, de l'initialisation du
thésaurus et des usages dans `views/` (création, édition, validation, recherche,
commentaires, médias et outils). L'historique et les suppressions/déplacements
locaux préexistants sont conservés. Aucun contenu métier du dump n'est recopié
ici et aucun identifiant de connexion historique n'est repris.

Le fichier `installation/dump_bdd/bdd.dump` est un SQL texte UTF-8 MariaDB,
produit avec un client 10.11.19 depuis un serveur 11.8.6. Il contient le schéma,
les données, des ordres CREATE DATABASE/USE/DROP TABLE, des commandes de session,
des verrouillages et des commentaires exécutables MySQL/MariaDB. Ce n'est ni
un dump PostgreSQL ni une archive `pg_restore`. Aucune version Alembic n'existe
dans l'export. Sa compatibilité doit être évaluée par sa structure réelle.

## Inventaire des données examinées

Analyse lexicale des INSERT, sans exécution SQL, puis contrôle des références,
des doublons de couples, des colonnes, des NULL, des longueurs et des dates.

| Table | Lignes | Plus grand identifiant entier | AUTO_INCREMENT exporté |
| --- | ---: | ---: | ---: |
| animation | 105 | identifiants texte | sans objet |
| commentaire | 19 | 45 | 46 |
| mat_peda | 452 | 578 | 579 |
| sequence | 560 | 1187 | 1188 |
| thesaurus | 85 | 88 | 94 |
| rel_anim_sequence | 560 | 1180 | 1181 |
| rel_anim_tag | 936 | 3826 | 3827 |
| rel_mat_peda_sequence | 489 | 1684 | 1685 |
| rel_mat_peda_thematique | 688 | 897 | 898 |

Aucune référence orpheline ni aucun doublon de couple de liaison détecté.
425 difficultés et 403 types de média associés à un outil sont NULL dans
`mat_peda`. Aucun autre NULL n'est présent dans cet export. Les statuts observés
sont 1 (86 animations), 2 (17), 3 (2) ; les usages historiques signifient validée,
terminée et en cours. Le schéma reste un entier sans ajouter de nouvelle
contrainte sur les statuts. Le thésaurus comporte 56 codes vides.

## Correspondance et décisions

Les neuf tables, toutes les colonnes (y compris suffixes `_id` Peewee), les
longueurs et les clés primaires sont conservées. Les classes Python sont en
PascalCase (`MatPeda`, `RelAnimSequence`, etc.). `Animation.id` reste un
VARCHAR(40), sans conversion UUID ni régénération d'identifiants. Les huit
identifiants entiers deviennent des SERIAL PostgreSQL, permettant une reprise
avec identifiants explicites puis un recalage des séquences.

| Écart historique | Décision de la migration initiale |
| --- | --- |
| Peewee impose plusieurs champs non NULL que MariaDB autorise à NULL | Conserver la nullabilité du dump pour `animation.lieu`, `fk_duree_id`, `date_modif`, `mat_peda.difficulte_id`, `date_modif`, `fk_type_mat_outil_id` et les trois champs texte du thésaurus. |
| Peewee déclare `thesaurus.code` unique ; le dump rend `label` unique | Reprendre l'unicité du label ; autoriser les codes vides répétés. Conserver les défauts chaîne vide Peewee sur `reference` et `code`, aussi comme défauts SQL ; les NULL importés restent autorisés. `reference` est un code texte, pas une FK vers un identifiant. |
| Le dump ne contraint pas la durée d'animation, la difficulté et le type média d'outil | Ajouter les trois FK attendues par les modèles et les usages ; aucune référence orpheline observée. Indexer toutes les FK. |
| Le dump n'a pas l'unicité des couples animation/séquence et matériel/séquence déclarée dans Peewee | Rétablir ces deux contraintes ; aucun doublon observé. Conserver aussi les deux unicités de couples avec le thésaurus. Garder les PK entières des liaisons. |
| Défaut Peewee SQLite `datetime('now')` ; défaut MariaDB différent selon la table | Utiliser `CURRENT_DATE` pour les deux `date_modif`, sans mise à jour automatique. Les valeurs historiques explicites sont conservées. |
| Collation MariaDB `utf8mb4_general_ci` | Utiliser les types PostgreSQL standards. L'unicité/comparaison des labels devient sensible à la casse selon la collation PostgreSQL retenue ; ne pas prétendre reproduire les recherches MariaDB. L'API devra définir les comparaisons métier. |

Aucune cascade de suppression ajoutée : les FK gardent leur protection par
défaut. L'historique supprime explicitement les associations, les séquences et
les commentaires avant l'animation ; ce workflow sera implémenté à l'étape 5,
avec examen des éventuelles séquences partagées. Il ne faut pas supprimer des
médias ou des entrées du thésaurus en cascade. Les collections many-to-many
sont en lecture seule côté ORM pour éviter des écritures concurrentes avec
les objets de liaison. L'ordre des séquences est rendu déterministe par l'id de
liaison ; aucune colonne de position n'existe dans l'historique et l'ordre
pédagogique exact devra être confirmé au moment du workflow d'édition.
Les relations simples conservent leurs noms métier (`fk_duree`, `difficulte`,
`commentaires`, etc.). Les champs texte requis n'acquièrent aucun défaut métier
inventé ; les futurs services devront les renseigner explicitement.

## Stratégie de reprise à réaliser à l'étape 4

Ne jamais transmettre ce dump directement à psql ou pg_restore, ni exécuter ses
ordres de suppression sur la cible. Prévoir une conversion des données seules,
ou un environnement MariaDB isolé puis un export contrôlé ; ne pas importer
son schéma dans les tables gérées par Alembic. La transformation devra préserver
les échappements MariaDB (apostrophes, antislashs, retours à la ligne), les chaînes
vides distinctes des NULL, Unicode, dates et tous les identifiants. Refaire
l'audit sur le dump réellement importé et refuser les anomalies sans correction
silencieuse.

Importer dans une transaction sur une cible sans données métier : thésaurus,
animations, séquences et matériel, puis commentaires et associations. Utiliser
des colonnes explicites car leur ordre doit être indépendant du DDL. Après
l'import, vérifier les comptes, les contraintes et les identifiants, puis
recaler les huit séquences au moins au maximum des identifiants importés et
au prochain AUTO_INCREMENT exporté. Pour le thésaurus, préserver en particulier
le prochain id 94 plutôt que reprendre les identifiants 89 à 93. Une table
`alembic_version` seule ne constitue pas des données métier. Aucune reprise
ne doit écraser une base déjà alimentée. Cette stratégie est documentée,
pas exécutée ou implémentée dans cette étape.

## Versions et vérifications effectuées

Versions stables vérifiées le 5 novembre 2026 sur les sources des projets :
[SQLAlchemy 2.1.8](https://pypi.org/project/SQLAlchemy/2.1.8/),
[Alembic 1.20.1](https://pypi.org/project/alembic/1.20.1/),
[PyYAML 6.0.3](https://pypi.org/project/PyYAML/6.0.3/) et
[Psycopg 3.3.8](https://pypi.org/project/psycopg/3.3.8/).
Dépendances installées et vérifiées uniquement dans un environnement temporaire
`/tmp/animmalle-models-venv`, sans modification de l'environnement historique.
`pip check` ne signale aucune incompatibilité.

Quatre tests unitaires passent : configuration des mappers et nullabilité,
comparaison du DDL PostgreSQL des modèles avec les opérations de la migration
figée (y compris index), upgrade/downgrade hors ligne sans lecture de secrets,
validation YAML et encodage des identifiants de connexion. La migration ne dépend
pas des imports des modèles courants, pour rester stable dans le temps.
Le SQL produit a été relu : ordre des dépendances, neuf tables métier, huit
SERIAL, FK, uniques, index, défauts DATE et suppression dans l'ordre inverse.
La génération inclut également la gestion habituelle de `alembic_version`.

Commandes et prérequis reproductibles dans le README du backend. Les contrôles
n'ont créé aucune base et n'ont exécuté aucun SQL sur PostgreSQL. Restent à
l'étape 3 : exécution réelle upgrade/downgrade sur PostgreSQL isolé, comparaison
par introspection/Alembic et tests réels des contraintes. Restent à l'étape 4 :
conversion, import transactionnel et validation des séquences. Ces validations
ne sont pas assimilées à des tests déjà réussis.


## Séparation de `mat_peda` (migration 0008)

La table historique `mat_peda` mélangeait médias et outils facilitateurs (distingués par la
famille du thésaurus de `fk_type_mat_id` : `ref.type_mat` ou `ref.type_outil`). Elle est
remplacée par `media` et `outil_facilitateur`, avec les mêmes identifiants (452 lignes
dans le dump : 425 médias, 27 outils).

| Table | Colonnes |
| --- | --- |
| `media` | `id`, `fk_type_mat_id`, `nom`, `description`, `url`, `date_modif` |
| `outil_facilitateur` | `id`, `fk_type_outil_id` (ex-`fk_type_mat_id`), `nom`, `description`, `url`, `variante`, `difficulte_id`, `materiel`, `date_modif`, `fk_type_mat_outil_id` |
| `rel_media_sequence`, `rel_media_thematique` | ex-`rel_mat_peda_*`, `fk_mat_peda_id` devient `fk_media_id` |

Abandonnées : `localisation` (vide partout), et pour les médias `variante`, `difficulte_id`,
`materiel` (vides) et `fk_type_mat_outil_id` (24 valeurs résiduelles sans sens pour un média,
perdues). Dans le dump, aucune liaison séquence/thématique ne concerne un outil ; la migration
et la reprise refusent d'abandonner une telle liaison. La migration n'a pas de retour arrière.
La reprise du dump (`installation/lib/restore.py`) lit toujours le format historique et
convertit `mat_peda` à l'import ; les prochains identifiants (`AUTO_INCREMENT`) sont repris.
L'API passe de `/materials` à `/media` et `/outils`.

Vérifié : tests unitaires backend (SQLite, DDL de la migration comparé aux modèles), tests de
`installation/` et conversion du vrai dump en lecture seule (425 + 27 lignes, 489 + 688
liaisons). Non vérifié : exécution de la migration 0008 et de la reprise sur PostgreSQL réel.
