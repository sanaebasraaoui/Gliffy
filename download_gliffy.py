#!/usr/bin/env python3
"""
Script pour télécharger les diagrammes Gliffy depuis Confluence et les insérer dans les pages.

Ce module permet de télécharger les images Gliffy (attachments) depuis Confluence
et de les insérer directement dans les pages sous les diagrammes correspondants.

Fonctionnalités :
- Téléchargement des attachments Gliffy (PNG/SVG)
- Insertion des images dans les pages Confluence
- Conversion en Excalidraw avec images en base64
- Sauvegarde locale des images téléchargées

Auteur: Sanae Basraoui
"""

import argparse
import base64
import json
import re
import requests
import time
import random
import math
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from html import unescape
from urllib.parse import urlparse

class GliffyDownloader:
    def __init__(
        self,
        confluence_url: str,
        username: str,
        api_token: str,
        output_dir: str = "gliffy_images",
        excalidraw_output_dir: str = "output",
    ):
        self.confluence_url = confluence_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Dossier pour les fichiers Excalidraw
        self.excalidraw_output_dir = Path(excalidraw_output_dir)
        self.excalidraw_output_dir.mkdir(exist_ok=True)
        
        # Détecter si c'est Atlassian Cloud
        if 'atlassian.net' in self.confluence_url.lower():
            if '/wiki' in self.confluence_url.lower():
                self.api_base = f"{self.confluence_url}/rest/api"
            else:
                self.api_base = f"{self.confluence_url}/wiki/rest/api"
        else:
            self.api_base = f"{self.confluence_url}/rest/api"
        
        self.session = requests.Session()
        self.session.auth = (username, api_token)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        self.stats = {
            'pages_processed': 0,
            'gliffy_found': 0,
            'gliffy_downloaded': 0,
            'errors': 0
        }

    def extract_gliffy_attachments_from_content(self, body_storage: str) -> List[Dict]:
        """Extrait les IDs d'attachments Gliffy depuis le contenu d'une page."""
        gliffy_attachments = []
        
        gliffy_macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
        gliffy_macros = re.findall(gliffy_macro_pattern, body_storage, re.DOTALL | re.IGNORECASE)
        
        for macro in gliffy_macros:
            image_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']imageAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            diagram_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']diagramAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            macro_id = re.search(r'<ac:parameter[^>]*ac:name=["\']macroId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            name_param = re.search(r'<ac:parameter[^>]*ac:name=["\']name["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            
            att_id = image_att_id.group(1).strip() if image_att_id else None
            diagram_att_id_value = diagram_att_id.group(1).strip() if diagram_att_id else None
            macro_id_value = macro_id.group(1).strip() if macro_id else None
            diagram_name = name_param.group(1).strip() if name_param else None
            
            if att_id or diagram_att_id_value:
                gliffy_attachments.append({
                    'attachmentId': att_id,
                    'diagramAttachmentId': diagram_att_id_value,
                    'macroId': macro_id_value,
                    'diagramName': diagram_name,
                    'macroHtml': macro
                })
        
        return gliffy_attachments

    def download_attachment_direct(self, page_id: str, attachment_id: str, is_draft: bool = False) -> Optional[Tuple[bytes, str]]:
        """Télécharge un attachment directement via l'API REST."""
        try:
            download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id}/download"
            params = {}
            if is_draft:
                params['status'] = 'draft'
            
            headers = {}
            download_response = self.session.get(download_api_url, params=params, headers=headers, timeout=30)
            
            if download_response.status_code == 200:
                content = download_response.content
                if b'Error 404' not in content and b'Diagram Missing' not in content:
                    content_type = download_response.headers.get('content-type', '').lower()
                    if 'svg' in content_type or content.startswith(b'<svg'):
                        return (content, 'image/svg+xml')
                    elif 'png' in content_type or content.startswith(b'\x89PNG'):
                        return (content, 'image/png')
                    elif 'image/' in content_type:
                        return (content, content_type)
                    return (content, content_type or 'application/octet-stream')
            
            if download_response.status_code != 200 and attachment_id.startswith('att'):
                attachment_id_no_prefix = attachment_id[3:]
                download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id_no_prefix}/download"
                download_response = self.session.get(download_api_url, params=params, headers=headers, timeout=30)
                
                if download_response.status_code == 200:
                    content = download_response.content
                    if b'Error 404' not in content and b'Diagram Missing' not in content:
                        content_type = download_response.headers.get('content-type', '').lower()
                        if 'svg' in content_type or content.startswith(b'<svg'):
                            return (content, 'image/svg+xml')
                        elif 'png' in content_type or content.startswith(b'\x89PNG'):
                            return (content, 'image/png')
                        elif 'image/' in content_type:
                            return (content, content_type)
                        return (content, content_type or 'application/octet-stream')
        except Exception as e:
            pass
        
        return None

    def download_gliffy_json(self, page_id: str, diagram_attachment_id: str, is_draft: bool = False) -> Optional[dict]:
        """Télécharge le fichier .gliffy JSON."""
        if not diagram_attachment_id:
            return None
        
        # Essayer différentes combinaisons de page_id et attachment_id
        page_ids_to_try = [page_id]
        attachment_ids_to_try = [diagram_attachment_id]
        
        # Si l'attachment_id commence par 'att', essayer aussi sans le préfixe
        if diagram_attachment_id.startswith('att'):
            attachment_ids_to_try.append(diagram_attachment_id[3:])
        
        for try_page_id in page_ids_to_try:
            for try_attachment_id in attachment_ids_to_try:
                try:
                    download_url = f"{self.api_base}/content/{try_page_id}/child/attachment/{try_attachment_id}/download"
                    params = {}
                    if is_draft:
                        params['status'] = 'draft'
                    
                    response = self.session.get(download_url, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        try:
                            gliffy_data = json.loads(response.content)
                            # Vérifier que c'est bien un JSON Gliffy valide
                            if isinstance(gliffy_data, dict) and (gliffy_data.get('stage') or gliffy_data.get('pages')):
                                # Sauvegarder le fichier .gliffy pour extraction des TID
                                gliffy_dir = self.output_dir / 'gliffy_files'
                                gliffy_dir.mkdir(exist_ok=True)
                                gliffy_filename = f"{try_page_id}_{try_attachment_id}.gliffy"
                                gliffy_filepath = gliffy_dir / gliffy_filename
                                with open(gliffy_filepath, 'wb') as f:
                                    f.write(response.content)
                                return gliffy_data
                        except json.JSONDecodeError:
                            pass
                    
                    # Si 404 avec status=draft, essayer sans le paramètre status
                    if response.status_code == 404 and is_draft:
                        params_no_status = {}
                        response_no_status = self.session.get(download_url, params=params_no_status, timeout=30)
                        if response_no_status.status_code == 200:
                            try:
                                gliffy_data = json.loads(response_no_status.content)
                                if isinstance(gliffy_data, dict) and (gliffy_data.get('stage') or gliffy_data.get('pages')):
                                    return gliffy_data
                            except json.JSONDecodeError:
                                pass
                except Exception as e:
                    continue
        
        return None

    def insert_image_after_macro(self, page_id: str, page_title: str, space_key: str, image_content: bytes, mime_type: str, diagram_name: Optional[str], macro_html: str, is_draft: bool = False, current_body: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Insère une image PNG après la macro Gliffy."""
        try:
            url = f"{self.api_base}/content/{page_id}"
            params = {'expand': 'body.storage,version,space,title'}
            if is_draft:
                params['status'] = 'draft'
            
            response = self.session.get(url, params=params)
            if response.status_code != 200:
                return (False, None)
            
            page_data = response.json()
            current_body = page_data.get('body', {}).get('storage', {}).get('value', '')
            version_num = page_data.get('version', {}).get('number', 1)
            title = page_data.get('title', page_title)
            space_key_from_api = page_data.get('space', {}).get('key', space_key)
            
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            image_data_url = f"data:{mime_type};base64,{image_base64}"
            
            safe_page_title = re.sub(r'[^\w\s-]', '', page_title).strip()
            safe_page_title = re.sub(r'[-\s]+', '_', safe_page_title)
            
            if diagram_name:
                safe_diagram_name = re.sub(r'[^\w\s-]', '', diagram_name).strip()
                safe_diagram_name = re.sub(r'[-\s]+', '_', safe_diagram_name)
                alt_text = f"{safe_page_title}_{page_id}_{safe_diagram_name}"
                title_text = f"📊 Diagramme Gliffy exporté: {diagram_name}"
            else:
                alt_text = f"{safe_page_title}_{page_id}_gliffy"
                title_text = "📊 Diagramme Gliffy exporté"
            
            image_html = f'<p><strong>{title_text}</strong><br/><img src="{image_data_url}" alt="{alt_text}" title="{alt_text}" /></p>'
            
            escaped_macro = re.escape(macro_html)
            macro_match = re.search(escaped_macro, current_body, re.DOTALL | re.IGNORECASE)
            
            if not macro_match:
                macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
                all_macros = list(re.finditer(macro_pattern, current_body, re.DOTALL | re.IGNORECASE))
                if all_macros:
                    macro_match = all_macros[-1]
            
            if macro_match:
                insert_position = macro_match.end()
                
                # Insérer l'image directement après la macro Gliffy, sans vérifier ce qui existe déjà
                new_body = current_body[:insert_position] + image_html + current_body[insert_position:]
            else:
                new_body = current_body + image_html
            
            # Pour les drafts, utiliser la version actuelle sans incrément
            version_number = version_num if is_draft else (version_num + 1)
            
            update_data = {
                'id': page_id,
                'type': 'page',
                'title': title,
                'space': {'key': space_key_from_api},
                'body': {'storage': {'value': new_body, 'representation': 'storage'}},
                'version': {'number': version_number}
            }
            
            update_response = self.session.put(url, json=update_data, params=params)
            if update_response.status_code == 200:
                return (True, new_body)
            elif update_response.status_code == 409 and is_draft:
                # Conflit de version pour draft - réessayer avec la version actuelle
                try:
                    current_response = self.session.get(url, params=params)
                    if current_response.status_code == 200:
                        current_data = current_response.json()
                        current_version = current_data.get('version', {}).get('number', version_num)
                        update_data['version'] = {'number': current_version}
                        retry_response = self.session.put(url, json=update_data, params=params)
                        if retry_response.status_code == 200:
                            return (True, new_body)
                except:
                    pass
        except Exception as e:
            pass
        return (False, None)

    def process_page(self, page_id: str, page_title: str, space_key: str, body_storage: Optional[str] = None, is_draft: bool = False, space_name: Optional[str] = None) -> Tuple[int, List[Dict]]:
        """Traite une page pour extraire et télécharger ses Gliffy."""
        try:
            if body_storage is None:
                url = f"{self.api_base}/content/{page_id}"
                params = {'expand': 'body.storage'}
                if is_draft:
                    params['status'] = 'draft'
                
                response = self.session.get(url, params=params)
                if response.status_code != 200:
                    return (0, [])
                
                page_data = response.json()
                body_storage = page_data.get('body', {}).get('storage', {}).get('value', '')
            
            gliffy_attachments = self.extract_gliffy_attachments_from_content(body_storage)
            
            if not gliffy_attachments:
                return (0, [])
            
            print(f"  📄 Page: '{page_title}' (ID: {page_id})")
            print(f"     {len(gliffy_attachments)} Gliffy trouvé(s)")
            
            downloaded_count = 0
            gliffy_info_list = []
            current_page_body = None
            
            for idx, gliffy_att in enumerate(gliffy_attachments):
                attachment_id = gliffy_att.get('attachmentId')
                macro_id = gliffy_att.get('macroId')
                
                if attachment_id:
                    print(f"     Téléchargement Gliffy {idx + 1}/{len(gliffy_attachments)} (Attachment: {attachment_id})...", end='')
                elif macro_id:
                    print(f"     Téléchargement Gliffy {idx + 1}/{len(gliffy_attachments)} (MacroId: {macro_id[:8]}...)...", end='')
                else:
                    continue
                
                result = None
                
                if attachment_id:
                    gliffy_info = gliffy_attachments[idx]
                    container_id = None
                    macro_html = gliffy_info.get('macroHtml', '')
                    if macro_html:
                        container_match = re.search(r'<ac:parameter[^>]*ac:name=["\']containerId["\'][^>]*>([^<]+)</ac:parameter>', macro_html, re.IGNORECASE)
                        if container_match:
                            container_id = container_match.group(1).strip()
                    
                    if container_id and container_id != page_id:
                        result = self.download_attachment_direct(container_id, attachment_id, False)
                        if not result:
                            result = self.download_attachment_direct(container_id, attachment_id, True)
                        if not result and attachment_id.startswith('att'):
                            attachment_id_no_prefix = attachment_id[3:]
                            result = self.download_attachment_direct(container_id, attachment_id_no_prefix, False)
                            if not result:
                                result = self.download_attachment_direct(container_id, attachment_id_no_prefix, True)
                    
                    if not result:
                        result = self.download_attachment_direct(page_id, attachment_id, is_draft=is_draft)
                    
                    if not result and is_draft:
                        # Pour les drafts, essayer avec status=draft explicitement
                        result = self.download_attachment_direct(page_id, attachment_id, True)
                    
                    # Si toujours pas de résultat, essayer sans le préfixe 'att'
                    if not result and attachment_id.startswith('att'):
                        attachment_id_no_prefix = attachment_id[3:]
                        result = self.download_attachment_direct(page_id, attachment_id_no_prefix, is_draft=is_draft)
                        if not result and is_draft:
                            result = self.download_attachment_direct(page_id, attachment_id_no_prefix, True)
                    
                    # Si le fichier existe déjà localement, le réutiliser
                    if not result:
                        diagram_name = gliffy_att.get('diagramName')
                        safe_page_title = re.sub(r'[^\w\s-]', '', page_title).strip()
                        safe_page_title = re.sub(r'[-\s]+', '_', safe_page_title)
                        
                        if diagram_name:
                            safe_diagram_name = re.sub(r'[^\w\s-]', '', diagram_name).strip()
                            safe_diagram_name = re.sub(r'[-\s]+', '_', safe_diagram_name)
                            filename_base = f"{safe_page_title}_{page_id}_{safe_diagram_name}"
                        else:
                            filename_base = f"{safe_page_title}_{page_id}_gliffy"
                        
                        if space_name:
                            safe_space_name = re.sub(r'[^\w\s-]', '', space_name).strip()
                            safe_space_name = re.sub(r'[-\s]+', '_', safe_space_name)
                            space_dir_name = safe_space_name
                        else:
                            space_dir_name = space_key
                        
                        space_dir = self.output_dir / space_dir_name
                        # Chercher le fichier PNG ou SVG existant
                        for ext in ['.png', '.svg']:
                            existing_file = space_dir / f"{filename_base}{ext}"
                            if existing_file.exists():
                                with open(existing_file, 'rb') as f:
                                    image_content = f.read()
                                mime_type = 'image/png' if ext == '.png' else 'image/svg+xml'
                                result = (image_content, mime_type)
                                print(f" 📁 (fichier existant réutilisé)", end='')
                                break
                
                if result:
                    image_content, mime_type = result
                    print(f" ✅")
                    
                    diagram_name = gliffy_att.get('diagramName')
                    
                    safe_page_title = re.sub(r'[^\w\s-]', '', page_title).strip()
                    safe_page_title = re.sub(r'[-\s]+', '_', safe_page_title)
                    
                    if diagram_name:
                        safe_diagram_name = re.sub(r'[^\w\s-]', '', diagram_name).strip()
                        safe_diagram_name = re.sub(r'[-\s]+', '_', safe_diagram_name)
                        filename_base = f"{safe_page_title}_{page_id}_{safe_diagram_name}"
                    else:
                        filename_base = f"{safe_page_title}_{page_id}_gliffy"
                    
                    if 'svg' in mime_type:
                        filename = f"{filename_base}.svg"
                    else:
                        filename = f"{filename_base}.png"
                    
                    if space_name:
                        safe_space_name = re.sub(r'[^\w\s-]', '', space_name).strip()
                        safe_space_name = re.sub(r'[-\s]+', '_', safe_space_name)
                        space_dir_name = safe_space_name
                    else:
                        space_dir_name = space_key
                    
                    space_dir = self.output_dir / space_dir_name
                    space_dir.mkdir(parents=True, exist_ok=True)
                    
                    filepath = space_dir / filename
                    with open(filepath, 'wb') as f:
                        f.write(image_content)
                    print(f"     💾 Image sauvegardée: {space_dir_name}/{filename}")
                    
                    relative_path = f"{space_dir_name}/{filename}"
                    gliffy_info_list.append({
                        'diagram_name': diagram_name or 'Sans nom',
                        'filename': filename,
                        'filepath': str(filepath),
                        'relative_path': relative_path,
                        'mime_type': mime_type,
                        'attachment_id': attachment_id,
                        'macro_id': macro_id
                    })
                    
                    print(f"     Insertion de l'image dans le contenu de la page ({mime_type})...")
                    
                    # Utiliser le body mis à jour de l'itération précédente, ou récupérer depuis l'API si c'est la première itération
                    if current_page_body is None:
                        try:
                            url = f"{self.api_base}/content/{page_id}"
                            params = {'expand': 'body.storage'}
                            if is_draft:
                                params['status'] = 'draft'
                            response = self.session.get(url, params=params)
                            if response.status_code == 200:
                                page_data = response.json()
                                current_page_body = page_data.get('body', {}).get('storage', {}).get('value', '')
                            else:
                                current_page_body = None
                        except:
                            current_page_body = None
                    
                    macro_html = gliffy_att.get('macroHtml', '')
                    insert_success, updated_body = self.insert_image_after_macro(
                        page_id, page_title, space_key, image_content, mime_type, diagram_name, macro_html, is_draft, current_page_body
                    )
                    
                    if insert_success:
                        print(f"     ✅ Image insérée dans la page!")
                        current_page_body = updated_body  # Mettre à jour pour la prochaine itération
                        downloaded_count += 1
                        self.stats['gliffy_downloaded'] += 1
                    else:
                        print(f"     ⚠️  Insertion échouée, image sauvegardée localement")
                        downloaded_count += 1
                    
                    # Conversion Gliffy → Excalidraw
                    diagram_attachment_id = gliffy_att.get('diagramAttachmentId')
                    if diagram_attachment_id:
                        print(f"     Conversion Gliffy → Excalidraw...", end='')
                        try:
                            # Utiliser containerId pour télécharger le JSON si disponible
                            json_page_id = page_id
                            if container_id and container_id != page_id:
                                json_page_id = container_id
                            
                            # Essayer d'abord avec containerId si disponible
                            gliffy_json = self.download_gliffy_json(json_page_id, diagram_attachment_id, is_draft=is_draft)
                            
                            # Si échec et containerId différent, essayer avec page_id
                            if not gliffy_json and json_page_id != page_id:
                                gliffy_json = self.download_gliffy_json(page_id, diagram_attachment_id, is_draft=is_draft)
                            
                            # Si toujours échec et c'est un draft, essayer sans le paramètre status
                            if not gliffy_json and is_draft:
                                gliffy_json = self.download_gliffy_json(json_page_id, diagram_attachment_id, is_draft=False)
                                if not gliffy_json and json_page_id != page_id:
                                    gliffy_json = self.download_gliffy_json(page_id, diagram_attachment_id, is_draft=False)
                            
                            if gliffy_json and isinstance(gliffy_json, dict):
                                from gliffy_to_excalidraw import convert_gliffy_to_excalidraw
                                try:
                                    from tid_image_mapper import TIDImageMapper
                                    tid_mapper = TIDImageMapper()
                                except ImportError:
                                    tid_mapper = None
                                
                                excalidraw_data = convert_gliffy_to_excalidraw(
                                    gliffy_json, 
                                    tid_image_mapper=tid_mapper
                                )
                                if excalidraw_data:
                                    # Formater le JSON de manière cohérente (sans espaces superflus mais avec séparateurs compacts)
                                    # Utiliser separators=(',', ':') pour éviter les espaces et garantir un format compact cohérent
                                    excalidraw_content = json.dumps(excalidraw_data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                                    
                                    # Créer un nom de fichier pour sauvegarder dans le dossier output
                                    if diagram_name:
                                        safe_diagram_name = re.sub(r'[^\w\s-]', '', diagram_name).strip()
                                        safe_diagram_name = re.sub(r'[-\s]+', '_', safe_diagram_name)
                                        excalidraw_filename = f"{safe_page_title}_{page_id}_{safe_diagram_name}.excalidraw"
                                    else:
                                        excalidraw_filename = f"{safe_page_title}_{page_id}_gliffy.excalidraw"
                                    
                                    # Sauvegarder le fichier Excalidraw dans le dossier output
                                    excalidraw_filepath = self.excalidraw_output_dir / excalidraw_filename
                                    with open(excalidraw_filepath, 'wb') as f:
                                        f.write(excalidraw_content)
                                    print(f" ✅ Sauvegardé dans output/{excalidraw_filename}")
                                else:
                                    print(f" ⚠️ (conversion retournée vide)")
                            else:
                                print(f" ⚠️ (téléchargement .gliffy échoué ou format invalide)")
                        except Exception as e:
                            import traceback
                            error_msg = str(e)
                            print(f" ⚠️ (erreur conversion: {error_msg[:50]})")
                            if 'GLIFFY_DEBUG' in str(e) or len(error_msg) < 100:
                                traceback.print_exc()
                else:
                    print(f" ❌ (attachment non accessible)")
                    self.stats['errors'] += 1
            
            self.stats['gliffy_found'] += len(gliffy_attachments)
            return (downloaded_count, gliffy_info_list)
            
        except Exception as e:
            print(f"  ⚠️  Erreur lors du traitement de la page '{page_title}': {e}")
            import traceback
            traceback.print_exc()
            self.stats['errors'] += 1
            return (0, [])

    def create_space_info_file(self, space_key: str, space_name: str, pages_info: List[Dict]):
        """Crée un fichier texte avec toutes les informations de l'espace."""
        if not space_name:
            safe_space_name = re.sub(r'[^\w\s-]', '', space_key).strip()
            safe_space_name = re.sub(r'[-\s]+', '_', safe_space_name)
            space_dir_name = safe_space_name
        else:
            safe_space_name = re.sub(r'[^\w\s-]', '', space_name).strip()
            safe_space_name = re.sub(r'[-\s]+', '_', safe_space_name)
            space_dir_name = safe_space_name
        
        space_dir = self.output_dir / space_dir_name
        space_dir.mkdir(parents=True, exist_ok=True)
        
        info_file = space_dir / 'info_espace.txt'
        
        with open(info_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"INFORMATIONS DE L'ESPACE CONFLUENCE\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Nom de l'espace: {space_name}\n")
            f.write(f"Clé de l'espace: {space_key}\n")
            f.write(f"URL de l'espace: {self.confluence_url.rstrip('/wiki')}/wiki/spaces/{space_key}\n")
            f.write(f"\n")
            
            f.write("=" * 80 + "\n")
            f.write(f"PAGES AVEC GLIFFY ({len(pages_info)} page(s))\n")
            f.write("=" * 80 + "\n\n")
            
            total_gliffy = 0
            for page_info in pages_info:
                page_id = page_info.get('page_id', '')
                page_title = page_info.get('page_title', 'Sans titre')
                gliffy_list = page_info.get('gliffy_list', [])
                total_gliffy += len(gliffy_list)
                
                f.write(f"\n📄 Page: {page_title}\n")
                f.write(f"   ID: {page_id}\n")
                f.write(f"   URL: {self.confluence_url.rstrip('/wiki')}/wiki/pages/viewpage.action?pageId={page_id}\n")
                f.write(f"   Nombre de Gliffy: {len(gliffy_list)}\n")
                
                if gliffy_list:
                    f.write(f"\n   Diagrammes Gliffy:\n")
                    for idx, gliffy in enumerate(gliffy_list, 1):
                        f.write(f"\n   {idx}. Diagramme: {gliffy.get('diagram_name', 'Sans nom')}\n")
                        f.write(f"      • Fichier PNG/SVG: {gliffy.get('filename', 'N/A')}\n")
                        f.write(f"      • Chemin relatif: {gliffy.get('relative_path', 'N/A')}\n")
                        f.write(f"      • Chemin absolu: {gliffy.get('filepath', 'N/A')}\n")
                        f.write(f"      • Type MIME: {gliffy.get('mime_type', 'N/A')}\n")
                        f.write(f"      • ID Attachment: {gliffy.get('attachment_id', 'N/A')}\n")
                        f.write(f"      • ID Macro: {gliffy.get('macro_id', 'N/A')}\n")
                f.write(f"\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"RÉSUMÉ\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total de pages avec Gliffy: {len(pages_info)}\n")
            f.write(f"Total de diagrammes Gliffy: {total_gliffy}\n")
            f.write(f"Dossier de sortie: {space_dir.absolute()}\n")
            f.write("=" * 80 + "\n")
        
        print(f"     📝 Fichier d'information créé: {space_dir_name}/info_espace.txt")
        
        # Copier également dans le dossier reports/ avec horodatage
        try:
            from report_utils import ensure_reports_dir, add_timestamp_to_filename
            import shutil
            reports_dir = ensure_reports_dir()
            timestamped_filename = add_timestamp_to_filename(f"info_espace_{space_dir_name}.txt")
            reports_info_file = reports_dir / timestamped_filename
            shutil.copy2(info_file, reports_info_file)
            print(f"     📝 Copie dans reports/: {reports_info_file.name}")
        except Exception as e:
            # Ne pas bloquer si la copie échoue
            pass

    def run_from_json(self, json_file: str = 'gliffy_pages.json'):
        """Lit le fichier JSON et traite toutes les pages."""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                pages_data = json.load(f)
        except FileNotFoundError:
            print(f"❌ Fichier {json_file} non trouvé. Veuillez exécuter find_gliffy_pages.py d'abord.")
            return
        
        print(f"📖 Traitement de {len(pages_data)} page(s)...\n")
        
        pages_by_space = {}
        for page_info in pages_data:
            space_key = page_info.get('space_key', 'unknown')
            if space_key not in pages_by_space:
                pages_by_space[space_key] = []
            pages_by_space[space_key].append(page_info)
        
        for space_key, pages in pages_by_space.items():
            space_name = pages[0].get('space_name', space_key)
            print(f"\n📁 Espace: {space_name} ({space_key})")
            
            space_pages_info = []
            for page_info in pages:
                page_id = page_info.get('id')
                page_title = page_info.get('title', 'Sans titre')
                body_storage = page_info.get('body_storage', '')
                is_draft = page_info.get('status') == 'draft'
                
                downloaded_count, gliffy_info_list = self.process_page(page_id, page_title, space_key, body_storage, is_draft, space_name)
                self.stats['pages_processed'] += 1
                
                if gliffy_info_list:
                    space_pages_info.append({
                        'page_id': page_id,
                        'page_title': page_title,
                        'gliffy_list': gliffy_info_list
                    })
                print()
            
            # Créer le fichier d'information pour cet espace
            if space_pages_info:
                self.create_space_info_file(space_key, space_name, space_pages_info)
        
        print("=" * 60)
        print("📊 Statistiques finales:")
        print(f"  • Pages traitées: {self.stats['pages_processed']}")
        print(f"  • Gliffy trouvés: {self.stats['gliffy_found']}")
        print(f"  • Gliffy uploadés dans Confluence: {self.stats['gliffy_downloaded']}")
        print(f"  • Erreurs: {self.stats['errors']}")
        print(f"  • Images sauvegardées localement dans: {self.output_dir.absolute()}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Télécharge et convertit les diagrammes Gliffy depuis Confluence')
    parser.add_argument('--url', required=True, help='URL de base de Confluence')
    parser.add_argument('--username', required=True, help='Nom d\'utilisateur ou email')
    parser.add_argument('--token', required=True, help='Token API Confluence')
    parser.add_argument('--output', default='gliffy_images', help='Dossier de sortie (défaut: gliffy_images)')
    parser.add_argument('--json', default='gliffy_pages.json', help='Fichier JSON avec les pages (défaut: gliffy_pages.json)')
    
    args = parser.parse_args()
    
    downloader = GliffyDownloader(
        confluence_url=args.url,
        username=args.username,
        api_token=args.token,
        output_dir=args.output
    )
    
    downloader.run_from_json(args.json)


if __name__ == '__main__':
    main()
