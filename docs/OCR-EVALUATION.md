# Évaluation des composants OCR

La sélection doit reposer sur des entrées locales identiques, leurs empreintes, des versions figées et une transcription revue. Les sources, extraits, labels et runs restent dans les répertoires ignorés. Aucun chiffre officiel de conformité n’est revendiqué.

## Candidats examinés

- EasyOCR : CRAFT + CRNN Latin, code Apache-2.0, CUDA PyTorch. Les rotations choisies uniquement par confiance peuvent dégrader les textes horizontaux. Conserver les preuves de chaque lecture.
- RapidOCR 1.4.4 : PP-OCRv4 ONNX, moteur Apache-2.0 et modèles issus de PaddleOCR (Apache-2.0). ONNX Runtime GPU doit être activé explicitement pour détection, orientation et reconnaissance. Vérifier les providers réels et le journal de repli CPU. Les poids restent dans l’installation locale du paquet.
- eDOCr2 : code MIT, spécialisé en cotation mécanique et GD&T. Le reconnaisseur de dimensions a été exécuté isolément sur les mêmes crops avec TensorFlow/Keras. Cela ne représente pas tout le pipeline eDOCr2. Sous Windows cette configuration est CPU. Les poids nécessitent leur propre vérification de licence avant redistribution. Non intégré.
- OCRX : code MIT ; tester séparément les composants. Le prétraitement de suppression de lignes peut aussi supprimer des caractères. L’installateur modifie des réglages globaux : ne pas l’exécuter pour le benchmark. Aucun appel cloud ni moteur LaTeX n’est nécessaire au composant évalué.
- a0-drawing-ocr : code MIT, tuilage et rotations de RapidOCR. Son appel RapidOCR par défaut n’active pas explicitement CUDA ; le benchmark doit le déclarer CPU si c’est ce que montrent les sessions. Son point d’entrée traite la première page : itérer explicitement pour un document entier. Ne pas écrire de sorties à côté des originaux.
- OD-OCR-System-for-Engineering-Drawings : aucune licence explicite ni poids exploitables vérifiés lors de l’audit. Non installé/intégré. La dépendance Ultralytics a ses propres conditions AGPL/entreprise.

## Protocole

1. Figer le code de référence et les entrées ; conserver les erreurs d’installation/inférence.
2. Séparer par projet/feuillet, sans répartir des duplications entre les partitions.
3. Comparer les mêmes crops à 144 et 300 dpi. Reporter CER/WER, exactitude par champ et simultanée, effectifs et champs non annotés.
4. Figer les paramètres avant le projet réservé. Une vérité terrain annotée seulement par un agent reste provisoire.
5. Comparer aussi des pages entières : les crops seuls ne mesurent pas le rappel du détecteur, la segmentation ou l’appariement.
6. Rapporter chargement et inférence séparément, providers, VRAM partagée (elle inclut d’autres processus), CPU/GPU et erreurs. Un provider disponible n’est pas la preuve que chaque nœud du graphe tourne sur GPU.
7. Mesurer précision/rappel des écarts uniquement avec des paires exhaustivement adjudicées. Les tests synthétiques ne prouvent pas la performance sur des plans réels.

Le moteur alternatif demeure expérimental. Le texte natif reste prioritaire, le choix du moteur est enregistré dans le cache et les conclusions incertaines restent à réviser. Les résultats confidentiels ne sont pas publiés dans ce document.

## Sources primaires

- https://github.com/JaidedAI/EasyOCR
- https://github.com/RapidAI/RapidOCR
- https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE
- https://github.com/javvi51/edocr2
- https://github.com/aeewws/ocrx-engineering-drawings
- https://github.com/15724894976/a0-drawing-ocr
- https://github.com/tanhdz228/OD-OCR-System-for-Engineering-Drawings
- https://www.tensorflow.org/install/pip
- https://www.ultralytics.com/license
