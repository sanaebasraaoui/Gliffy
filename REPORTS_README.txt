================================================================================
GUIDE DES RAPPORTS - TOUS LES FICHIERS DANS reports/
================================================================================

Tous les rapports générés par l'application sont maintenant sauvegardés en 
format texte (.txt) dans le dossier 'reports/' pour une lecture facile.

================================================================================
DOSSIER reports/
================================================================================

Le dossier 'reports/' est créé automatiquement lors de la première génération
d'un rapport. Tous les fichiers de rapport y sont centralisés.

================================================================================
FICHIERS GÉNÉRÉS
================================================================================

1. gliffy_pages.txt
   - Généré par: find_gliffy_pages.py ou via le scan
   - Contenu: Liste de toutes les pages Confluence contenant des diagrammes Gliffy
   - Format: Texte lisible avec détails par page (titre, ID, espace, URL, etc.)

2. migration_report.txt
   - Généré par: gliffy_migrator.py (commande 'migrate')
   - Contenu: Rapport détaillé de la migration des images Gliffy
   - Format: Statistiques globales + détails par page (statut, erreurs, etc.)

3. tids_mapping.txt
   - Généré par: extract_tids.py
   - Contenu: Liste de tous les TID (Type ID) trouvés dans les fichiers Gliffy
   - Format: Liste triée par fréquence avec occurrences et chemins d'images

4. confluence_inventory.txt
   - Généré par: confluence_scanner.py (commande 'scan')
   - Contenu: Inventaire complet de toutes les pages Confluence
   - Format: Pages groupées par espace avec métadonnées détaillées

5. info_espace_*.txt
   - Généré par: download_gliffy.py
   - Contenu: Informations détaillées sur chaque espace avec ses pages Gliffy
   - Format: Un fichier par espace avec liste des diagrammes et leurs métadonnées

================================================================================
FORMAT DES FICHIERS
================================================================================

Tous les fichiers .txt sont formatés de manière lisible pour les humains avec:
- En-têtes clairs avec séparateurs
- Informations structurées et indentées
- Dates et statistiques en haut de fichier
- Détails organisés par section

Les fichiers JSON originaux sont toujours générés pour compatibilité avec
d'autres outils, mais les versions .txt sont recommandées pour la lecture.

================================================================================
UTILISATION
================================================================================

Les fichiers .txt sont générés automatiquement lors de l'exécution des scripts.
Aucune action supplémentaire n'est nécessaire.

Exemples:
- python find_gliffy_pages.py → génère reports/gliffy_pages.txt
- python cli.py migrate → génère reports/migration_report.txt
- python extract_tids.py → génère reports/tids_mapping.txt
- python cli.py scan → génère reports/confluence_inventory.txt

================================================================================

