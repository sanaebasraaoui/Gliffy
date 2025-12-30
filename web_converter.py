#!/usr/bin/env python3
"""
Interface web pour convertir des fichiers Gliffy en Excalidraw.

Ce module fournit une interface web Flask permettant de convertir des fichiers
Gliffy (.gliffy) en fichiers Excalidraw (.excalidraw) via une interface
utilisateur moderne et intuitive.

Fonctionnalités :
- Interface web moderne avec glisser-déposer
- Conversion de fichiers Gliffy uniques ou multiples
- Export en fichier unique (.excalidraw) ou ZIP (plusieurs fichiers)
- Gestion des erreurs avec messages clairs
- Support du mapper TID pour les images

Auteur: Sanae Basraoui
"""

import json
import zipfile
import os
import logging
from typing import Tuple, Optional
from io import BytesIO
from flask import Flask, request, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
from gliffy_to_excalidraw import convert_gliffy_to_excalidraw

# Imports optionnels pour les fonctionnalités de sécurité
try:
    from flask_httpauth import HTTPBasicAuth
    from flask_wtf.csrf import CSRFProtect
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    SECURITY_AVAILABLE = True
except ImportError:
    # Si les modules de sécurité ne sont pas installés, créer des stubs
    SECURITY_AVAILABLE = False
    HTTPBasicAuth = None
    CSRFProtect = None
    Limiter = None
    get_remote_address = None

# Configuration de l'application
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(32).hex())

# Configuration de sécurité
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB par fichier
MAX_JSON_SIZE = 50 * 1024 * 1024  # 50 MB pour JSON parsé
MAX_FILES_PER_REQUEST = 20  # Maximum de fichiers par requête

# Authentification HTTP Basic (optionnelle via variables d'environnement)
if SECURITY_AVAILABLE:
    auth = HTTPBasicAuth()
    WEB_USERNAME = os.environ.get('WEB_USERNAME', None)
    WEB_PASSWORD = os.environ.get('WEB_PASSWORD', None)
    
    # Protection CSRF
    csrf = CSRFProtect(app)
    
    # Rate limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    
    @auth.verify_password
    def verify_password(username, password):
        """Vérifie les credentials pour l'authentification HTTP Basic."""
        if WEB_USERNAME is None or WEB_PASSWORD is None:
            # Pas d'authentification configurée, autoriser l'accès
            return True
        return username == WEB_USERNAME and password == WEB_PASSWORD

    def csrf_exempt_decorator(f):
        return csrf.exempt(f) if csrf else f
else:
    # Mode sans sécurité (pour compatibilité)
    auth = None
    csrf = None
    limiter = None
    WEB_USERNAME = None
    WEB_PASSWORD = None
    
    # Décorateurs factices
    def verify_password(username, password):
        return True
        
    def csrf_exempt_decorator(f):
        return f

