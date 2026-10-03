# Sémantique du rapport L2C / Concorde

## But

Le rapport PDF est une synthèse de révision des observations produites par le pipeline.
Il expose les preuves extraites et leur couverture connue; il ne certifie pas la conformité
d'un élément ni l'exhaustivité de la lecture d'un dessin.

## Propositions machine et décisions humaines

Les statuts `conforme`, `non_conforme` et `a_verifier` décrivent les propositions émises
par la machine. Dans le rapport, ils sont libellés **accord partiel**, **écart candidat**
et **à vérifier**. Un accord partiel ne porte que sur les champs lisibles communs. Un écart
reste à confirmer sur les plans. Le rapport compte séparément les décisions humaines
`confirme`, `rejete` et `a_verifier` (présentées comme confirmée, rejetée et à reprendre).
Une revue ne réécrit pas le statut machine : les deux informations répondent à des
questions différentes et restent traçables dans `comparaisons.json`.

## Catégories officielles d'absence et d'ajout

Le défi demande les catégories « manquant dans l'atelier » et « ajouté dans l'atelier ».
Le schéma actuel des résultats ne les représente pas. Le rapport ne crée donc pas ces
statuts et les décrit comme **non établis par cette analyse**. Une annotation sans paire,
une page sans extraction, un échec ou une couverture partielle ne prouve ni un manque ni
un ajout. Toute future attribution de ces catégories demande une population de référence
complète et une validation explicite, et ne doit pas être déduite d'un simple non-match.

## Couverture par feuillet

Les pages de plan sont regroupées par feuillet à partir des métadonnées de traitement.
Pour chaque feuillet, le rapport affiche le nombre de pages traitées et les pages en échec,
ignorées ou sans état connu, puis le nombre de propositions machine et le nombre de revues
humaines. Un feuillet sans résultats demeure visible s'il apparaît dans les métadonnées de
page. Si aucune métadonnée exploitable n'existe, sa couverture apparaît comme inconnue.
Un état traité indique que le pipeline a parcouru la page; il ne garantit pas que toutes
les annotations ont été détectées. Les métriques globales sont conservées depuis les
statistiques du run; les états par page restent consultables dans `comparaisons.json`.

Les résultats qui n'ont pas d'annotation liée au plan sont regroupés sous « Atelier · sans
plan associé » et ne sont pas attribués arbitrairement à un feuillet de plan. Les exports
JSON demeurent la source détaillée pour les coordonnées, les raisons et les pages sources.

## Sources et limites

Le résumé donne, par rôle, le nombre de fichiers et de pages consignés, puis rappelle les
trois sorties générées : rapport PDF, annotations JSON et comparaisons JSON. Les nombres de
pages sont des décomptes de métadonnées du run; une entrée absente signifie « inconnue » et
non zéro. Les scores OCR n'expriment pas une probabilité de conformité.

L'objectif est un rapport concis, lisible pour la révision et honnête sur les preuves. Les
cas « manquant » et « ajouté » restent explicitement non établis tant que le pipeline ne
dispose pas d'une couverture complète et d'une vérité terrain validée permettant de les
mesurer sans confondre absence d'extraction et absence réelle.
