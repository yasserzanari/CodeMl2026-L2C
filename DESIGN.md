# Concorde — contexte de conception

## Produit et usage

Concorde est un poste de révision locale destiné aux ingénieurs et réviseurs qui comparent des plans de structure aux dessins d’atelier. La tâche principale est d’inspecter deux sources, de comprendre pourquoi une comparaison est proposée, puis d’enregistrer une décision humaine traçable.

## Direction visuelle

- **Palette (tokens existants) :** encre `#182C40`, texte secondaire `#60748A`, surfaces `#FFFFFF` et `#F5F7FA`, bleu `#305BE8`, turquoise `#178CA4`, ambre `#BD731B`, rouge `#B7464E`, vert `#187C68`.
- **Typographie :** sans-serif système pour l’interface et les consignes; chiffres tabulaires et monospace pour coordonnées, identifiants, scores bruts et métadonnées de provenance.
- **Disposition :** outils denses mais calmes; deux plans visibles côte à côte sur grand écran, empilés sur petit écran. Les sources et leur provenance restent lisibles sans masquer l’état de décision.
- **Élément signature :** les panneaux plan/atelier ont des accents turquoise/ambre distincts, comme deux calques techniques qui restent comparables sans être confondus.

## Règles d’interface

- Les statuts automatiques sont des propositions; les décisions humaines restent distinctes et portent auteur, date et preuve.
- Les coordonnées et les liens doivent conduire à la source correspondante. Une page lue ne garantit pas une détection exhaustive.
- Un score OCR brut ne s’appelle pas « probabilité de conformité » et ne devient pas un score métier avant calibration indépendante.
- Une absence de rapprochement n’est jamais présentée comme un élément manquant ou ajouté.
- Les exports sont locaux, accessibles au clavier, et leur état de chargement/erreur est explicite.
- Toute nouvelle fonction reste dans le style de navigation, des cartes, des champs et des notifications décrit dans [UX-CONTRACT](l2c_app/UX-CONTRACT.md).

## Accessibilité et adaptation

Les contrôles utilisent des boutons, liens, labels et messages de statut sémantiques. Le contraste, le focus clavier, le mouvement réduit et les vues étroites sont conservés. Les noms de documents et les valeurs longues restent consultables même quand ils sont tronqués visuellement.
