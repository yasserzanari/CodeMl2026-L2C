---
version: alpha
name: Concorde
description: Bureau de révision local pour les plans de structure et les dessins d’atelier.
colors:
  primary: "#2060df"
  foreground: "#183247"
  muted: "#647789"
  background: "#f0f4f7"
  surface: "#ffffff"
  navigation: "#142e42"
  border: "#dce5ec"
  success: "#14765a"
  warning: "#9a5a13"
  danger: "#bb3939"
typography:
  sans:
    fontFamily: "Segoe UI, Arial, sans-serif"
  display:
    fontFamily: "Bahnschrift, Segoe UI, sans-serif"
  mono:
    fontFamily: "Consolas, monospace"
rounded:
  DEFAULT: "12px"
  control: "7px"
  dialog: "16px"
spacing:
  section-gap: "24px"
  page-max: "1720px"
components:
  button: {}
  card: {}
  table: {}
  dialog: {}
  field: {}
---

# Concorde : système visuel

## Intention

Un bureau d’ingénierie clair, calme et précis. La preuve documentaire demeure au centre.
Interface française canadienne, desktop en priorité, utilisable sur mobile. Aucun service externe,
police distante, CDN ou traceur. Les vignettes proviennent des vrais PDF locaux.

## Source des tokens

`static/v2.css :root` implémente les couleurs, familles, rayon et états partagés de l’interface Concorde.
Ce fichier et `UX-CONTRACT.md` constituent la source des décisions de conception.
Les couleurs secondaires servent exclusivement à distinguer plan, atelier et état.

## Composition

Navigation navy permanente de 244 px, barre de contexte, contenu sur fond ardoise pâle.
En-tête concis, puis zone de comparaison dessinée, compteurs réels et bibliothèque.
Dossier récent illustré par son plan réel, compteurs compacts et bibliothèque en lignes.
La révision utilise un tableau paginé et une page dédiée avec les preuves côte à côte.
À 850 px, navigation compacte ; à 550 px, navigation supérieure et colonnes empilées.

## Typographie et hiérarchie

Bahnschrift pour les titres, Segoe UI pour les contrôles/prose, Consolas pour références
et chiffres techniques. Corps 14 px / 1.5 ; prose secondaire 12 px. Aucun texte de plan
recomposé en image. Les sources sont consultables en PDF à leur taille d’origine.

## Composants et états

Bouton primaire bleu réservé à l’action principale. Secondaire blanc bordé, liens tertiaires
explicites. Focus visible bleu 3 px, état désactivé natif, état occupé pendant les requêtes.
Cartes et tables structurées par des bordures fines ; pas d’ombre décorative excessive.
Ombre réservée aux dialogues, retours ponctuels et survol léger des dossiers.
Badges avec texte pour que la couleur ne soit jamais le seul indicateur.

## Interaction et accessibilité

Dialogues HTML natifs avec titre, fermeture explicite et navigation clavier.
Champs nommés, recherche effaçable, messages d’erreur près du formulaire, notifications
en région live. Réduction des mouvements selon la préférence système. Les tableaux
débordent horizontalement sur petit écran sans bloquer les formulaires.
Les sélecteurs sont natifs : choix fini, comportement clavier familier, aucun composant
supplémentaire nécessaire. Le redimensionnement vertical du commentaire est intentionnel
pour les longues notes de révision.

## Contenu

« Écart candidat », « Accord partiel » et « À vérifier » décrivent exactement ce que fait le
moteur. Jamais de compteur factice, score inventé ou promesse de conformité générale.
La couverture de lecture et la validation des armatures sont deux informations distinctes.

## Mouvement

Transitions de survol 150 ms, aucune animation décorative persistante. Une barre de
progression est alimentée par les pages réellement parcourues ; aucune durée prédite.

## Refonte du bureau de révision — octobre 2026

Le besoin explicite de refonte autorise cette nouvelle identité : navigation profonde,
surfaces claires et plans réels comme signature visuelle. Les icônes SVG sont locales.
Le modèle B de tokens reste canonique : v2.css définit les variables partagées
et les composants consomment ces variables. Les classes de zoom et de progression
font partie du même fichier afin que les états chargés restent cohérents.
Aucun style calculé inline. Le turquoise identifie le plan et le cuivre le dessin d’atelier.

Rapports : panneau de sélection à gauche, aperçu papier à droite. Le bouton de feuillet
ouvre son aperçu ; la case à cocher ne modifie que la sélection d’export. Recherche et
sélection persistent pendant la consultation. La navigation entre écrans revient en haut.
Aux largeurs 900 et 680 px, la navigation se compacte puis les panneaux se superposent.

## Bureau de révision des plans

La route de détail compacte la navigation à 82 px et conserve deux lecteurs côte à côte.
Le cadrage initial affiche les zones repérées à partir des coordonnées réelles du moteur.
Un contrôle commun permet de retrouver les pages entières. Les lecteurs ont chacun
un zoom et un défilement ; les zooms peuvent être liés. « Adapter » ajuste la source
aux dimensions disponibles. Le déplacement à la souris complète le défilement natif.
Le panneau de décision se masque explicitement pour agrandir les sources. Les notes
non enregistrées restent en mémoire par analyse et observation pendant la session.
