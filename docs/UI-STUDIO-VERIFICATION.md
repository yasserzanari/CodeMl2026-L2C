# Refonte Concorde — vérification du 3 octobre 2026

La demande porte sur une refonte globale plus aboutie et sa vérification navigateur.
Le rendu partagé est défini dans `l2c_app/static/studio.css`, chargé après les bases
de `v2.css`. Les icônes sont des SVG locaux et les aperçus sont les documents réels.

## Vérifications effectuées

- Chrome, écran de bureau, 1280 × 900 et 390 × 844 ; dimensions restaurées ensuite.
- Projets : bibliothèque, dossier récent, ouverture de CLP.
- Documents : liste et aperçu PDF chargés.
- Révision : ouverture d’une observation, sources côte à côte, zoom synchronisé.
- Brouillon de note conservé pendant le zoom ; aucune décision enregistrée.
- Rapports : recherche S-600B, sélection « Aucun », sélection d’un seul feuillet,
  aperçu indépendant, recherche conservée pendant le changement d’aperçu.
- Export : réponse de préparation réussie et notification de lancement du téléchargement.
  Le premier observateur automatique de téléchargement a expiré ; le fichier sauvegardé
  par le navigateur n’a donc pas été certifié. Le retour applicatif a été revérifié
  après ajout de l’état occupé et du nettoyage différé de l’URL temporaire.
- Guide : les ancres conservent la route #guide.
- Réglages : présentation mobile ; aucun changement enregistré.
- Import : validation du nom obligatoire ; annulation sans création de dossier.
- À 390 px : largeur du document égale à sa largeur utile (380 px), sans débordement.
- Console navigateur : aucune erreur retournée pendant les parcours contrôlés.
- `node --check l2c_app/static/app.js` et `git diff --check` : réussis.
- Suite Python existante : 34 tests réussis, un avertissement de dépréciation Starlette.

## Limites

Pas de lancement d’analyse GPU ni de test d’arrêt d’un traitement en cours.
Le contrôle statique premium strict signale 19 boutons dont il ne détecte pas
les handlers délégués. Cette limite est documentée dans UX-CONTRACT.md ;
ce contrôle ne constitue pas un succès strict et ne remplace pas les essais navigateur.

Capture : `ui-studio/rapports.png`.

## Bureau de révision des plans

- Vue initiale sur les zones repérées, avec basculement vers les pages entières.
- Zoom lié : les deux sources passent à 125 % ; zoom indépendant : plan à 150 %,
  atelier maintenu à 125 %.
- Déplacement réel à la souris : scroll horizontal de 140 px et vertical de 100 px.
- « Adapter » remet le cadrage et le défilement à leur état initial.
- Mode agrandi : panneau de décision masqué puis réaffiché.
- Aller à l’observation suivante puis revenir : le brouillon de note est conservé.
  Le brouillon de test a été effacé et aucune décision n’a été enregistrée.
- À 390 × 844 : document de 380 px utiles, sans débordement horizontal ; panneaux empilés.
- Syntaxe JavaScript et vérification des espaces Git réussies.
- Capture : `ui-studio/revision-plans.png`.
