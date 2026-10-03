# Plan d’exécution L2C — Concorde

Date : 3 octobre 2026

## Objectif

Livrer un outil local reproductible qui prend les PDF d’un projet, extrait les annotations d’armature avec leur provenance, propose des rapprochements explicables, produit les JSON et un rapport PDF par feuillet, puis permet à un ingénieur de vérifier les conclusions. Les quatre projets fournis servent au développement; le cinquième projet du jury reste le seul contexte prévu pour la démonstration finale indépendante.

Les documents, extraits, caches, labels et rapports réels restent sur la machine et dans les répertoires locaux ignorés par Git. Aucun contenu réel du défi ne doit être ajouté au dépôt ou transmis à un service externe.

## État initial observé

- Application locale, extraction texte/OCR, JSON/PDF, notebook, moteur de rapprochement conservateur et aide expérimentale existent.
- RapidOCR est le moteur actuellement retenu dans les réglages; les résultats disponibles sont exploratoires et ne mesurent pas la conformité structurelle.
- Des exports existent pour les quatre projets, mais seuls les runs CLP recensés couvrent le projet complet. EspCa3B, LIGREP et WP2 ont des profils partiels/natifs. Ils ne satisfont donc pas encore le livrable d’exports complets pour chaque projet.
- Les comparaisons de référence ne forment pas une vérité terrain exhaustive. Les paires, faux appariements et vrais négatifs n’ont pas été adjudiqués de façon suffisante pour annoncer précision/rappel.
- Le cinquième projet n’est pas disponible localement. Une performance sur ce projet ne peut pas être vérifiée à ce stade.
- Le dépôt contient des changements locaux non commités. Ils doivent être examinés et intégrés sans écraser le travail existant.

## Chantiers parallèles

### A. Préparer l’adjudication humaine — agent `adjudication_workflow`

- Générer depuis des runs locaux un paquet de revue stable qui montre chaque source et garde suggestions automatiques et champs humains séparés.
- Capturer identité positive/négative/incertaine, champs d’écart, auteur et provenance des entrées.
- Verrouiller hashes des runs et règles de partition par projet/document; aucun split aléatoire de pages liées.
- Remettre un guide d’utilisation et de validation des labels.

**Sortie attendue :** script et protocole prêts; les décisions techniques restent à remplir par un réviseur humain.

### B. Auditer les livrables — agent `deliverable_audit`

- Comparer le catalogue local, les runs, leur portée et leurs JSON/PDF exportés.
- Signaler par projet les pages/runs manquants, les erreurs et les sorties partielles.
- Produire un résumé JSON/CLI et un statut bloquant quand les quatre projets n’ont pas les exports attendus.
- Ne pas présenter couverture ou nombre d’alertes comme une mesure d’exactitude.

**Sortie attendue :** outil réexécutable avant remise, qui détecte les trous de couverture.

### C. Rendre le rapport fidèle aux preuves — agent `report_semantics`

- Séparer décomptes automatiques et décisions humaines.
- Afficher clairement pages traitées, pages en erreur/ignorées, périmètre et incertitudes par feuillet.
- Ne pas inférer « manquant » ou « ajouté » depuis une simple absence de rapprochement.
- Préserver les mentions « écart candidat » et « accord partiel » plutôt que de certifier l’ingénierie.

**Sortie attendue :** sémantique de rapport documentée et PDF informatif même lorsque la couverture est partielle.

## Plan séquentiel et portes de sortie

### 0. Stabiliser le code existant — responsable : intégration

1. Relire les modifications déjà présentes dans le dépôt, préserver celles qui sont utiles et résoudre incohérences entre code, interface et documentation.
2. Intégrer séparément les trois contributions parallèles; inspecter chaque diff avant fusion.
3. Faire un contrôle non destructif de configuration, des dépendances, du stockage local et des sorties attendues.

**Porte :** aucun changement parallèle ne touche les mêmes fichiers; aucune donnée réelle n’est suivie par Git.

### 1. Constituer une vérité terrain utile — responsable : ingénieur/réviseur; outil fourni par le chantier A

1. Faire adjudiquer les quatre cas de référence interprétables et documenter les deux cas ambigus au lieu de leur assigner une classe forcée.
2. Ajouter des exemples vérifiés de conformités, non-conformités, non-correspondances et lectures incertaines, sur plusieurs familles et les deux côtés des dessins.
3. Revoir les identités, niveaux, coordonnées/rectangles source, repères et attributs; conserver qui a pris chaque décision et sa justification.
4. Conserver les splits au niveau projet ou document. Aucun extrait, tuile, révision ou page d’un même dessin ne doit passer du développement au holdout.

