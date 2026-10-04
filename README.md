# Concorde

**Concorde** est un outil local de révision de plans d’armatures. Il extrait les annotations depuis des PDF, propose des correspondances entre plans et dessins d’atelier, puis aide un réviseur à examiner les sources et les écarts. Il produit des exports JSON et des rapports PDF par feuillet.

Le projet est un prototype d’aide à la revue. Les résultats automatiques ne certifient pas la conformité d’un ouvrage; les décisions d’ingénierie restent humaines.

## Fonctionnalités

- Extraction du texte PDF natif et OCR local pour les pages numérisées.
- Détection OCR en tuiles pour traiter les grands dessins.
- Rapprochement explicable des éléments à partir de leur identité et du contexte du dessin, avant de comparer les valeurs d’armature.
- Abstention et revue visuelle lorsque plusieurs correspondances restent plausibles.
- Décisions humaines distinctes des propositions automatiques, avec justification et traçabilité.
- Suivi de couverture, coordonnées et liens vers les pages sources; exports JSON et PDF.
- Outils facultatifs d’adjudication, de comparaison de révisions et d’annotation PDF.
- Interface locale en français, notebook de démonstration et scripts Windows.

## Installation et démarrage (Windows)

Prérequis : Python 3.11. Pour CUDA, installer un pilote NVIDIA compatible avec CUDA 12.8. L’installation par défaut prépare CUDA et télécharge les dépendances et poids OCR nécessaires.

```powershell
.\install-concorde.ps1
.\start-concorde.ps1
```

Ouvrir <http://127.0.0.1:8766>. Arrêter le serveur avec :

```powershell
.\stop-concorde.ps1
```

Pour un poste sans GPU NVIDIA, installer le profil CPU avec `.install-concorde.ps1 -Device cpu`. Le notebook nécessite Jupyter, à installer séparément. Les scripts prennent en charge une installation hors ligne avec `-Wheelhouse` si les paquets et poids requis ont été préparés localement.

Les poids OCR peuvent aussi être préparés explicitement avec `scripts/download_l2c_models.py`. L’inférence ne télécharge pas de modèle à la volée. Les documents, poids, caches et exports sont exclus de Git.

## Utilisation

1. Importer les PDF du plan et des dessins d’atelier dans l’interface.
2. Choisir le profil complet pour un traitement détaillé. Le profil rapide est un aperçu et peut manquer des annotations.
3. Examiner les extractions, les pages sources et les correspondances candidates.
4. Confirmer, corriger ou laisser en suspens les décisions ambiguës.
5. Exporter les annotations et le rapport; consulter la couverture avant d’interpréter les résultats.

Les statuts automatiques décrivent les champs lisibles qui ont pu être comparés. Une absence d’extraction ou de correspondance ne prouve pas qu’un élément est absent du dessin. Les décisions « manquant » et « ajouté » exigent une vérification humaine explicite du périmètre et des sources.

## Traitement local et aide vision facultative

Le serveur écoute uniquement sur l’adresse locale (`127.0.0.1`) et ne fournit pas d’authentification. Ne pas l’exposer sur Internet. L’OCR, les imports et les exports s’exécutent localement; aucun document n’est envoyé à un service externe.

Une aide expérimentale peut interroger un modèle vision local via Ollama. Elle est désactivée par défaut, facultative et ne décide ni de l’identité finale ni du statut de conformité. Pour l’activer, installer Ollama séparément puis télécharger un modèle vision local, par exemple :

```powershell
ollama pull qwen3.5:4b
```

La mémoire nécessaire dépend du modèle, du runtime et des images traitées. Qwen3.5 est un modèle généraliste, pas un modèle spécialisé ou validé pour les plans d’armatures. Toute suggestion doit être contrôlée visuellement. Ollama n’est pas requis pour utiliser Concorde.

## Configuration

| Variable | Utilité |
|---|---|
| `L2C_DATA` | Dossier local des PDF source |
| `L2C_STORE` | Imports, caches et runs |
| `L2C_MODELS` | Poids locaux EasyOCR |
| `CONCORDE_PYTHON` | Interpréteur Python utilisé par les lanceurs |
| `CONCORDE_PORT` | Port local du serveur (8766 par défaut) |
| `CONCORDE_OLLAMA_URL` | URL locale Ollama (127.0.0.1 par défaut) |
| `CONCORDE_VLM_MODEL` | Modèle vision local configuré |

Un fichier local `local-settings.ps1` peut définir ces variables; il est ignoré par Git.

## Développement et tests

```powershell
.\.venv\Scripts\python.exe -m pip install pytest httpx
.\.venv\Scripts\python.exe -m pytest tests -q
```

Les tests utilisent des entrées synthétiques et ne nécessitent pas les plans du défi. Pour vérifier le flux local complet avec les poids installés, le script crée des PDF temporaires et passe par les routes d’import, les moteurs OCR, les exports et la reprise d’un run :

```powershell
.\.venv\Scripts\python.exe scripts/check_local_flow.py --models artifacts/l2c/models --output data/checks/flow-001.json
```

Les scripts d’audit, benchmark et adjudication sont décrits dans `docs/`. Les fichiers de référence et les étiquettes d’ingénieur doivent rester indépendants des données utilisées pour développer le système.

## Architecture

- `l2c_app/` : service FastAPI, extraction, OCR, appariement, révision, interface et rapports.
- `scripts/` : installation des modèles, contrôles de flux, audits et outils d’évaluation.
- `tests/` : tests unitaires et d’intégration sur données synthétiques.
- `notebooks/l2c_concorde.ipynb` : démonstration et inspection de runs locaux.
- `docs/` : protocoles, sémantique des rapports et limites de validation.

## Limites et interprétation

EasyOCR et RapidOCR sont des moteurs généralistes; ils ne sont pas entraînés pour certifier des détails de structure. Les identités spatiales et appariements restent heuristiques. Une validation du schéma, des coordonnées ou de la couverture confirme la structure et le traitement, pas l’exactitude sémantique. Aucune précision, aucun rappel global et aucun score officiel ne sont revendiqués sans références exhaustives annotées indépendamment par des ingénieurs.

PyMuPDF est distribué sous AGPL-3.0 ou licence commerciale; EasyOCR est sous Apache-2.0. Vérifier les licences applicables aux dépendances et aux poids avant toute redistribution. Aucun poids tiers ni document de projet n’est inclus dans ce dépôt.

## Documentation

- [Validation de l’appariement](docs/MATCHING-VALIDATION.md)
- [Audit des livrables](docs/DELIVERABLE-AUDIT.md)
- [Workflow d’adjudication](docs/ADJUDICATION-WORKFLOW.md)
- [Sémantique des rapports](docs/REPORT-SEMANTICS.md)
