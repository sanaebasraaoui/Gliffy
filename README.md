# Application Gliffy - Gestion et conversion de diagrammes Gliffy

Application en ligne de commande pour gérer les diagrammes Gliffy dans Confluence et les convertir vers Excalidraw.

## 📋 Vue d'ensemble

Cette application expose **trois fonctionnalités distinctes** via une interface CLI :

1. **Scan global de Confluence** - Crée un inventaire complet de toutes les pages
2. **Migration des images Gliffy** - Copie les images Gliffy sous les diagrammes (idempotent)
3. **Conversion Gliffy → Excalidraw** - Interface web pour convertir des fichiers

## 🚀 Installation

### Prérequis

- Python 3.8 ou supérieur
- Un compte Confluence avec accès API

### Installation des dépendances

```bash
pip install -r requirements.txt
```

Les dépendances incluent :
- `requests` - Pour les appels API Confluence
- `beautifulsoup4` et `lxml` - Pour le parsing HTML
- `flask` et `werkzeug` - Pour l'interface web
- `Pillow` - Pour la compression automatique des images

### Vérifier l'installation

```bash
python3 -c "import requests, flask; print('✅ Installation réussie')"
```

## ⚙️ Configuration

### Créer un token API Confluence

1. Connectez-vous à votre instance Confluence
2. Allez dans **Account Settings** → **Security** → **API tokens**
3. Cliquez sur **Create API token**
4. Copiez le token généré (vous en aurez besoin pour toutes les commandes)

## 📖 Utilisation

### 1️⃣ Scan global de Confluence (inventaire)

Crée un fichier d'inventaire donnant une vision globale du contenu Confluence.

#### Commande de base

```bash
python cli.py scan \
  --url https://votre-confluence.atlassian.net/wiki \
  --username votre_email@example.com \
  --token VOTRE_TOKEN_API
```

#### Options disponibles

- `--spaces ESPACE1 ESPACE2` : Scanner uniquement certains espaces
- `--page PAGE_ID` : Scanner une page spécifique
- `--format txt|json` : Format d'export (défaut: `txt` dans `reports/`)
- `--output FICHIER` : Nom du fichier de sortie sans extension (défaut: `confluence_inventory`)

#### Exemples

```bash
# Scanner tout Confluence et exporter en TXT (dans reports/)
python cli.py scan \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --format txt \
  --output confluence_inventory

# Scanner un espace spécifique
python cli.py scan \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --spaces DEV PROD

# Scanner une page spécifique
python cli.py scan \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --page 123456
```

#### Métadonnées collectées

Pour chaque page, l'inventaire contient :
- **ID de la page**
- **Titre** (nom)
- **Domaine / space** (clé et nom)
- **Statut** (current, draft, etc.)
- **Version**
- **Date de création** et auteur
- **Date de mise à jour** et auteur
- **Page parent** (ID et titre)
- **Nombre d'ancêtres** (profondeur dans la hiérarchie)
- **URL** de la page

---

### 2️⃣ Migration des images Gliffy dans les pages Confluence

Copie les images Gliffy (pièces jointes) directement sous le diagramme Gliffy dans la page Confluence correspondante.

**⚠️ Important** : Cette commande est **idempotente** - une page déjà traitée ne sera jamais modifiée une seconde fois. Vous pouvez relancer la commande sans risque.

#### Commande de base

```bash
python cli.py migrate \
  --url https://votre-confluence.atlassian.net/wiki \
  --username votre_email@example.com \
  --token VOTRE_TOKEN_API
```

#### Options disponibles

- `--spaces ESPACE1 ESPACE2` : Traiter uniquement certains espaces
- `--page PAGE_ID` : Traiter une page spécifique
- `--report FICHIER` : Fichier de rapport de migration (défaut: `migration_report.json`)

#### Exemples

