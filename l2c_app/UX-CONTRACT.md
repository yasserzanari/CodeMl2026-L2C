# Contrat d’interface Concorde

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Table Selection | state.selectedSheets et updateReportSelection | static/app.js | Cases des feuillets, tout/aucun ; aperçu indépendant | Sélection, recherche, aperçu et export navigateur |
| Select/Listbox | native | static/index.html et app.js | Choix finis avec label | Navigation clavier native |
| Date | Intl.DateTimeFormat | static/app.js date() | fr-CA, fuseau du navigateur | Horodatage dans activité |
| Form | Formulaire HTML et API Pydantic | static/app.js et models.py | Import, analyse, réglages, révision | Erreur locale et réponse API |
| Validation / bonus | static/quality.js | Révisions candidates, calibration descriptive, mapping PDF local | Analyse terminée uniquement; aucune décision métier automatique | Navigation, ordre chronologique, exports locaux, fichier mapping |
| Progression projet | `activeJob()` + bandeau dans static/app.js | Run actif du même projet depuis `/api/overview` | Le suivi détaillé reste sur `#progress`; aucune relance | Statut/pages mis à jour par le polling existant |
| Moteur de lecture | configuration courante `ocr_engine` | static/app.js `renderSettings()` | Carte matérielle nomme le moteur et le modèle sélectionnés | Carte cohérente avec le sélecteur |
| Scrollbar | CSS global | static/v2.css :root et règles globales | Tableau overflow auto | Page et dialogue longs |
| Toast | toast() | static/app.js | Région status, succès bref | Retour après action |
| CRUD | API locale FastAPI | server.py et service.py | Import/lecture/révision ; pas de suppression | Persistance locale |
| Avis vision local | `llm_pairing.analyze_pair()` sur action explicite | `pairing-assist` et service Ollama loopback | Suggestion d’identité pour la paire sélectionnée; aucune mutation du run/verdict | Réponse structurée, abstention possible, vérification humaine |

## Flux

Bibliothèque → dossier → analyse → progression → révision → preuves → rapport → validation.
La revue ne change pas les conclusions machine : elle ajoute une décision humaine horodatée.
L’avis vision local reste éphémère et ne remplace jamais la décision de la personne réviseuse.
Un projet doit contenir des PDF de référence ET des PDF d’atelier pour être importé.
Fichiers invalides, protégés, trop gros ou trop nombreux : refus explicite. Pas d’écrasement.

## Requêtes asynchrones

Recherche après 300 ms, annulation de la précédente requête, filtres conservés lors de la
pagination. Pas de noms de projet ni de texte recherché dans les paramètres d’URL publics.
Le hash contient uniquement les identifiants de navigation locale. Une seule analyse GPU
à la fois dans le serveur. Arrêt après la page en cours ; cache conservé pour relancer.
Le redémarrage classe une tâche inachevée « interrompue ». Pas de succès silencieux.
Les pages en erreur ou sans OCR demandé restent comptabilisées dans la couverture.
Le projet affiche aussi le run actif et un lien vers sa progression, sans relancer le traitement.

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
La page Validation compare uniquement des exports d’analyses terminées du même projet et respecte l’ordre temporel. Elle ne certifie pas deux révisions PDF distinctes et n’affiche pas les empreintes des sources; celles-ci doivent être vérifiées. Ses appariements à 72 points restent des propositions; les observations non appariées ne signifient pas « manquant » ou « ajouté ». Le mapping PDF est un modèle vide de chemins et le script produit des copies dans un dossier sans sorties existantes. Les cercles marquent les coordonnées centrales exportées, sans contour détecté de l’objet. Les mesures de confiance restent descriptives jusqu’à l’adjudication indépendante.


Les handlers data-* de app.js sont délégués sur le document. Le contrôle statique affordance.actionless-button ne suit pas les gabarits HTML construits en JavaScript. Vérifier chaque contrôle dans la liste des handlers et dans le navigateur. Les styles calculés par l’interface passent par des classes et attributs data-* afin de respecter la CSP sans styles inline.
