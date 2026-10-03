---
version: alpha
name: Concorde
description: Bureau de révision local pour les plans de structure et les dessins d’atelier.
colors:
  primary: "#2463dc"
  foreground: "#172d3b"
  muted: "#607383"
  background: "#f3f6f9"
  surface: "#ffffff"
  navigation: "#142a39"
  border: "#dce4eb"
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

`static/styles.css :root` implémente les couleurs, familles, rayon et états partagés.
Ce fichier et `UX-CONTRACT.md` constituent la source des décisions de conception.
Les couleurs secondaires servent exclusivement à distinguer plan, atelier et état.

## Composition

Navigation navy permanente de 236 px, barre de contexte, contenu sur fond ardoise pâle.
En-tête concis, puis zone de comparaison dessinée, compteurs réels et bibliothèque.
Cartes de dossiers à deux colonnes, chaque carte avec une vignette et une action claire.
La révision utilise un tableau paginé et une boîte de dialogue avec les preuves côte à côte.
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