```bash
# Migrer les images Gliffy dans tous les espaces
python cli.py migrate \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --report migration_report.json

# Migrer les images Gliffy dans un espace spécifique
python cli.py migrate \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --spaces DEV \
  --report migration_report.json

# Migrer les images Gliffy dans une page spécifique
python cli.py migrate \
  --url https://confluence.example.com \
  --username user@example.com \
  --token TOKEN \
  --page 123456
```

#### Fonctionnement

1. **Détection** : La commande identifie toutes les macros Gliffy dans les pages
2. **Téléchargement** : Pour chaque Gliffy, télécharge l'image PNG/SVG depuis les attachments
3. **Compression automatique** : Si l'image dépasse ~3.7 MB, elle est automatiquement compressée pour respecter la limite de 5 MB de Confluence
4. **Vérification d'idempotence** : Vérifie si l'image a déjà été insérée (pour éviter les doublons)
5. **Insertion** : Insère l'image juste sous le diagramme Gliffy avec le titre du diagramme
6. **Rapport** : Génère un rapport détaillé listant toutes les pages modifiées

#### Format de l'image insérée

L'image est insérée avec le format suivant :
```html
<p><strong>📊 Diagramme Gliffy exporté: [Nom du diagramme]</strong><br/>
<img src="data:image/png;base64,..." alt="..." title="..." /></p>
```

#### Compression automatique des images

**Fonctionnalité automatique** : Si une image dépasse ~3.7 MB, elle est automatiquement compressée pour respecter la limite de 5 MB de Confluence.

- ✅ Compression intelligente : Réduction de taille et optimisation de qualité
- ✅ Préservation de la qualité : Minimum 200px pour maintenir la lisibilité
- ✅ Double vérification : Si la requête totale dépasse 5 MB, compression supplémentaire
- ✅ Formats supportés : PNG et JPEG
- ✅ Transparent : Fonctionne automatiquement sans intervention

Si l'image est encore trop grande après compression, un message d'erreur détaillé indiquera la taille et suggérera de réduire le diagramme dans l'éditeur Gliffy.

#### Rapport de migration

Les rapports sont générés en deux formats :
- **JSON** : Format structuré pour traitement automatique (dans le répertoire courant)
- **TXT** : Format lisible pour les humains (dans `reports/` avec horodatage)

Le rapport contient :
- **Timestamp** de la migration
- **Statistiques globales** (pages traitées, modifiées, ignorées, etc.)
- **Détails par page** :
  - ID et titre de la page
  - Statut (modified, skipped, error)
  - Nombre de Gliffy trouvés
  - Nombre d'images insérées
  - Erreurs détaillées avec messages explicites (permissions, taille, etc.)

---

### 3️⃣ Conversion Gliffy → Excalidraw via interface web

Lance une interface web permettant d'uploader un fichier `.gliffy` et de télécharger le fichier `.excalidraw` généré.

#### Commande de base

```bash
python cli.py web
```

#### Options disponibles

- `--host ADRESSE` : Adresse IP du serveur (défaut: `127.0.0.1`)
- `--port PORT` : Port du serveur (défaut: `5000`)
- `--debug` : Mode debug

#### Exemples

```bash
# Lancer le serveur sur le port par défaut (127.0.0.1:5000)
python cli.py web

# Lancer le serveur sur toutes les interfaces réseau
python cli.py web --host 0.0.0.0 --port 8080

# Mode debug
python cli.py web --debug
```

#### Utilisation de l'interface web

1. Lancez la commande `python cli.py web`
2. Ouvrez votre navigateur et accédez à `http://localhost:5000`
3. Cliquez ou glissez-déposez votre fichier `.gliffy`
4. Cliquez sur "Convertir"
5. Téléchargez le fichier `.excalidraw` généré

#### Fonctionnalités

- Interface moderne et intuitive
- Support du glisser-déposer
- Conversion côté serveur
- Téléchargement direct du fichier converti
- Gestion des erreurs avec messages clairs
- Limite de taille : 16MB par fichier

---

## 🏗️ Architecture

L'application est structurée en modules réutilisables :

