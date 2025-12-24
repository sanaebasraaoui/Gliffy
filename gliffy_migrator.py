#!/usr/bin/env python3
"""
Module pour migrer les images Gliffy dans les pages Confluence.
Migration idempotente : ne modifie pas les pages déjà traitées.
"""

import base64
import json
import re
import requests
import io
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime
from confluence_base import ConfluenceBase

# Essayer d'importer PIL pour la compression d'images
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class GliffyMigrator(ConfluenceBase):
    """Migrateur idempotent pour copier les images Gliffy sous les diagrammes."""
    
    def __init__(
        self,
        confluence_url: str,
        username: str,
        api_token: str,
        spaces: Optional[List[str]] = None,
        page_id: Optional[str] = None,
    ):
        """
        Initialise le migrateur Gliffy.
        
        Args:
            confluence_url: URL de base de Confluence
            username: Nom d'utilisateur Confluence
            api_token: Token API Confluence
            spaces: Liste des clés d'espaces à traiter (None = tous)
            page_id: ID d'une page spécifique à traiter (None = toutes les pages)
        """
        super().__init__(confluence_url, username, api_token)
        self.spaces_filter = set(spaces) if spaces else None
        self.page_id_filter = page_id
        
        # Statistiques et rapport
        self.stats = {
            'pages_processed': 0,
            'pages_modified': 0,
            'pages_skipped': 0,
            'gliffy_found': 0,
            'images_inserted': 0,
            'errors': 0
        }
        self.report = []
    
    def get_all_spaces(self) -> List[Dict]:
        """Récupère tous les espaces Confluence."""
        print("📂 Récupération de la liste des espaces...")
        spaces = super().get_all_spaces(self.spaces_filter)
        
        if self.spaces_filter:
            print(f"✅ {len(spaces)} espace(s) sélectionné(s)")
        else:
            print(f"✅ {len(spaces)} espace(s) trouvé(s)")
        
        return spaces
    
    def get_all_pages(self, space_key: str, include_drafts: bool = True) -> List[Dict]:
        """Récupère toutes les pages d'un espace."""
        return super().get_all_pages(space_key, include_drafts, expand='body.storage')
    
    def get_page_details(self, page_id: str) -> Optional[Dict]:
        """Récupère les détails d'une page spécifique."""
        return super().get_page_details(page_id, expand='body.storage,space,version')
    
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
    
    def is_page_already_processed(self, body_storage: str, macro_html: str) -> bool:
        """
        Vérifie si une page a déjà été traitée (idempotence).
        On cherche si une image avec le titre du Gliffy existe déjà juste après la macro.
        """
        # Échapper la macro pour la recherche
        escaped_macro = re.escape(macro_html)
        
        # Chercher la macro dans le body
        macro_match = re.search(escaped_macro, body_storage, re.DOTALL | re.IGNORECASE)
        if not macro_match:
            return False
        
        # Extraire le texte après la macro (les 500 premiers caractères)
        after_macro = body_storage[macro_match.end():macro_match.end() + 500]
        
        # Chercher un pattern d'image avec le titre du Gliffy
        # Pattern: <p><strong>📊 Diagramme Gliffy exporté: ...</strong><br/><img ...
        image_pattern = r'<p><strong>📊\s+Diagramme\s+Gliffy\s+exporté[^<]*</strong><br/><img'
        if re.search(image_pattern, after_macro, re.IGNORECASE):
            return True
        
        # Chercher aussi un pattern plus générique
        image_pattern_generic = r'<p><strong>[^<]*Diagramme\s+Gliffy[^<]*</strong><br/><img'
        if re.search(image_pattern_generic, after_macro, re.IGNORECASE):
            return True
        
        return False
    
    def compress_image(self, image_content: bytes, mime_type: str, max_size_bytes: int = 3_500_000) -> Tuple[bytes, str]:
        """
        Compresse et réduit une image si nécessaire pour qu'elle rentre dans la limite de taille.
        
        Args:
            image_content: Contenu de l'image en bytes
            mime_type: Type MIME de l'image
            max_size_bytes: Taille maximale cible en bytes
            
        Returns:
            Tuple (image_content_compressed, mime_type)
        """
        if not PIL_AVAILABLE:
            return (image_content, mime_type)
        
        # Ne compresser que les PNG et JPEG
        if 'png' not in mime_type.lower() and 'jpeg' not in mime_type.lower() and 'jpg' not in mime_type.lower():
            return (image_content, mime_type)
        
        try:
            # Ouvrir l'image
            img = Image.open(io.BytesIO(image_content))
            original_format = img.format
            
            # Si l'image est déjà assez petite, la retourner telle quelle
            if len(image_content) <= max_size_bytes:
                return (image_content, mime_type)
            
            # Calculer le facteur de réduction nécessaire
            size_ratio = (max_size_bytes / len(image_content)) ** 0.5  # Racine carrée pour réduire proportionnellement
            
            # Réduire la taille de l'image (largeur et hauteur)
            new_width = int(img.width * size_ratio)
            new_height = int(img.height * size_ratio)
            
            # S'assurer que les dimensions ne sont pas trop petites (minimum 200px)
            new_width = max(200, new_width)
            new_height = max(200, new_height)
            
            # Redimensionner l'image avec un filtre de qualité
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convertir en RGB si nécessaire (pour JPEG)
            if original_format == 'JPEG' and img_resized.mode != 'RGB':
                img_resized = img_resized.convert('RGB')
            
            # Compresser l'image
            output = io.BytesIO()
            quality = 85  # Qualité initiale
            
            # Essayer différentes qualités jusqu'à obtenir une taille acceptable
            for attempt_quality in [85, 75, 65, 55, 45]:
                output.seek(0)
                output.truncate(0)
                
                if original_format == 'PNG':
                    # Pour PNG, utiliser optimize=True et compress_level
                    img_resized.save(output, format='PNG', optimize=True, compress_level=9)
                else:
                    # Pour JPEG
                    img_resized.save(output, format='JPEG', quality=attempt_quality, optimize=True)
                
                compressed_size = len(output.getvalue())
                if compressed_size <= max_size_bytes:
                    break
                
                # Si toujours trop grand, réduire encore la taille
                if attempt_quality == 45 and compressed_size > max_size_bytes:
                    # Réduire encore plus la taille de l'image
                    size_ratio = (max_size_bytes / compressed_size) ** 0.5
                    new_width = max(200, int(new_width * size_ratio))
                    new_height = max(200, int(new_height * size_ratio))
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    if original_format == 'JPEG' and img_resized.mode != 'RGB':
                        img_resized = img_resized.convert('RGB')
                    output.seek(0)
                    output.truncate(0)
                    if original_format == 'PNG':
                        img_resized.save(output, format='PNG', optimize=True, compress_level=9)
                    else:
                        img_resized.save(output, format='JPEG', quality=45, optimize=True)
            
            compressed_content = output.getvalue()
            compressed_mime_type = 'image/png' if original_format == 'PNG' else 'image/jpeg'
            
            # Vérifier que la compression a fonctionné
            if len(compressed_content) < len(image_content):
                return (compressed_content, compressed_mime_type)
            else:
                # Si la compression n'a pas réduit la taille, retourner l'original
                return (image_content, mime_type)
                
        except Exception as e:
            # En cas d'erreur, retourner l'image originale
            return (image_content, mime_type)
    
    def download_attachment_direct(self, page_id: str, attachment_id: str, is_draft: bool = False) -> Optional[Tuple[bytes, str]]:
        """Télécharge un attachment directement via l'API REST."""
        try:
            download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id}/download"
            params = {}
            if is_draft:
                params['status'] = 'draft'
            
            download_response = self.session.get(download_api_url, params=params, timeout=30)
            
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
            
            # Essayer sans le préfixe 'att'
            if download_response.status_code != 200 and attachment_id.startswith('att'):
                attachment_id_no_prefix = attachment_id[3:]
                download_api_url = f"{self.api_base}/content/{page_id}/child/attachment/{attachment_id_no_prefix}/download"
                download_response = self.session.get(download_api_url, params=params, timeout=30)
                
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
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException as e:
            # Ne pas logger ici pour éviter trop de bruit, mais on pourrait améliorer
            return None
        except Exception as e:
            # Autres exceptions inattendues
            return None
    
    def insert_image_after_macro(
        self,
        page_id: str,
        page_title: str,
        space_key: str,
        image_content: bytes,
        mime_type: str,
        diagram_name: Optional[str],
        macro_html: str,
        is_draft: bool = False,
        current_body: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
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
            
            # Vérifier si déjà traité (idempotence)
            if self.is_page_already_processed(current_body, macro_html):
                return (False, "already_processed")
            
            # Vérifier la taille de l'image (limite Confluence: ~5 MB pour la requête totale)
            # Base64 augmente la taille d'environ 33%, donc on limite à ~3.7 MB pour être sûr
            MAX_IMAGE_SIZE = 3_700_000  # ~3.7 MB en bytes
            image_size = len(image_content)
            
            # Si l'image est trop grande, essayer de la compresser automatiquement
            if image_size > MAX_IMAGE_SIZE:
                if PIL_AVAILABLE:
                    # Compresser automatiquement l'image
                    image_content, mime_type = self.compress_image(image_content, mime_type, MAX_IMAGE_SIZE)
                    image_size = len(image_content)
                    
                    # Si après compression c'est encore trop grand, retourner une erreur
                    if image_size > MAX_IMAGE_SIZE:
                        return (False, f"Image trop grande même après compression ({image_size / 1_000_000:.2f} MB). Limite: {MAX_IMAGE_SIZE / 1_000_000:.2f} MB. Essayez de réduire la taille du diagramme Gliffy.")
                else:
                    return (False, f"Image trop grande ({image_size / 1_000_000:.2f} MB). Limite: {MAX_IMAGE_SIZE / 1_000_000:.2f} MB. Installez Pillow (pip install Pillow) pour activer la compression automatique.")
            
            # Vérifier aussi la taille après encodage base64
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            base64_size = len(image_base64.encode('utf-8'))
            total_request_size = len(current_body.encode('utf-8')) + base64_size + 500  # +500 pour le HTML autour
            
            # Si la requête totale est trop grande, essayer de compresser encore plus
            if total_request_size > 5_000_000:  # 5 MB limite Confluence
                if PIL_AVAILABLE:
                    # Calculer la taille d'image maximale pour que la requête totale soit < 5 MB
                    max_image_base64_size = 5_000_000 - len(current_body.encode('utf-8')) - 500
                    max_image_bytes = int(max_image_base64_size / 1.33)  # Base64 augmente de ~33%
                    
                    # Recompresser avec une limite plus stricte
                    image_content, mime_type = self.compress_image(image_content, mime_type, max_image_bytes)
                    image_base64 = base64.b64encode(image_content).decode('utf-8')
                    base64_size = len(image_base64.encode('utf-8'))
                    total_request_size = len(current_body.encode('utf-8')) + base64_size + 500
                    
                    # Vérifier à nouveau
                    if total_request_size > 5_000_000:
                        return (False, f"Requête trop grande après compression ({total_request_size / 1_000_000:.2f} MB). Limite: 5 MB. La page contient déjà beaucoup de contenu.")
                else:
                    return (False, f"Requête trop grande après encodage ({total_request_size / 1_000_000:.2f} MB). Limite: 5 MB. Installez Pillow (pip install Pillow) pour activer la compression automatique.")
            
            image_data_url = f"data:{mime_type};base64,{image_base64}"
            
            # Créer le titre avec le nom du diagramme
            if diagram_name:
                title_text = f"📊 Diagramme Gliffy exporté: {diagram_name}"
            else:
                title_text = "📊 Diagramme Gliffy exporté"
            
            image_html = f'<p><strong>{title_text}</strong><br/><img src="{image_data_url}" alt="{title_text}" title="{title_text}" /></p>'
            
            # Trouver la position de la macro
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
            elif update_response.status_code == 409:
                # Conflit de version - réessayer avec la version actuelle
                try:
                    current_response = self.session.get(url, params=params)
                    if current_response.status_code == 200:
                        current_data = current_response.json()
                        current_version = current_data.get('version', {}).get('number', version_num)
                        update_data['version'] = {'number': current_version}
                        retry_response = self.session.put(url, json=update_data, params=params)
                        if retry_response.status_code == 200:
                            return (True, new_body)
                        else:
                            return (False, f"Erreur HTTP {retry_response.status_code} lors de la mise à jour (conflit de version)")
                    else:
                        return (False, f"Erreur HTTP {current_response.status_code} lors de la récupération de la version")
                except Exception as e:
                    return (False, f"Exception lors de la gestion du conflit de version: {str(e)}")
            elif update_response.status_code == 403:
                return (False, "Permission refusée (403) - Vérifiez vos droits d'écriture sur cette page")
            elif update_response.status_code == 404:
                return (False, "Page non trouvée (404)")
            elif update_response.status_code == 413:
                # Calculer la taille pour le message d'erreur
                try:
                    base64_size = len(image_base64.encode('utf-8'))
                    size_msg = f"({base64_size / 1_000_000:.2f} MB)"
                except:
                    size_msg = ""
                return (False, f"Requête trop grande (413) - L'image encodée {size_msg} dépasse la limite de 5 MB de Confluence. Solution: réduisez la taille du diagramme Gliffy dans l'éditeur Gliffy ou divisez-le en plusieurs diagrammes plus petits.")
            else:
                try:
                    error_detail = update_response.json().get('message', '')
                    return (False, f"Erreur HTTP {update_response.status_code}: {error_detail}")
                except:
                    return (False, f"Erreur HTTP {update_response.status_code} lors de la mise à jour")
        except requests.exceptions.Timeout:
            return (False, "Timeout lors de la requête API")
        except requests.exceptions.RequestException as e:
            return (False, f"Erreur de connexion: {str(e)}")
        except Exception as e:
            return (False, f"Exception inattendue: {str(e)}")
        
        return (False, "Erreur inconnue lors de l'insertion")
    
    def process_page(self, page: Dict, space_key: str, space_name: str) -> Dict:
        """Traite une page pour migrer les images Gliffy."""
        page_id = page.get('id')
        page_title = page.get('title', 'Sans titre')
        is_draft = page.get('status') == 'draft'
        body_storage = page.get('body', {}).get('storage', {}).get('value', '')
        
        if not body_storage:
            return {
                'page_id': page_id,
                'page_title': page_title,
                'status': 'skipped',
                'reason': 'no_content',
                'gliffy_count': 0,
                'images_inserted': 0
            }
        
        gliffy_attachments = self.extract_gliffy_attachments_from_content(body_storage)
        
        if not gliffy_attachments:
            return {
                'page_id': page_id,
                'page_title': page_title,
                'status': 'skipped',
                'reason': 'no_gliffy',
                'gliffy_count': 0,
                'images_inserted': 0
            }
        
        self.stats['gliffy_found'] += len(gliffy_attachments)
        
        images_inserted = 0
        errors = []
        already_processed_count = 0
        
        for idx, gliffy_att in enumerate(gliffy_attachments):
            attachment_id = gliffy_att.get('attachmentId')
            macro_html = gliffy_att.get('macroHtml', '')
            diagram_name = gliffy_att.get('diagramName')
            
            if not attachment_id:
                continue
            
            # Vérifier si cette macro a déjà été traitée
            if self.is_page_already_processed(body_storage, macro_html):
                already_processed_count += 1
                continue
            
            # Télécharger l'image
            result = self.download_attachment_direct(page_id, attachment_id, is_draft=is_draft)
            
            if not result and is_draft:
                result = self.download_attachment_direct(page_id, attachment_id, True)
            
            if not result and attachment_id.startswith('att'):
                attachment_id_no_prefix = attachment_id[3:]
                result = self.download_attachment_direct(page_id, attachment_id_no_prefix, is_draft=is_draft)
                if not result and is_draft:
                    result = self.download_attachment_direct(page_id, attachment_id_no_prefix, True)
            
            if result:
                image_content, mime_type = result
                
                # Insérer l'image
                try:
                    insert_success, result_msg = self.insert_image_after_macro(
                        page_id, page_title, space_key, image_content, mime_type,
                        diagram_name, macro_html, is_draft, body_storage
                    )
                    
                    if insert_success:
                        images_inserted += 1
                        self.stats['images_inserted'] += 1
                        body_storage = result_msg  # Mettre à jour pour la prochaine itération
                    elif result_msg == "already_processed":
                        # Page déjà traitée, on skip
                        already_processed_count += 1
                    else:
                        error_msg = result_msg if result_msg else "Erreur lors de l'insertion de l'image"
                        errors.append(f"Gliffy {idx + 1}: {error_msg}")
                except Exception as e:
                    error_msg = f"Exception lors de l'insertion: {str(e)}"
                    errors.append(f"Gliffy {idx + 1}: {error_msg}")
            else:
                errors.append(f"Gliffy {idx + 1}: Impossible de télécharger l'image (attachment_id: {attachment_id})")
        
        if images_inserted > 0:
            self.stats['pages_modified'] += 1
            status = 'modified'
            reason = None
        elif errors:
            self.stats['errors'] += len(errors)
            status = 'error'
            reason = 'errors'
        elif already_processed_count == len(gliffy_attachments):
            self.stats['pages_skipped'] += 1
            status = 'skipped'
            reason = 'already_processed'
        else:
            self.stats['pages_skipped'] += 1
            status = 'skipped'
            reason = 'no_images_inserted'
        
        result_dict = {
            'page_id': page_id,
            'page_title': page_title,
            'status': status,
            'gliffy_count': len(gliffy_attachments),
            'images_inserted': images_inserted,
            'errors': errors
        }
        
        if reason:
            result_dict['reason'] = reason
        
        return result_dict
    
    def migrate(self) -> List[Dict]:
        """Lance la migration complète."""
        print("🚀 Démarrage de la migration des images Gliffy\n")
        
        # Si une page spécifique est demandée
        if self.page_id_filter:
            print(f"🎯 Mode: Page spécifique (ID: {self.page_id_filter})\n")
            page_data = self.get_page_details(self.page_id_filter)
            if page_data:
                space = page_data.get('space', {})
                space_key = space.get('key', 'unknown')
                space_name = space.get('name', space_key)
                result = self.process_page(page_data, space_key, space_name)
                self.report.append(result)
                self.stats['pages_processed'] += 1
                print(f"✅ Page traitée: {result['page_title']}")
            else:
                print(f"❌ Page {self.page_id_filter} non trouvée")
            return self.report
        
        # Migration par espace(s)
        if self.spaces_filter:
            print(f"🎯 Mode: Espaces spécifiques ({', '.join(self.spaces_filter)})\n")
        else:
            print(f"🌐 Mode: Tous les espaces\n")
        
        spaces = self.get_all_spaces()
        
        if not spaces:
            print("❌ Aucun espace trouvé")
            return []
        
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name', space_key)
            
            print(f"\n📄 Analyse de l'espace: {space_name} ({space_key})")
            
            pages = self.get_all_pages(space_key, include_drafts=True)
            
            if not pages:
                print(f"  ℹ️  Aucune page trouvée")
                continue
            
            print(f"  📋 {len(pages)} page(s) trouvée(s)")
            
            for page in pages:
                result = self.process_page(page, space_key, space_name)
                self.report.append(result)
                self.stats['pages_processed'] += 1
                
                if result['status'] == 'modified':
                    print(f"  ✅ {result['page_title']}: {result['images_inserted']} image(s) insérée(s)")
                elif result['status'] == 'skipped':
                    reason = result.get('reason', 'unknown')
                    if reason == 'already_processed':
                        print(f"  ⏭️  {result['page_title']}: Déjà traitée ({result['gliffy_count']} Gliffy)")
                    elif reason == 'no_gliffy':
                        print(f"  ⏭️  {result['page_title']}: Aucun Gliffy")
                    elif reason == 'no_content':
                        print(f"  ⏭️  {result['page_title']}: Pas de contenu")
                    else:
                        print(f"  ⏭️  {result['page_title']}: Ignorée ({reason})")
                elif result['status'] == 'error':
                    error_count = len(result.get('errors', []))
                    print(f"  ❌ {result['page_title']}: {error_count} erreur(s)")
        
        print(f"\n✅ Migration terminée")
        return self.report
    
    def export_report(self, output_file: str):
        """Exporte le rapport de migration."""
        if not self.report:
            print("❌ Aucun rapport à exporter")
            return
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'pages': self.report
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Rapport exporté: {output_path.absolute()}")
        
        # Sauvegarder également en format texte lisible
        try:
            from report_utils import export_migration_report_txt
            txt_output_file = Path(output_file).stem + '.txt'
            export_migration_report_txt(report_data, txt_output_file)
        except ImportError:
            pass
        
        # Afficher un résumé
        print(f"\n📊 Résumé:")
        print(f"  • Pages traitées: {self.stats['pages_processed']}")
        print(f"  • Pages modifiées: {self.stats['pages_modified']}")
        print(f"  • Pages ignorées: {self.stats['pages_skipped']}")
        print(f"  • Gliffy trouvés: {self.stats['gliffy_found']}")
        print(f"  • Images insérées: {self.stats['images_inserted']}")
        print(f"  • Erreurs: {self.stats['errors']}")

