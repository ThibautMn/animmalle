# Point de reprise — 5 novembre 2026

L'étape 1 est terminée selon les documents présents : modèles SQLAlchemy,
migration initiale Alembic et étude des modèles et du dump MariaDB historiques.
Voir `backend/README.md` et `backend/docs/reprise_historique.md` pour les choix,
les limites et les commandes de validation.

Après le plantage de VS Code, les quatre tests hors ligne ont été relancés avec
succès :

```sh
PYTHONPATH=backend /tmp/animmalle-models-venv/bin/python -m unittest discover -s backend/tests -v
```

L'environnement temporaire existait encore lors de cette vérification. Aucun
serveur, aucune création de base et aucune restauration n'ont été lancés pendant
la reprise. La validation réelle des migrations sur PostgreSQL reste à réaliser
à l'étape 3 ; la conversion et l'import du dump MariaDB restent à l'étape 4.

La prochaine étape est l'étape 2 : créer `installation/install.sh` sans
l'exécuter. Elle n'a pas encore été autorisée : la question a été posée, puis
l'utilisateur a demandé de sauvegarder l'avancement avant un clear. Attendre sa
demande explicite avant de commencer cette étape, conformément à `AGENTS.md`.

Préserver toutes les modifications locales et les suppressions/déplacements
historiques déjà présents. Ne pas restaurer les fichiers supprimés à la racine
et ne pas modifier `ancien_animalle/`. Les nouveaux fichiers de `backend/` et
d'`installation/` sont encore non suivis ; `.gitignore` est modifié. Aucun commit
n'a été créé pendant cette reprise.
