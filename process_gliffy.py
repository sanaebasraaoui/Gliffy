#!/usr/bin/env python3
"""
Script unique pour traiter tous les Gliffy depuis Confluence.

Ce module effectue un traitement complet des diagrammes Gliffy dans Confluence :
1. Trouve toutes les pages contenant des Gliffy
2. Télécharge les images PNG (captures d'écran) depuis les attachments
3. Insère les images en bas du Gliffy dans les pages Confluence
4. Convertit les Gliffy en Excalidraw avec images en base64
5. Sauvegarde les fichiers Excalidraw dans le dossier output/

Auteur: Sanae Basraoui
"""

import argparse
import base64
import json
import re
import requests
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class GliffyProcessor:
    def __init__(
        self,
        confluence_url: str,
        username: str,
        api_token: str,
        excalidraw_output_dir: str = "output",
        spaces: Optional[List[str]] = None,
    ):
        self.confluence_url = confluence_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.excalidraw_output_dir = Path(excalidraw_output_dir)
        try:
            self.excalidraw_output_dir.mkdir(exist_ok=True)
        except (PermissionError, OSError):
            print(f"⚠️ Impossible de créer le dossier {excalidraw_output_dir}, utilisation du dossier courant.")
            self.excalidraw_output_dir = Path(".")
        self.spaces_filter = set(spaces) if spaces else None
        
        # Détecter si c'est Atlassian Cloud
        if 'atlassian.net' in self.confluence_url.lower():
            # Pour Atlassian Cloud, l'API est toujours à /wiki/rest/api
            if '/wiki' in self.confluence_url.lower():
                # URL contient déjà /wiki, utiliser tel quel
                self.api_base = f"{self.confluence_url.rstrip('/wiki')}/wiki/rest/api"
            else:
                # URL sans /wiki, l'ajouter
                self.api_base = f"{self.confluence_url}/wiki/rest/api"
        else:
            # Confluence Server/Data Center
            self.api_base = f"{self.confluence_url.rstrip('/')}/rest/api"
        
        self.session = requests.Session()
        self.session.auth = (username, api_token)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        self.stats = {
            'spaces_analyzed': 0,
            'pages_analyzed': 0,
            'pages_with_gliffy': 0,
            'gliffy_found': 0,
            'gliffy_downloaded': 0,
            'excalidraw_saved': 0,
            'errors': 0
        }

    def get_all_spaces(self) -> List[Dict]:
        """Récupère tous les espaces Confluence."""
        print("📂 Récupération de la liste des espaces...")
        spaces = []
        start = 0
        limit = 100
        
        while True:
            url = f"{self.api_base}/space"
            params = {'start': start, 'limit': limit, 'expand': 'name,key'}
            
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                results = data.get('results', [])
                if not results:
                    break
                    
                spaces.extend(results)
                
                if len(results) < limit:
                    break
                    
                start += limit
            except Exception as e:
                print(f"❌ Erreur lors de la récupération des espaces: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"   URL testée: {url}")
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('errorMessage') or str(error_data)
                        print(f"   Message: {error_msg}")
                    except:
                        print(f"   Réponse: {e.response.text[:300]}")
                break
        
        if self.spaces_filter:
            spaces = [s for s in spaces if s.get('key') in self.spaces_filter]
            print(f"✅ {len(spaces)} espace(s) sélectionné(s)")
        else:
            print(f"✅ {len(spaces)} espace(s) trouvé(s)")
        
        return spaces

    def get_all_pages(self, space_key: str, include_drafts: bool = True) -> List[Dict]:
        """Récupère toutes les pages d'un espace."""
        pages = []
        start = 0
        limit = 100
        
        while True:
            url = f"{self.api_base}/content"
            params = {
                'spaceKey': space_key,
                'type': 'page',
                'start': start,
                'limit': limit,
                'expand': 'space,version,body.storage'
            }
            
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                results = data.get('results', [])
                if not results:
                    break
                    
                pages.extend(results)
                
                if len(results) < limit:
                    break
                    
                start += limit
            except Exception as e:
                break
        
        # Chercher aussi les drafts
        if include_drafts:
            start = 0
            while True:
                url = f"{self.api_base}/content"
                params = {
                    'spaceKey': space_key,
                    'type': 'page',
                    'status': 'draft',
                    'start': start,
                    'limit': limit,
                    'expand': 'space,version,body.storage'
                }
                
                try:
                    response = self.session.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    results = data.get('results', [])
                    if not results:
                        break
                        
                    pages.extend(results)
                    
                    if len(results) < limit:
                        break
                        
                    start += limit
                except Exception as e:
                    break
        
        return pages

    def extract_gliffy_attachments_from_content(self, body_storage: str, page_id: str = "Inconnue") -> List[Dict]:
        """Extrait les IDs d'attachments Gliffy depuis le contenu d'une page."""
        gliffy_attachments = []
        
        gliffy_macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
        gliffy_macros = re.findall(gliffy_macro_pattern, body_storage, re.DOTALL | re.IGNORECASE)
        
        for macro in gliffy_macros:
            image_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']imageAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            diagram_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']diagramAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            macro_id = re.search(r'<ac:parameter[^>]*ac:name=["\']macroId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            name_param = re.search(r'<ac:parameter[^>]*ac:name=["\']name["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            # Paramètres alternatifs DC
            filename_param = re.search(r'<ac:parameter[^>]*ac:name=["\']filename["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            id_param = re.search(r'<ac:parameter[^>]*ac:name=["\']id["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            
            att_id = image_att_id.group(1).strip() if image_att_id else None
            diagram_att_id_value = diagram_att_id.group(1).strip() if diagram_att_id else None
            macro_id_value = macro_id.group(1).strip() if macro_id else None
            diagram_name = name_param.group(1).strip() if name_param else None
            
            # Si on n'a toujours pas d'ID d'attachement ou si c'est 'test' (placeholder DC)
            if not att_id or att_id == 'test':
                if id_param and id_param.group(1).strip() != 'test':
                    att_id = id_param.group(1).strip()
                elif name_param:
                    att_id = name_param.group(1).strip()
                elif filename_param:
                    att_id = filename_param.group(1).strip()
                elif id_param: # Fallback sur 'test'
                    att_id = id_param.group(1).strip()

            if not diagram_att_id_value or diagram_att_id_value == 'test':
                diagram_att_id_value = diagram_att_id.group(1).strip() if diagram_att_id else att_id

            if att_id or diagram_att_id_value:
                gliffy_attachments.append({
                    'attachmentId': att_id,
                    'diagramAttachmentId': diagram_att_id_value,
                    'macroId': macro_id_value,
                    'diagramName': diagram_name,
                    'macroHtml': macro
                })
        
        return gliffy_attachments

    def download_attachment_direct(self, page_id: str, attachment_id: str, is_draft: bool = False) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Télécharge un attachment directement via l'API REST.
        Retourne (content, mime_type, error_msg)
        """
        last_error = None
        try:
            download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id}/download"
            params = {}
            if is_draft:
                params['status'] = 'draft'
            
            # Utiliser un header Accept large pour le téléchargement binaire
            # et outrepasser le Accept: application/json de la session
            headers = {'Accept': '*/*'}
            download_response = self.session.get(download_api_url, params=params, headers=headers, timeout=30)
            
            if download_response.status_code == 200:
                content = download_response.content
                if b'Error 404' not in content and b'Diagram Missing' not in content:
                    content_type = download_response.headers.get('content-type', '').lower()
                    mime_type = 'application/octet-stream'
                    if 'svg' in content_type or content.startswith(b'<svg'):
                        mime_type = 'image/svg+xml'
                    elif 'png' in content_type or content.startswith(b'\x89PNG'):
                        mime_type = 'image/png'
                    elif 'image/' in content_type:
                        mime_type = content_type
                    return (content, mime_type, None)
                else:
                    last_error = f"Contenu invalide (404/Missing) pour {attachment_id}"
            else:
                last_error = f"HTTP {download_response.status_code}"
            
            if attachment_id.startswith('att'):
                attachment_id_no_prefix = attachment_id[3:]
                download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id_no_prefix}/download"
                download_response = self.session.get(download_api_url, params=params, headers=headers, timeout=30)
                
                if download_response.status_code == 200:
                    content = download_response.content
                    if b'Error 404' not in content and b'Diagram Missing' not in content:
                        content_type = download_response.headers.get('content-type', '').lower()
                        mime_type = 'application/octet-stream'
                        if 'svg' in content_type or content.startswith(b'<svg'):
                            mime_type = 'image/svg+xml'
                        elif 'png' in content_type or content.startswith(b'\x89PNG'):
                            mime_type = 'image/png'
                        elif 'image/' in content_type:
                            mime_type = content_type
                        return (content, mime_type, None)
                    else:
                        last_error = f"Contenu invalide (404/Missing) pour {attachment_id_no_prefix}"
                else:
                    last_error = f"HTTP {download_response.status_code} (avec et sans préfixe 'att')"
            
            return (None, None, last_error or "Échec")
            
        except Exception as e:
            return (None, None, f"Exception: {str(e)}")

    def download_gliffy_json(self, page_id: str, diagram_attachment_id: str, is_draft: bool = False) -> Optional[dict]:
        """Télécharge le fichier .gliffy JSON."""
        if not diagram_attachment_id:
            return None
        
        page_ids_to_try = [page_id]
        attachment_ids_to_try = [diagram_attachment_id]
        
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
                            if isinstance(gliffy_data, dict) and (gliffy_data.get('stage') or gliffy_data.get('pages')):
                                return gliffy_data
                        except json.JSONDecodeError:
                            pass
                    
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
                except Exception:
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
                new_body = current_body[:insert_position] + image_html + current_body[insert_position:]
            else:
                new_body = current_body + image_html
            
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
        except Exception:
            pass
        return (False, None)

    def process_page(self, page: Dict, space_name: str) -> None:
        """Traite une page : trouve les Gliffy, télécharge, insère et convertit."""
        page_id = page.get('id')
        page_title = page.get('title', 'Sans titre')
        space_key = page.get('space', {}).get('key', 'unknown')
        body_storage = page.get('body', {}).get('storage', {}).get('value', '')
        is_draft = page.get('status') == 'draft'
        
        self.stats['pages_analyzed'] += 1
        
        gliffy_attachments = self.extract_gliffy_attachments_from_content(body_storage)
        
        if not gliffy_attachments:
            return
        
        self.stats['pages_with_gliffy'] += 1
        self.stats['gliffy_found'] += len(gliffy_attachments)
        
        print(f"  📄 Page: '{page_title}' (ID: {page_id})")
        print(f"     {len(gliffy_attachments)} Gliffy trouvé(s)")
        
        current_page_body = None
        
        for idx, gliffy_att in enumerate(gliffy_attachments):
            attachment_id = gliffy_att.get('attachmentId')
            macro_id = gliffy_att.get('macroId')
            diagram_name = gliffy_att.get('diagramName')
            
            if attachment_id:
                print(f"     Téléchargement Gliffy {idx + 1}/{len(gliffy_attachments)} (Attachment: {attachment_id})...", end='')
            elif macro_id:
                print(f"     Téléchargement Gliffy {idx + 1}/{len(gliffy_attachments)} (MacroId: {macro_id[:8]}...)...", end='')
            else:
                continue
            
            result = None
            container_id = None
            
            if attachment_id:
                macro_html = gliffy_att.get('macroHtml', '')
                if macro_html:
                    container_match = re.search(r'<ac:parameter[^>]*ac:name=["\']containerId["\'][^>]*>([^<]+)</ac:parameter>', macro_html, re.IGNORECASE)
                    if container_match:
                        container_id = container_match.group(1).strip()
                
                if container_id and container_id != page_id:
                    image_content, mime_type, download_error = self.download_attachment_direct(container_id, attachment_id, False)
                    if not image_content:
                        image_content, mime_type, download_error = self.download_attachment_direct(container_id, attachment_id, True)
                    
                    if not image_content and attachment_id.startswith('att'):
                        attachment_id_no_prefix = attachment_id[3:]
                        image_content, mime_type, download_error = self.download_attachment_direct(container_id, attachment_id_no_prefix, False)
                        if not image_content:
                            image_content, mime_type, download_error = self.download_attachment_direct(container_id, attachment_id_no_prefix, True)
                    
                    if image_content:
                        result = (image_content, mime_type)
                
                if not result:
                    image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id, is_draft=is_draft)
                    if not image_content and is_draft:
                        image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id, True)
                    
                    if not image_content and attachment_id.startswith('att'):
                        attachment_id_no_prefix = attachment_id[3:]
                        image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id_no_prefix, is_draft=is_draft)
                        if not image_content and is_draft:
                            image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id_no_prefix, True)
                    
                    if image_content:
                        result = (image_content, mime_type)
            
            if result:
                image_content, mime_type = result
                print(f" ✅")
                
                # Insérer l'image dans Confluence
                print(f"     Insertion de l'image dans le contenu de la page ({mime_type})...", end='')
                
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
                    print(f" ✅")
                    current_page_body = updated_body
                    self.stats['gliffy_downloaded'] += 1
                else:
                    print(f" ⚠️")
                
                # Conversion Gliffy → Excalidraw
                diagram_attachment_id = gliffy_att.get('diagramAttachmentId')
                if diagram_attachment_id:
                    print(f"     Conversion Gliffy → Excalidraw...", end='')
                    try:
                        json_page_id = page_id
                        if container_id and container_id != page_id:
                            json_page_id = container_id
                        
                        gliffy_json = self.download_gliffy_json(json_page_id, diagram_attachment_id, is_draft=is_draft)
                        
                        if not gliffy_json and json_page_id != page_id:
                            gliffy_json = self.download_gliffy_json(page_id, diagram_attachment_id, is_draft=is_draft)
                        
                        if not gliffy_json and is_draft:
                            gliffy_json = self.download_gliffy_json(json_page_id, diagram_attachment_id, is_draft=False)
                            if not gliffy_json and json_page_id != page_id:
                                gliffy_json = self.download_gliffy_json(page_id, diagram_attachment_id, is_draft=False)
                        
                        if gliffy_json and isinstance(gliffy_json, dict):
                            from gliffy_to_excalidraw import convert_gliffy_to_excalidraw
                            try:
                                from tid_image_mapper import TIDImageMapper
                                tid_mapper = TIDImageMapper()
                            except (ImportError, Exception):
                                tid_mapper = None
                            
                            excalidraw_data = convert_gliffy_to_excalidraw(gliffy_json, tid_image_mapper=tid_mapper)
                            
                            if excalidraw_data:
                                excalidraw_content = json.dumps(excalidraw_data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                                
                                safe_page_title = re.sub(r'[^\w\s-]', '', page_title).strip()
                                safe_page_title = re.sub(r'[-\s]+', '_', safe_page_title)
                                
                                if diagram_name:
                                    safe_diagram_name = re.sub(r'[^\w\s-]', '', diagram_name).strip()
                                    safe_diagram_name = re.sub(r'[-\s]+', '_', safe_diagram_name)
                                    excalidraw_filename = f"{safe_page_title}_{page_id}_{safe_diagram_name}.excalidraw"
                                else:
                                    excalidraw_filename = f"{safe_page_title}_{page_id}_gliffy.excalidraw"
                                
                                excalidraw_filepath = self.excalidraw_output_dir / excalidraw_filename
                                with open(excalidraw_filepath, 'wb') as f:
                                    f.write(excalidraw_content)
                                
                                print(f" ✅ Sauvegardé dans output/{excalidraw_filename}")
                                self.stats['excalidraw_saved'] += 1
                            else:
                                print(f" ⚠️ (conversion retournée vide)")
                        else:
                            print(f" ⚠️ (téléchargement .gliffy échoué)")
                    except Exception as e:
                        error_msg = str(e)
                        print(f" ⚠️ (erreur: {error_msg[:50]})")
                        self.stats['errors'] += 1
                else:
                    print(f"     ⚠️ (pas de diagramAttachmentId)")
            else:
                print(f" ❌ (attachment non accessible)")
                self.stats['errors'] += 1
        
        print()

    def run(self):
        """Lance le processus complet."""
        print("🚀 Démarrage du traitement des Gliffy...\n")
        
        spaces = self.get_all_spaces()
        if not spaces:
            print("❌ Aucun espace trouvé")
            return
        
        self.stats['spaces_analyzed'] = len(spaces)
        
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name', space_key)
            
            print(f"\n📁 Espace: {space_name} ({space_key})")
            
            pages = self.get_all_pages(space_key, include_drafts=True)
            print(f"     {len(pages)} page(s) trouvée(s)")
            
            for page in pages:
                try:
                    self.process_page(page, space_name)
                except Exception as e:
                    print(f"     ⚠️ Erreur lors du traitement: {e}")
                    self.stats['errors'] += 1
        
        print("=" * 60)
        print("📊 Statistiques finales:")
        print(f"  • Espaces analysés: {self.stats['spaces_analyzed']}")
        print(f"  • Pages analysées: {self.stats['pages_analyzed']}")
        print(f"  • Pages avec Gliffy: {self.stats['pages_with_gliffy']}")
        print(f"  • Gliffy trouvés: {self.stats['gliffy_found']}")
        print(f"  • Images insérées dans Confluence: {self.stats['gliffy_downloaded']}")
        print(f"  • Fichiers Excalidraw sauvegardés: {self.stats['excalidraw_saved']}")
        print(f"  • Erreurs: {self.stats['errors']}")
        print(f"  • Fichiers Excalidraw dans: {self.excalidraw_output_dir.absolute()}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Traite tous les Gliffy depuis Confluence en un seul script')
    parser.add_argument('--url', required=True, help='URL de base de Confluence')
    parser.add_argument('--username', required=True, help='Nom d\'utilisateur ou email')
    parser.add_argument('--token', required=True, help='Token API Confluence')
    parser.add_argument('--excalidraw-output', default='output', help='Dossier de sortie pour Excalidraw (défaut: output)')
    parser.add_argument('--spaces', nargs='+', help='Espaces spécifiques à traiter (optionnel, tous par défaut)')
    
    args = parser.parse_args()
    
    processor = GliffyProcessor(
        confluence_url=args.url,
        username=args.username,
        api_token=args.token,
        excalidraw_output_dir=args.excalidraw_output,
        spaces=args.spaces
    )
    
    processor.run()


if __name__ == '__main__':
    main()

