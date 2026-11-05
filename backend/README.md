# Backend — étape 1

Cette étape, explicitement demandée, fournit uniquement les modèles SQLAlchemy,
la migration initiale Alembic et la lecture de la connexion YAML nécessaire aux
migrations. L'API Flask, Marshmallow, Gunicorn et les services métier seront
implémentés à l'étape 5. Aucun script d'installation ni base n'a été créé.

L'étude, les décisions de compatibilité et les limites de validation sont dans
[docs/reprise_historique.md](docs/reprise_historique.md).

Python >= 3.10 est requis (vérification effectuée sous Python 3.11.2).
Les dépendances de cette étape sont fixées dans `requirements.txt`.
Dans un environnement virtuel dédié disposant de ces dépendances, depuis la racine :

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
python -m alembic -c backend/alembic.ini upgrade head --sql
python -m alembic -c backend/alembic.ini downgrade 0001_initial:base --sql
PYTHONPATH=backend python backend/tests/audit_dump.py --models
```

L'audit est facultatif et nécessite le dump local ignoré
`installation/dump_bdd/bdd.dump`. Il analyse le format précis de cet export
MariaDB sans exécuter son SQL et affiche seulement des agrégats. Ce n'est pas un
convertisseur universel. Les tests unitaires fonctionnent sans dump ni YAML réel.
Les commandes Alembic ci-dessus produisent du SQL uniquement, sans connexion.
Le downgrade génère des suppressions : ne pas exécuter ce SQL sur des données à conserver.

Le mode connecté, réservé à l'étape 3, lira directement
`installation/config_principal.yaml`, indépendamment du répertoire courant.
Le fichier `installation/config_principal.example.yaml` définit les seules clés
nécessaires à cette étape, sans identifiants réels. Aucun URL concurrent n'est
stocké dans `alembic.ini`. Les autres clés de configuration seront définies lors
des étapes concernées. Ne pas publier le dossier `installation/` par HTTP.

Les collections `sequences`, `tags`, `materiel`, `sequence` et `thematiques`
sont des vues ORM en lecture seule : écrire les associations via les classes
`RelAnimSequence`, `RelAnimTag`, `RelMatPedaSequence` et
`RelMatPedaThematique`, qui conservent leurs identifiants historiques.
Aucun import ne crée de connexion et aucune utilisation de `create_all()` n'est prévue.