```
cli.py                    # Point d'entrée principal avec les commandes CLI
├── confluence_base.py    # Classe de base pour les opérations Confluence
├── confluence_scanner.py # Module de scan et inventaire Confluence
├── gliffy_migrator.py    # Module de migration idempotente des images Gliffy
│                          # (avec compression automatique des images)
├── web_converter.py      # Interface web Flask pour la conversion
├── gliffy_to_excalidraw.py  # Module de conversion Gliffy → Excalidraw
└── report_utils.py      # Utilitaires pour générer les rapports TXT dans reports/
```

## 🎯 Portée des commandes

Toutes les commandes Confluence (`scan` et `migrate`) supportent trois modes de portée :

1. **Root (tout Confluence)** : Par défaut, si aucune option n'est spécifiée
2. **Espace(s) spécifique(s)** : Via l'option `--spaces ESPACE1 ESPACE2`
3. **Page spécifique** : Via l'option `--page PAGE_ID`

## 🔒 Sécurité et idempotence

- La commande `migrate` est **idempotente** : vous pouvez la relancer sans risque
- Les pages déjà traitées sont automatiquement détectées et ignorées
- Un rapport détaillé est généré pour tracer toutes les modifications
- Les commandes utilisent uniquement l'API REST de Confluence (pas de navigateur)

## 🖼️ Images personnalisées pour les TID Gliffy

Le système permet de remplacer les icônes Gliffy non reconnues (comme "cloud") par des images dans Excalidraw.

### Étapes pour utiliser des images personnalisées

#### 1. Extraire tous les TID depuis vos fichiers Gliffy

```bash
python3 extract_tids.py --dir gliffy_images/gliffy_files --output tids_mapping.json
```

Cela va créer un fichier `tids_mapping.json` avec tous les TID trouvés.

#### 2. Ajouter vos images pour les TID

1. Créez un dossier `tid_images/` et placez-y vos images (PNG, JPG, SVG)
2. Modifiez le fichier `tids_mapping.json` pour ajouter le chemin de l'image pour chaque TID :

```json
{
  "com.gliffy.stencil.cloud.basic_v1": {
    "count": 5,
    "image_path": "tid_images/cloud.png",
    "description": "Icône cloud"
  }
}
```

#### 3. Utiliser le système

Le système est automatiquement utilisé lors de la conversion Gliffy → Excalidraw. Les objets avec un TID mappé à une image seront convertis en images au lieu de formes.

#### Format des images

- Formats supportés : PNG, JPG/JPEG, SVG
- Les images seront automatiquement encodées en base64 et intégrées dans le fichier Excalidraw
- Les dimensions de l'image seront préservées depuis Gliffy

## 🔧 Dépannage

### Erreur d'authentification

- Vérifiez que votre token API est correct
- Vérifiez que votre utilisateur a les permissions nécessaires sur les pages
- Assurez-vous que l'URL de Confluence est correcte (avec ou sans `/wiki` selon votre instance)

### Erreur "No module named 'requests'"

```bash
pip install -r requirements.txt
```

Assurez-vous d'utiliser Python 3.8 ou supérieur.

### Erreur lors de la migration

- Consultez le rapport TXT dans `reports/` pour les détails lisibles
- Les pages en erreur sont listées avec des messages d'erreur détaillés :
  - **Erreur 413** : Image trop grande - compression automatique activée
  - **Erreur 403** : Permission refusée - vérifiez vos droits d'écriture
  - **Erreur 404** : Page non trouvée
  - **Timeout** : Problème de connexion réseau
- Vérifiez que vous avez les permissions d'écriture sur les pages

### Erreur "Request too large" (413)

Si vous voyez cette erreur :
- La compression automatique devrait normalement la résoudre
- Si l'image est encore trop grande après compression, réduisez la taille du diagramme Gliffy dans l'éditeur
- Divisez les très grands diagrammes en plusieurs plus petits

### Le serveur web ne démarre pas

- Vérifiez que le port n'est pas déjà utilisé
- Utilisez `--host 0.0.0.0` pour écouter sur toutes les interfaces
- Vérifiez les permissions de port (ports < 1024 nécessitent des privilèges root)

