# Concorde — révision locale de plans

Dashboard français pour comparer les annotations d’armatures d’un plan de référence et des dessins d’atelier. Python, PDF natif, OCR préentraîné local sur CUDA, révision visuelle, exports JSON et PDF. Aucune intégration WhatsApp et aucune API IA distante.

## Installation Windows

Python 3.11 et pilote NVIDIA compatible CUDA 12.8 :

```powershell
.\install-concorde.ps1
.\start-concorde.ps1
```

Ouvrir http://127.0.0.1:8765. Arrêter avec `stop-concorde.ps1`. Les modèles sont téléchargés une seule fois par `scripts/download_l2c_models.py`, puis l’inférence interdit leur téléchargement automatique. Aucun document n’est inclus dans ce dépôt.

Importer deux groupes de PDF depuis l’interface, choisir le profil d’analyse, examiner les observations et télécharger les exports. Le profil aperçu limite l’OCR : il ne représente pas une analyse complète. Les décisions humaines restent distinctes des propositions automatiques.

## Configuration locale

Variables facultatives `L2C_DATA` (PDF), `L2C_STORE` (imports/cache/runs), `L2C_MODELS` (poids EasyOCR). Les chemins par défaut sont `data/l2c/raw`, `data/l2c/app`, `artifacts/l2c/models`. `CONCORDE_PYTHON` permet au lanceur d’utiliser un environnement Python déjà installé. Les fichiers `local-settings.ps1` sont ignorés et peuvent définir ces variables sur votre machine.

Les documents, extraits, résultats, captures et poids restent locaux et ignorés par Git. Ne jamais les ajouter avec `git add -f`. Le serveur écoute uniquement sur loopback, sans CDN. Il ne fournit pas d’authentification pour un déploiement public. Ne pas exposer son port sur Internet.

## Moteur et limites

CRAFT détecte le texte ; le CRNN Latin d’EasyOCR reconnaît les caractères. Ce sont des modèles OCR génériques, pas un modèle entraîné à certifier la conformité d’une structure. Le texte PDF natif est privilégié. Les grandes pages sont découpées en tuiles. CUDA est utilisé si disponible, avec réduction du lot en cas de mémoire insuffisante.

L’identité, le niveau et la famille sont rapprochés avant les valeurs d’armature. Les identités spatiales restent heuristiques. `non_conforme` désigne un écart candidat ; `conforme` un accord partiel sur les champs comparables ; `a_verifier` une abstention. Les éléments non appariés ne sont pas automatiquement déclarés manquants ou ajoutés. Les groupes de fabrication et lectures incertaines restent à réviser. La couverture est indiquée explicitement.

Les coordonnées sont les centres des annotations en points PDF, origine supérieure gauche, dans la page affichée après rotation. Une transformation inverse permet de surligner les sources sans modifier les originaux.

Aucun score officiel ni précision de conformité n’est revendiqué. Les mesures OCR sur de petits extraits ne prouvent pas la qualité de l’appariement. Le benchmark local conserve les échecs et distingue validation, confirmation, CPU et GPU.

## Développement et contrôles

```powershell
.\.venv\Scripts\python.exe -m pip install pytest httpx
.\.venv\Scripts\python.exe -m pytest tests -q
```

Les tests utilisent uniquement des textes et PDF synthétiques. Le script `scripts/l2c_benchmark_worker.py` attend un manifeste local non fourni ; il ne contient aucun résultat client. Le socket Python est bloqué durant ses inférences, mais ce contrôle n’est pas un pare-feu système.

## Dépendances

Versions : `l2c_app/requirements.txt` et `install-concorde.ps1`. EasyOCR est Apache-2.0 ; PyMuPDF est AGPL-3.0 ou commercial ; PyTorch utilise sa licence BSD. Vérifier les obligations des dépendances et des poids avant redistribution. Aucun poids tiers n’est publié ici. Le code a été développé avec l’assistance de Codex.
