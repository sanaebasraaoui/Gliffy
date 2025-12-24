#!/usr/bin/env python3
"""
Interface web pour convertir des fichiers Gliffy en Excalidraw.
"""

import json
from io import BytesIO
from flask import Flask, request, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
from gliffy_to_excalidraw import convert_gliffy_to_excalidraw

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
        
        .file-name {
            color: #333;
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .file-size {
            color: #666;
            font-size: 12px;
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
        <p class="subtitle">Téléchargez un fichier .gliffy et obtenez le fichier .excalidraw correspondant</p>
        
        <div class="upload-area" id="uploadArea">
            <div class="upload-icon">📁</div>
            <div class="upload-text">Cliquez ou glissez-déposez votre fichier .gliffy</div>
            <div class="upload-hint">Format accepté: .gliffy (max 16MB)</div>
            <input type="file" id="fileInput" accept=".gliffy" />
        </div>
        
        <div class="file-info" id="fileInfo">
            <div class="file-name" id="fileName"></div>
            <div class="file-size" id="fileSize"></div>
        </div>
        
        <button class="button" id="convertButton" onclick="convertFile()">Convertir</button>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p style="margin-top: 10px; color: #666;">Conversion en cours...</p>
        </div>
        
        <div class="error" id="error"></div>
        <div class="success-message" id="success">✅ Conversion réussie !</div>
        
        <a href="#" class="button download-button" id="downloadButton" download>📥 Télécharger le fichier .excalidraw</a>
    </div>
    
    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const convertButton = document.getElementById('convertButton');
        const downloadButton = document.getElementById('downloadButton');
        const errorDiv = document.getElementById('error');
        const successDiv = document.getElementById('success');
        const loadingDiv = document.getElementById('loading');
        
        let selectedFile = null;
        
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
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });
        
        function handleFile(file) {
            if (!file.name.endsWith('.gliffy')) {
                showError('Veuillez sélectionner un fichier .gliffy');
                return;
            }
            
            selectedFile = file;
            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            fileInfo.classList.add('show');
            convertButton.style.display = 'block';
            downloadButton.classList.remove('show');
            errorDiv.classList.remove('show');
            successDiv.classList.remove('show');
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
            if (!selectedFile) {
                showError('Veuillez sélectionner un fichier');
                return;
            }
            
            convertButton.disabled = true;
            loadingDiv.classList.add('show');
            errorDiv.classList.remove('show');
            successDiv.classList.remove('show');
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            
            try {
                const response = await fetch('/convert', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Erreur lors de la conversion');
                }
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                downloadButton.href = url;
                downloadButton.download = selectedFile.name.replace('.gliffy', '.excalidraw');
                
                loadingDiv.classList.remove('show');
                successDiv.classList.add('show');
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
    return render_template_string(HTML_TEMPLATE)


@app.route('/convert', methods=['POST'])
def convert():
    """Endpoint pour convertir un fichier Gliffy en Excalidraw."""
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    if not file.filename.endswith('.gliffy'):
        return jsonify({'error': 'Le fichier doit être au format .gliffy'}), 400
    
    try:
        # Lire le contenu JSON du fichier Gliffy
        gliffy_data = json.load(file)
        
        # Vérifier que c'est un fichier Gliffy valide
        if not isinstance(gliffy_data, dict):
            return jsonify({'error': 'Format de fichier Gliffy invalide'}), 400
        
        # Essayer d'importer le mapper TID si disponible
        try:
            from tid_image_mapper import TIDImageMapper
            tid_mapper = TIDImageMapper()
        except ImportError:
            tid_mapper = None
        
        # Convertir en Excalidraw
        excalidraw_data = convert_gliffy_to_excalidraw(gliffy_data, tid_image_mapper=tid_mapper)
        
        if not excalidraw_data:
            return jsonify({'error': 'Échec de la conversion'}), 500
        
        # Créer le contenu JSON
        excalidraw_json = json.dumps(excalidraw_data, ensure_ascii=False, separators=(',', ':'))
        
        # Retourner le fichier directement depuis la mémoire
        from io import BytesIO
        return send_file(
            BytesIO(excalidraw_json.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=secure_filename(file.filename.replace('.gliffy', '.excalidraw'))
        )
    
    except json.JSONDecodeError:
        return jsonify({'error': 'Le fichier n\'est pas un JSON valide'}), 400
    except Exception as e:
        return jsonify({'error': f'Erreur lors de la conversion: {str(e)}'}), 500


def run_server(host='127.0.0.1', port=5000, debug=False):
    """Lance le serveur web."""
    print(f"🌐 Serveur web démarré sur http://{host}:{port}")
    print(f"📝 Ouvrez votre navigateur et accédez à l'URL ci-dessus")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Interface web pour convertir Gliffy en Excalidraw')
    parser.add_argument('--host', default='127.0.0.1', help='Adresse IP du serveur (défaut: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Port du serveur (défaut: 5000)')
    parser.add_argument('--debug', action='store_true', help='Mode debug')
    
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port, debug=args.debug)