### Aucun Gliffy trouvé

- Vérifiez que les pages contiennent bien des diagrammes Gliffy
- Certains Gliffy peuvent être dans des formats non standards
- Les drafts peuvent nécessiter des permissions spéciales

## 📁 Gestion des rapports

Tous les rapports générés sont sauvegardés dans le dossier `reports/` au format texte (`.txt`) pour une lecture facile.

### Format des fichiers

- **Horodatage automatique** : Chaque rapport a un horodatage dans son nom pour éviter l'écrasement
  - Format : `nom_rapport_YYYY-MM-DD_HH-MM-SS.txt`
  - Exemple : `migration_report_2025-12-24_15-30-22.txt`
- **Fichiers générés** :
  - `gliffy_pages_*.txt` - Liste des pages avec Gliffy
  - `migration_report_*.txt` - Rapport de migration détaillé
  - `tids_mapping_*.txt` - Mapping des TID Gliffy
  - `confluence_inventory_*.txt` - Inventaire complet Confluence
  - `info_espace_*_*.txt` - Informations par espace

### Avantages

- ✅ Aucun fichier n'est écrasé - historique complet conservé
- ✅ Format texte lisible directement
- ✅ Triable chronologiquement par nom de fichier
- ✅ Tous les rapports centralisés dans un seul dossier

## 📝 Notes importantes

- Les commandes utilisent uniquement l'API REST de Confluence
- Pas besoin de navigateur pour les commandes `scan` et `migrate`
- Le serveur web est autonome et ne nécessite pas de configuration supplémentaire
- Les fichiers temporaires sont automatiquement nettoyés
- Fonctionne avec Confluence Cloud (atlassian.net) et Confluence Server/Data Center
- Support des pages en brouillon (drafts)
- **Compression automatique** : Les images trop grandes sont automatiquement compressées pour respecter les limites de Confluence

## 📚 Scripts supplémentaires

L'application inclut également des scripts utilitaires :

- `find_gliffy_pages.py` - Identifie les pages avec Gliffy (ancien script, toujours fonctionnel)
- `download_gliffy.py` - Télécharge et insère les Gliffy (ancien script, toujours fonctionnel)
- `convert_local_gliffy.py` - Convertit les fichiers `.gliffy` locaux en Excalidraw
- `extract_tids.py` - Extrait les TID depuis les fichiers Gliffy
- `tid_image_mapper.py` - Gère le mapping des images pour les TID

## 🎉 Exemple complet d'utilisation

```bash
# 1. Scanner tout Confluence pour créer un inventaire (génère reports/confluence_inventory_*.txt)
python cli.py scan \
  --url https://mon-confluence.atlassian.net/wiki \
  --username mon.email@example.com \
  --token MON_TOKEN_API \
  --format txt

# 2. Scanner un espace spécifique
python cli.py scan \
  --url https://mon-confluence.atlassian.net/wiki \
  --username mon.email@example.com \
  --token MON_TOKEN_API \
  --spaces DEV

# 3. Migrer les images Gliffy dans un espace spécifique
# Génère reports/migration_report_*.txt avec horodatage
python cli.py migrate \
  --url https://mon-confluence.atlassian.net/wiki \
  --username mon.email@example.com \
  --token MON_TOKEN_API \
  --spaces DEV \
  --report migration_report.json

# 4. Lancer l'interface web pour convertir des fichiers
python cli.py web --host 0.0.0.0 --port 8080
```

## 📋 Commandes rapides

```bash
# Installation
pip install -r requirements.txt

# Scanner Confluence (génère reports/confluence_inventory_*.txt)
python cli.py scan --url URL --username USER --token TOKEN --spaces ESPACE

# Migrer les images Gliffy (génère reports/migration_report_*.txt)
python cli.py migrate --url URL --username USER --token TOKEN --report migration_report.json

# Lancer l'interface web
python cli.py web
```
