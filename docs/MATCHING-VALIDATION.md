# Contrat de validation de l’appariement

## Décisions observables

L’extraction répond à « quel texte/attribut et où ? ». L’appariement répond à « est-ce le même élément, au même niveau et dans le même rôle ? ». La comparaison ne commence qu’ensuite. La désignation, la quantité ou l’espacement attendus ne doivent jamais servir à choisir le candidat qui semble conforme.

| Critère du défi | Points | Observation mesurable |
|---|---:|---|
| Détection | 30 | TP/FN/FP sur des non-conformités et paires adjudicées ; rappel prioritaire, pondération exacte inconnue |
| Extraction / JSON | 20 | Complétude, exactitude des champs, coordonnées, schéma |
| Rapport | 15 | Résumé par feuillet, écart explicite, source retrouvable |
| Technique | 15 | Reproduction, architecture et contrôles |
| Généralisation | 10 | Projet non vu et cinq familles |
| Démonstration | 10 | Exécution et limites présentées clairement |

Aucune formule officielle n’est inventée. L’exigence de modèle entraîné/affiné ne s’applique que lorsqu’un tel entraînement a été effectué. Les documents et dérivés restent locaux ; aucun nouveau moteur ou service cloud n’est intégré par ce travail.

## Règles de l’assistant de révision

- Normaliser uniquement les séparateurs non ambigus de repères et les variantes explicites de niveaux.
- Préserver les axes décimaux et ne pas supposer un niveau absent.
- Rejeter les conflits explicites de famille, niveau, rôle et position haut/bas.
- Garder les candidats multiples visibles ; aucune suppression basée seulement sur l’égalité des armatures.
- Classer par indices de contexte disponibles, jamais par accord des valeurs.
- Montrer séparément les écarts conditionnels, les champs inconnus et l’incertitude d’identité.
- Ne pas déduire manquant/ajouté sur un périmètre incomplet.
- Le comparateur historique utilise 0,5 mm de tolérance informatique : cette valeur n’est pas une tolérance d’ingénierie fournie par le défi. L’aide expérimentale affiche toute différence supérieure au bruit numérique (1e-6), sans l’approuver techniquement. Les conversions d’unité ont lieu au parsing, les quantités restent exactes.

## Protocole et limites

Les runs d’entrée et le tableur de référence sont identifiés par SHA-256 et conservés. La nouvelle aide ne réexécute pas l’OCR et ne modifie pas les conclusions historiques. Les contrôles synthétiques vérifient alias, conflits, inconnues, multiplicité et indépendance des valeurs dans le classement. Les mesures réelles de couverture sont descriptives : des candidats nombreux ne prouvent pas un gain de rappel.

Un tableau d’anomalies partielles ne contient pas les vrais négatifs. Une ligne dont les deux valeurs sont identiques ne peut être comptée comme une non-conformité sans clarification. Une notation non interprétable reste exclue avec justification. Les omissions par repère exact doivent être distinguées de l’extraction absente et d’une mauvaise localisation.

La matrice complète des faux appariements, vrais négatifs et doublons physiques exige une annotation indépendante. Tant qu’elle manque, ces cellules restent « non mesurées », jamais zéro. Les données de développement ou déjà examinées ne permettent pas de revendiquer une confirmation indépendante. Les profils natifs/aperçu ne couvrent pas toutes les annotations d’atelier.

## Décision de mise en service

Le gain de précision/rappel d’appariement n’est pas démontré. Le défaut reste inchangé. L’assistant est un outil de revue facultatif ; les décisions humaines sont conservées séparément. La prochaine preuve requise est un jeu de paires avec niveaux, régions sources, révisions et statut adjudiqués, puis une évaluation sur un projet réellement indépendant.
