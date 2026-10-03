# Contrat d’interface Concorde

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Table Selection | Non applicable : aucune sélection multiple | static/app.js | Action Examiner par ligne | Lire une observation |
| Select/Listbox | native | static/index.html et app.js | Choix finis avec label | Navigation clavier native |
| Date | Intl.DateTimeFormat | static/app.js date() | fr-CA, fuseau du navigateur | Horodatage dans activité |
| Form | Formulaire HTML et API Pydantic | static/app.js et models.py | Import, analyse, réglages, révision | Erreur locale et réponse API |
| Scrollbar | CSS global | static/styles.css :root et html | Tableau overflow auto | Page et dialogue longs |
| Toast | toast() | static/app.js | Région status, succès bref | Retour après action |
| CRUD | API locale FastAPI | server.py et service.py | Import/lecture/révision ; pas de suppression | Persistance locale |

## Flux

Bibliothèque → dossier → analyse → progression → révision → preuves → rapport.
La revue ne change pas les conclusions machine : elle ajoute une décision humaine horodatée.
Un projet doit contenir des PDF de référence ET des PDF d’atelier pour être importé.
Fichiers invalides, protégés, trop gros ou trop nombreux : refus explicite. Pas d’écrasement.

## Requêtes asynchrones

Recherche après 300 ms, annulation de la précédente requête, filtres conservés lors de la
pagination. Pas de noms de projet ni de texte recherché dans les paramètres d’URL publics.
Le hash contient uniquement les identifiants de navigation locale. Une seule analyse GPU
à la fois dans le serveur. Arrêt après la page en cours ; cache conservé pour relancer.
Le redémarrage classe une tâche inachevée « interrompue ». Pas de succès silencieux.
Les pages en erreur ou sans OCR demandé restent comptabilisées dans la couverture.

## Politique des formulaires

Contraintes HTML (required/min/max) lues par validateForm(), erreurs intégrées au formulaire, puis validation serveur Pydantic. Les formulaires déclarent novalidate pour éviter les bulles du navigateur.
Les sélecteurs natifs et le textarea à redimensionnement vertical sont des exceptions
documentées aux préférences du skill premium. Tous les boutons data-* utilisent la
délégation d’événements de app.js, compatible avec une CSP sans scripts inline.
Les faux positifs du contrôle statique des handlers inline doivent être documentés,
jamais corrigés par l’ajout d’un onclick vide.

## Contrôle de qualité

Aucune mesure de performance de détection n’est revendiquée sans annotations de vérité
terrain et évaluation par projet. Les compteurs affichés sont les résultats du moteur.
La présentation du rapport et l’interface sont consultables sur les données réelles.
