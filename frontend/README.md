# Frontend Anim’Malle — étape 6

Interface Vue 3 / Nuxt 4 / Vite, en français, adaptative et accessible au clavier.
Elle reprend la navigation et les workflows des templates Jinja et des composants
Vue 2 historiques, sans modifier `ancien_animalle/`.

## Fonctionnalités

- Connexion, session Pinia, déconnexion et retour à la connexion sur expiration.
  ofetch transmet les cookies et le jeton CSRF, renouvelé après connexion ; aucune
  mutation ni upload n’est réessayé automatiquement.
- Pédathèque : filtres par auteur, statut et mots-clés, pertinence, pagination,
  raccourci « Mes animations », consultation et impression.
- Création et remplacement complet des animations, brouillon / à valider,
  séquences ordonnées, références et associations de médias. Les identifiants
  existants sont conservés et les champs calculés sont exclus des PUT.
- Validation et réattribution administrateur, suppression confirmée, commentaires.
- Médiathèque et outils : recherche par types et thèmes, import multipart,
  consultation, modification administrateur et remplacement de fichier, export
  ZIP/ODT et téléchargement authentifié. Aperçu sur demande des images usuelles,
  sons, vidéos et PDF selon les formats reconnus par le navigateur.
- Pages d’outils : HTML nettoyé par le backend, documents associés, édition Markdown
  administrateur, création d’une page absente et signalement d’un échec de mail.
- Administration des catégories et mots-clés ; refus de suppression des références
  encore utilisées géré par l’API. Statistiques cumulées et tableau mensuel.

L’API reste l’autorité pour les droits : les boutons conditionnels ne remplacent
pas les contrôles serveur. Les erreurs sont affichées sans effacer le formulaire.
Une confirmation protège les changements de route pendant l’édition. Fermer ou
recharger l’onglet ne sauvegarde pas automatiquement le travail.

Le texte des animations et des notices est affiché comme texte préservant les
retours à la ligne ; seul le HTML des pages, nettoyé côté backend, est injecté.
Les aperçus des formats bureautiques autres que PDF passent par téléchargement.
Les composants et services PrimeVue nécessitant un abonnement ne sont pas utilisés.
PrimeVue Button est utilisé en mode sans thème, avec les styles du projet.

## Versions et prérequis

Versions stables vérifiées le 5 novembre 2026 sur le registre npm officiel,
fixées dans `package.json` et verrouillées transitivement dans `package-lock.json` :

| Bibliothèque | Version |
| --- | --- |
| [Nuxt](https://registry.npmjs.org/nuxt/latest) | 4.6.4 |
| [Vue](https://registry.npmjs.org/vue/latest) | 3.5.45 |
| [Vite](https://registry.npmjs.org/vite/latest) | 8.3.6 |
| [Pinia](https://registry.npmjs.org/pinia/latest) | 4.1.0 |
| [@pinia/nuxt](https://registry.npmjs.org/@pinia%2fnuxt/latest) | 1.0.3 |
| [ofetch](https://registry.npmjs.org/ofetch/latest) | 1.5.1 |
| [yaml](https://registry.npmjs.org/yaml/latest) | 2.9.1 |
| [PrimeVue](https://registry.npmjs.org/primevue/4.5.5) | **4.5.5**, version imposée |
| Playwright (tests) | 1.64.1 |
| Prettier (formatage) | 3.9.10 |

Nuxt exige Node `^22.22.3 || ^24.15.0 || >=26.0.0` ; validation effectuée avec
Node **24.18.0** et npm **11.16.0**. Le Node 18 fourni par défaut dans cet
espace n’est pas compatible. Sélectionner Node 24 LTS dans le PATH avant npm.

## Configuration et rendu

Choix : **CSR** (`ssr: false`), servi par le serveur Node Nitro, et non export
statique. Les appels à Flask viennent exclusivement du navigateur : aucune
propagation de cookie de session entre un rendu SSR et l’API n’est nécessaire.
Les domaines frontend et API doivent être distincts, avec des cookies compatibles
avec leur topologie (voir `backend/README.md`).

Au démarrage, le serveur Nuxt lit directement
`installation/config_principal.yaml` avec `yaml`. Il valide `public.api_url` et
expose seulement `{ apiBase: '<origine API>/api' }` dans la configuration publique.
Le YAML n’est jamais copié dans les assets. Son chemin est une valeur **privée**
de runtimeConfig, résolue à la construction. Après déplacement du dépôt,
reconstruire ou définir `NUXT_CENTRAL_CONFIG_PATH` vers le même YAML central.
Cette variable est également utilisée par les tests pour leur fichier temporaire.

Changer l’adresse API dans le YAML demande un **redémarrage Node**, sans rebuild.
Changer le code demande une reconstruction puis un redémarrage. Les clés
`nuxt.port` et `nginx.*` servent à la génération des services et du proxy ; les
modifier demande une nouvelle préparation/application du déploiement.
Ne pas définir `NUXT_PUBLIC_API_BASE` : le hook serveur impose la valeur du YAML.

La construction est indépendante des secrets et d’une base disponible. Le serveur
refuse de démarrer si le YAML est absent ou si l’origine API est invalide.
Le YAML réel existant ne contient pas encore toutes les sections applicatives :
le compléter depuis l’exemple **sans remplacer les identifiants PostgreSQL**.

## Commandes

Depuis `frontend/`, avec Node compatible :

```sh
npm ci
npm test
npm run build
npm run test:browser
npm run dev
npm start
```

`dev` et `start` démarrent un serveur ; utiliser le YAML réel complété et les
origines/cookies adaptées. Les tests navigateur démarrent uniquement un serveur
Nuxt temporaire sur `127.0.0.1:3107`, lisent l’exemple sans secrets et interceptent
les appels API. Chromium doit être installé ; `CHROMIUM_PATH` adapte son chemin.
Aucun navigateur ni paquet système n’est téléchargé automatiquement.

`./installation/install.sh frontend` (depuis la racine) effectue `npm ci`, les
tests unitaires et la construction. La préparation et l’application Nginx/systemd
sont documentées dans `installation/README.md`.

## Validation et limites

Construction de production réussie, quatre tests unitaires dans deux fichiers,
trois parcours Chromium réussis : connexion/rotation CSRF/création et modification
avec séquence/commentaire ; import multipart/téléchargement/page outil ; droits,
erreur de validation et affichage mobile sans débordement. Aucun avertissement Vue
ni erreur JavaScript observé dans ces parcours. Captures locales produites dans
`test-results/animation.png` et `test-results/accueil-mobile.png` (ignorées par Git).

Le backend expose `Content-Disposition` en CORS pour conserver les noms et
extensions des fichiers téléchargés par le frontend.

Les 18 tests backend (SQLite temporaire) et les 12 tests installation passent.
Aucune connexion aux données PostgreSQL historiques ni modification système n’a
été nécessaire. Les tests Chromium simulent les réponses Flask : l’intégration
réseau complète avec LDAP, cookies HTTPS, fichiers réels et Nginx reste à valider
sur la configuration de déploiement. Aucun déploiement de production effectué.

`npm audit --omit=dev` signale **12 alertes transitives : six faibles et six
modérées**, sans alerte élevée/critique. Elles remontent via Nitro : deepmerge
4.3.1, glob 13.0.6 et minimatch 10.2.6. La dernière deepmerge stable est encore
4.3.1 ; les correctifs glob 14 et minimatch 11 changent de majeure. Aucun override
incompatible ni rétrogradation Nuxt automatique appliqué. Réévaluer à la prochaine
mise à jour Nitro ; ne pas présenter cet audit comme vierge.