**Porte :** labels traçables et indépendants; les désaccords sont conservés/résolus et les unités de comptage sont spécifiées. Sans cette porte, seuls des taux de couverture descriptifs sont autorisés.

### 2. Corriger l’appariement et les cas métier — responsable : intégration + réviseur

1. Utiliser les paquets adjudiqués pour réparer le lien entre repères, tableaux, élévations, flèches et éléments.
2. Mesurer séparément extraction, localisation, identité, comparaison des attributs et décision finale.
3. Prioriser le nombre de barres; comparer diamètre, espacement et longueur lorsqu’ils sont présents et interprétables.
4. Maintenir l’abstention pour une lecture ou une identité incertaine. Les statuts « manquant/ajouté » nécessitent une couverture de recherche suffisante et une règle métier confirmée.
5. Garder un journal des erreurs et des modifications; ne pas régler puis annoncer les scores sur les mêmes cas.

**Porte :** protocole de comparaison fixé avant calcul; résultats présentés par projet/famille avec erreurs et cas non mesurés.

### 3. Couvrir les quatre projets connus — responsable : opérateur local

1. Lancer des runs complets, en conservant chaque run échoué, les versions de moteurs, réglages, hashes d’entrée, statut CPU/GPU et durées.
2. Contrôler que toutes les pages sont comptées, que les pages en échec/ignorées sont visibles et que les coordonnées respectent l’annexe A.
3. Produire et valider le JSON et le rapport PDF par projet; comparer la couverture réelle au catalogue.
4. Garder les sorties réelles dans le dossier local ignoré; ne publier que des exemples synthétiques.

**Porte :** quatre projets ont des exports complets ou une liste explicite, revue, de leurs exceptions. Une exécution complète ne signifie pas que son contenu est exact.

### 4. Préparer la démo et la remise — responsable : intégration

1. Vérifier README, installation, point d’entrée, dépendances, notebook de pipeline de bout en bout et limites connues.
2. Vérifier l’exécution locale sans réseau avec les poids déjà installés et le comportement CPU si le GPU est absent.
3. Répéter le parcours de dix minutes; montrer les preuves sources, les incertitudes, la couverture et le temps froid/cache.
4. Confirmer avec l’organisateur le canal privé des sorties contenant des documents confidentiels et le processus de suppression à la fin du hackathon.
5. Ne traiter le cinquième projet qu’au moment de l’évaluation, sans l’utiliser pour le réglage préalable.

**Porte :** démonstration répétée et remise accessible au jury, sans exposer les documents publiquement.

## Mesures à fixer avant l’évaluation

- **Détection :** rappel et précision des non-conformités adjudiquées; le rappel est plus pondéré par les consignes, mais aucune formule officielle détaillée n’est fournie.
- **Extraction/JSON :** couverture des annotations, exactitude des champs, conformité au schéma et exactitude des coordonnées en points PDF depuis le coin haut-gauche.
- **Appariement :** précision des identités, ambiguïtés et faux appariements, séparés des différences d’armature.
- **Rapport :** écarts retrouvables dans les deux sources, couverture des feuillets, erreurs et cas incertains.
- **Généralisation :** projet/document retenu hors réglage, et cinq familles représentées; les quatre projets connus ont déjà été explorés, donc aucun ne doit être présenté comme holdout totalement vierge.

Ne pas inventer de seuil de réussite, tolérance d’ingénierie ou formule de score. Clarifier les unités de comptage et le traitement des substitutions/« manquant/ajouté » auprès de L2C; tant que la réponse manque, documenter l’hypothèse et garder les verdicts concernés à vérifier.

## Limites non automatisables par ce chantier

- L’assistant ne peut pas créer une vérité terrain d’ingénieur à partir de ses propres suggestions.
- Aucun score final de détection sur le projet du jury ne peut être calculé avant l’accès à ce projet.
- La présence de JSON/PDF et la réussite d’un parcours synthétique ne prouvent pas la complétude ou l’exactitude sur des plans réels.
- Les contrôles de livraison prouvent la couverture des fichiers traités, pas la conformité structurale.

## État de suivi

- [x] Audit initial des consignes officielles et du dépôt.
- [x] A — paquet d’adjudication et protocole local prêts; les labels d’ingénieur restent à créer.
- [x] B — audit automatique de complétude de remise ajouté; il n’a pas encore été exécuté.
- [x] C — rapport séparant propositions machine, décisions humaines et couverture ajouté.
- [ ] Intégration et revue complète des changements locaux déjà présents; contributions revues sans relancer de tests.
- [ ] Adjudication indépendante des paires réelles.
- [ ] Correction puis évaluation contrôlée de l’appariement.
- [ ] Runs complets des quatre projets et exports finaux.
- [ ] Préparation et répétition de la démo/remise.