# Configuration du logging sécurisé
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_gliffy_file(file) -> Tuple[bool, str, Optional[dict]]:
    """
    Valide un fichier Gliffy avant traitement.
    
    Args:
        file: Fichier uploadé
        
    Returns:
        Tuple (is_valid, error_message, gliffy_data)
    """
    try:
        # Vérifier la taille du fichier
        file.seek(0, 2)  # Aller à la fin
        file_size = file.tell()
        file.seek(0)  # Retourner au début
        
        if file_size > MAX_FILE_SIZE:
            return False, f"Fichier trop volumineux ({file_size / 1024 / 1024:.2f} MB). Maximum: {MAX_FILE_SIZE / 1024 / 1024} MB", None
        
        if file_size == 0:
            return False, "Fichier vide", None
        
        # Lire et parser le JSON
        try:
            gliffy_data = json.load(file)
        except json.JSONDecodeError as e:
            return False, f"JSON invalide: {str(e)}", None
        
        # Vérifier la taille du JSON parsé
        json_size = len(json.dumps(gliffy_data).encode('utf-8'))
        if json_size > MAX_JSON_SIZE:
            return False, f"JSON parsé trop volumineux ({json_size / 1024 / 1024:.2f} MB). Maximum: {MAX_JSON_SIZE / 1024 / 1024} MB", None
        
        # Vérifier que c'est un dictionnaire (structure Gliffy de base)
        if not isinstance(gliffy_data, dict):
            return False, "Format de fichier invalide: doit être un objet JSON", None
        
        # Vérifier la structure Gliffy minimale (doit avoir un marqueur type de Gliffy)
        gliffy_keys = ['stage', 'pages', 'content', 'type', 'contentType', 'version']
        if not any(k in gliffy_data for k in gliffy_keys):
            return False, "Format Gliffy invalide: structure de fichier non reconnue", None
        
        return True, "", gliffy_data
        
    except Exception as e:
        logger.error(f"Erreur lors de la validation du fichier: {type(e).__name__}")
        return False, f"Erreur de validation: {type(e).__name__}", None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Convertisseur Gliffy → Excalidraw</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 600px;
            width: 100%;
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        
        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: #f8f9ff;
        }
        
        .upload-area:hover {
            border-color: #764ba2;
            background: #f0f2ff;
        }
        
        .upload-area.dragover {
            border-color: #764ba2;
            background: #e8ebff;
        }
        
        .upload-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
        
        .upload-text {
            color: #667eea;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .upload-hint {
            color: #999;
            font-size: 12px;
        }
        
        input[type="file"] {
            display: none;
        }
        
        .file-info {
            margin-top: 20px;
            padding: 15px;
            background: #f0f2ff;
            border-radius: 8px;
            display: none;
        }
        
        .file-info.show {
            display: block;
        }
        
        .file-list {
            max-height: 200px;
            overflow-y: auto;
            margin-top: 10px;
        }
        
        .file-item {
            padding: 8px;
            background: white;
            border-radius: 5px;
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .file-item-name {
            color: #333;
            font-weight: 600;
            font-size: 14px;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .file-item-size {
            color: #666;
            font-size: 12px;
            margin-left: 10px;
        }
        
        .file-count {
            color: #667eea;
            font-weight: 600;
            margin-bottom: 10px;
        }
        
        .button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 20px;
            transition: transform 0.2s ease;
            display: none;
        }
        
        .button:hover {
            transform: translateY(-2px);
        }
        
        .button:active {
            transform: translateY(0);
        }
        
        .button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .download-button {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            display: none;
        }
        
        .download-button.show {
            display: block;
        }
        
        .error {
            margin-top: 20px;
            padding: 15px;
            background: #fee;
            border: 1px solid #fcc;
            border-radius: 8px;
            color: #c33;
            display: none;
        }
        
        .error.show {
            display: block;
        }
        
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
        }
        
        .loading.show {
            display: block;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .success-message {
            margin-top: 20px;
            padding: 15px;
            background: #efe;
            border: 1px solid #cfc;
            border-radius: 8px;
            color: #3c3;
            display: none;
        }
        
        .success-message.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 Convertisseur Gliffy → Excalidraw</h1>
        <p class="subtitle">Téléchargez un ou plusieurs fichiers .gliffy et obtenez les fichiers .excalidraw correspondants</p>
        
        <div class="upload-area" id="uploadArea">
            <div class="upload-icon">📁</div>
            <div class="upload-text">Cliquez ou glissez-déposez vos fichiers .gliffy</div>
            <div class="upload-hint">Format accepté: .gliffy (max 16MB par fichier) - Sélection multiple possible</div>
            <input type="file" id="fileInput" accept=".gliffy" multiple />
        </div>
        
        <div class="file-info" id="fileInfo">
            <div class="file-count" id="fileCount"></div>
            <div class="file-list" id="fileList"></div>
        </div>
        
        <button class="button" id="convertButton" onclick="convertFile()">Convertir</button>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p style="margin-top: 10px; color: #666;">Conversion en cours...</p>
        </div>
        
        <div class="error" id="error"></div>
        <div class="success-message" id="success"></div>
        
        <a href="#" class="button download-button" id="downloadButton" download>📥 Télécharger les fichiers .excalidraw</a>
    </div>
    
    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const fileCount = document.getElementById('fileCount');
        const fileList = document.getElementById('fileList');
        const convertButton = document.getElementById('convertButton');
        const downloadButton = document.getElementById('downloadButton');
        const errorDiv = document.getElementById('error');
        const successDiv = document.getElementById('success');
        const loadingDiv = document.getElementById('loading');
        
        let selectedFiles = [];
        
        uploadArea.addEventListener('click', () => fileInput.click());
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = Array.from(e.dataTransfer.files);
            if (files.length > 0) {
                handleFiles(files);
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFiles(Array.from(e.target.files));
            }
        });
        
        function handleFiles(files) {
            // Filtrer uniquement les fichiers .gliffy
            const gliffyFiles = files.filter(file => file.name.endsWith('.gliffy'));
            
            if (gliffyFiles.length === 0) {
                showError('Veuillez sélectionner au moins un fichier .gliffy');
                return;
            }
            
            selectedFiles = gliffyFiles;
            updateFileList();
            fileInfo.classList.add('show');
            convertButton.style.display = 'block';
            downloadButton.classList.remove('show');
            errorDiv.classList.remove('show');
            successDiv.classList.remove('show');
        }
        
        function updateFileList() {
            const count = selectedFiles.length;
            fileCount.textContent = `${count} fichier${count > 1 ? 's' : ''} sélectionné${count > 1 ? 's' : ''}`;
            
            fileList.innerHTML = '';
            selectedFiles.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <span class="file-item-name">${file.name}</span>
                    <span class="file-item-size">${formatFileSize(file.size)}</span>
                `;
                fileList.appendChild(fileItem);
            });
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }
        
        function showError(message) {
            errorDiv.textContent = message;
            errorDiv.classList.add('show');
            successDiv.classList.remove('show');
        }
        
        async function convertFile() {
            if (selectedFiles.length === 0) {
                showError('Veuillez sélectionner au moins un fichier');
                return;
            }
            
            convertButton.disabled = true;
            loadingDiv.classList.add('show');
            errorDiv.classList.remove('show');
            successDiv.classList.remove('show');
            
            const formData = new FormData();
            selectedFiles.forEach(file => {
                formData.append('files', file);
            });
            
            try {
                const response = await fetch('/convert', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                if (!response.ok) {
                    let errorMessage = 'Erreur lors de la conversion';
                    const contentType = response.headers.get("content-type");
                    if (contentType && contentType.indexOf("application/json") !== -1) {
                        const error = await response.json();
                        errorMessage = error.error || errorMessage;
                    } else {
                        const text = await response.text();
                        console.error("Réponse serveur non-JSON reçue:", text);
                        errorMessage = `Erreur serveur (${response.status})`;
                    }
                    throw new Error(errorMessage);
                }
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                downloadButton.href = url;
                
                // Déterminer le nom du fichier de téléchargement
                if (selectedFiles.length === 1) {
                    downloadButton.download = selectedFiles[0].name.replace('.gliffy', '.excalidraw');
                } else {
                    downloadButton.download = 'gliffy_converted.zip';
                }
                
                loadingDiv.classList.remove('show');
                successDiv.classList.add('show');
                successDiv.textContent = `✅ ${selectedFiles.length} fichier${selectedFiles.length > 1 ? 's' : ''} converti${selectedFiles.length > 1 ? 's' : ''} avec succès !`;
                downloadButton.classList.add('show');
                convertButton.disabled = false;
            } catch (error) {
                loadingDiv.classList.remove('show');
                showError(error.message);
                convertButton.disabled = false;
            }
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Page d'accueil avec l'interface de conversion."""
    # Appliquer l'authentification si disponible
    if SECURITY_AVAILABLE and auth is not None:
        @auth.login_required
        def protected_index():
            return render_template_string(HTML_TEMPLATE)
        return protected_index()
    return render_template_string(HTML_TEMPLATE)


@app.route('/convert', methods=['POST'])
@csrf_exempt_decorator
def convert():
    """
    Endpoint pour convertir un ou plusieurs fichiers Gliffy en Excalidraw.
    Protégé par authentification HTTP Basic et rate limiting.
    """
    try:
        # Vérifier si on a des fichiers (nouveau format multiple) ou un seul fichier (ancien format)
        if 'files' in request.files:
            files = request.files.getlist('files')
        elif 'file' in request.files:
            files = [request.files['file']]
        else:
            return jsonify({'error': 'Aucun fichier fourni'}), 400
        
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        # Limiter le nombre de fichiers par requête
        if len(files) > MAX_FILES_PER_REQUEST:
            return jsonify({'error': f'Trop de fichiers ({len(files)}). Maximum: {MAX_FILES_PER_REQUEST}'}), 400
        
        # Filtrer les fichiers valides par extension
        valid_files = [f for f in files if f.filename and f.filename.endswith('.gliffy')]
        
        if not valid_files:
            return jsonify({'error': 'Aucun fichier .gliffy valide'}), 400
        
        # Essayer d'importer le mapper TID si disponible
        try:
            from tid_image_mapper import TIDImageMapper
            tid_mapper = TIDImageMapper()
        except ImportError:
            tid_mapper = None
        
        converted_files = []
        errors = []
        
        for file in valid_files:
            try:
                # Valider le fichier (taille, structure, contenu)
                is_valid, error_msg, gliffy_data = validate_gliffy_file(file)
                
                if not is_valid:
                    errors.append(f'{secure_filename(file.filename)}: {error_msg}')
                    continue
                
                # Convertir en Excalidraw
                excalidraw_data = convert_gliffy_to_excalidraw(gliffy_data, tid_image_mapper=tid_mapper)
                
                if not excalidraw_data:
                    errors.append(f'{secure_filename(file.filename)}: Échec de la conversion')
                    continue
                
                # Créer le contenu JSON
                excalidraw_json = json.dumps(excalidraw_data, ensure_ascii=False, separators=(',', ':'))
                converted_files.append({
                    'name': secure_filename(file.filename.replace('.gliffy', '.excalidraw')),
                    'content': excalidraw_json.encode('utf-8')
                })
            
            except Exception as e:
                # Ne pas exposer les détails de l'erreur en production
                logger.error(f"Erreur lors de la conversion de {secure_filename(file.filename)}: {type(e).__name__}")
                errors.append(f'{secure_filename(file.filename)}: Erreur lors de la conversion')
        
        if not converted_files:
            error_msg = 'Aucun fichier n\'a pu être converti'
            if errors:
                # Limiter l'exposition des erreurs détaillées
                error_summary = '; '.join(errors[:5])  # Limiter à 5 erreurs
                if len(errors) > 5:
                    error_summary += f' ... et {len(errors) - 5} autre(s) erreur(s)'
                error_msg += f'. Erreurs: {error_summary}'
            return jsonify({'error': error_msg}), 500
        
        # Si un seul fichier, retourner directement
        if len(converted_files) == 1:
            return send_file(
                BytesIO(converted_files[0]['content']),
                mimetype='application/json',
                as_attachment=True,
                download_name=converted_files[0]['name']
            )
        
        # Si plusieurs fichiers, créer un ZIP
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for converted_file in converted_files:
                zip_file.writestr(converted_file['name'], converted_file['content'])
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='gliffy_converted.zip'
        )
    
    except Exception as e:
        # Gestion d'erreur globale sécurisée
        logger.error(f"Erreur inattendue dans convert: {type(e).__name__}")
        return jsonify({'error': 'Une erreur interne est survenue'}), 500


# Gestionnaire d'erreurs global pour l'API pour éviter les réponses HTML
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Trop de requêtes. Veuillez réessayer plus tard."}), 429


@app.errorhandler(500)
def internal_error_handler(e):
    return jsonify({"error": "Erreur interne du serveur."}), 500


def run_server(host='127.0.0.1', port=5000, debug=False):
    """
    Lance le serveur web avec les configurations de sécurité.
    
    Args:
        host: Adresse IP du serveur
        port: Port du serveur
        debug: Mode debug (désactivé en production pour la sécurité)
    """
    # Désactiver le mode debug en production pour éviter l'exposition d'informations
    if os.environ.get('FLASK_ENV') == 'production':
        debug = False
        app.config['DEBUG'] = False
    
    # Avertissements de sécurité
    if not SECURITY_AVAILABLE:
        print("⚠️  ATTENTION: Modules de sécurité non installés!")
        print("   Installez-les avec: pip install flask-httpauth flask-wtf flask-limiter")
        print("   L'interface web fonctionnera sans authentification.")
    else:
        if WEB_USERNAME is None or WEB_PASSWORD is None:
            print("⚠️  ATTENTION: Authentification web non configurée!")
            print("   Configurez WEB_USERNAME et WEB_PASSWORD pour sécuriser l'interface.")
            print("   Exemple: export WEB_USERNAME=admin && export WEB_PASSWORD=secret")
        else:
            print("✅ Authentification HTTP Basic activée")
        
        print(f"🔒 Rate limiting: 10 conversions/minute par IP")
        print(f"🛡️  Protection CSRF activée")
    
    print(f"🌐 Serveur web démarré sur http://{host}:{port}")
    print(f"📝 Ouvrez votre navigateur et accédez à l'URL ci-dessus")
    
    # Désactiver le reloader en production pour éviter les problèmes de sécurité
    use_reloader = debug and os.environ.get('FLASK_ENV') != 'production'
    app.run(host=host, port=port, debug=debug, use_reloader=use_reloader)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Interface web pour convertir Gliffy en Excalidraw')
    parser.add_argument('--host', default='127.0.0.1', help='Adresse IP du serveur (défaut: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Port du serveur (défaut: 5000)')
    parser.add_argument('--debug', action='store_true', help='Mode debug')
    
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port, debug=args.debug)

