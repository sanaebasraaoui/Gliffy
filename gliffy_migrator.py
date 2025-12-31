#!/usr/bin/env python3
"""
Module pour migrer les images Gliffy dans les pages Confluence.

Ce module permet de migrer les images Gliffy (PNG/SVG) depuis les attachments
Confluence et de les insérer directement dans les pages sous les diagrammes Gliffy.

Fonctionnalités :
- Migration idempotente par défaut (ne modifie pas les pages déjà traitées)
- Option --force pour forcer la réinsertion même si déjà présent
- Compression automatique des images trop grandes
- Support des drafts (brouillons)
- Génération de rapports détaillés de migration

Auteur: Sanae Basraoui

⚠️ NOTE : Ce code a été développé rapidement et n'a pas été testé de manière exhaustive. 
Utilisez-le avec prudence et faites des sauvegardes.
"""

import base64
import json
import re
import requests
import io
from html import escape
from typing import List, Dict, Optional, Tuple, Union
from pathlib import Path
from datetime import datetime, timezone
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
        force: bool = False,
    ):
        """
        Initialise le migrateur Gliffy.
        
        Args:
            confluence_url: URL de base de Confluence
            username: Nom d'utilisateur Confluence
            api_token: Token API Confluence
            spaces: Liste des clés d'espaces à traiter (None = tous)
            page_id: ID d'une page spécifique à traiter (None = toutes les pages)
            force: Si True, réinsère les images même si elles existent déjà (défaut: False)
        """
        super().__init__(confluence_url, username, api_token)
        self.spaces_filter = set(spaces) if spaces else None
        self.page_id_filter = page_id
        self.force = force
        
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
        return super().get_all_pages(space_key, include_drafts, expand='body.storage,version')
    
    def get_page_details(self, page_id: str) -> Optional[Dict]:
        """Récupère les détails d'une page spécifique."""
        return super().get_page_details(page_id, expand='body.storage,space,version')
    
    def extract_gliffy_attachments_from_content(self, body_storage: str, page_id: str = "Inconnue") -> List[Dict]:
        """Extrait les IDs d'attachments Gliffy depuis le contenu d'une page."""
        gliffy_attachments = []
        
        gliffy_macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
        gliffy_macros = re.findall(gliffy_macro_pattern, body_storage, re.DOTALL | re.IGNORECASE)
        
        for macro in gliffy_macros:
            # Paramètres standards Cloud
            image_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']imageAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            diagram_att_id = re.search(r'<ac:parameter[^>]*ac:name=["\']diagramAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            
            # Paramètres alternatifs (souvent sur Data Center)
            name_param = re.search(r'<ac:parameter[^>]*ac:name=["\']name["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            filename_param = re.search(r'<ac:parameter[^>]*ac:name=["\']filename["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            id_param = re.search(r'<ac:parameter[^>]*ac:name=["\']id["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            macro_id_param = re.search(r'<ac:parameter[^>]*ac:name=["\']macroId["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            
            att_id = image_att_id.group(1).strip() if image_att_id else None
            diagram_att_id_value = diagram_att_id.group(1).strip() if diagram_att_id else None
            
            # Si on n'a toujours pas d'ID d'attachement ou si c'est 'test' (placeholder DC), on essaie d'utiliser les autres paramètres trouvés
            if not att_id or att_id == 'test':
                if id_param and id_param.group(1).strip() != 'test':
                    att_id = id_param.group(1).strip()
                elif name_param:
                    att_id = name_param.group(1).strip()
                elif filename_param:
                    att_id = filename_param.group(1).strip()
                elif id_param: # Fallback sur 'test' si vraiment rien d'autre
                    att_id = id_param.group(1).strip()

            if not diagram_att_id_value or diagram_att_id_value == 'test':
                if diagram_att_id:
                    diagram_att_id_value = diagram_att_id.group(1).strip()
                else:
                    diagram_att_id_value = att_id

            macro_id_value = macro_id_param.group(1).strip() if macro_id_param else None
            diagram_name = name_param.group(1).strip() if name_param else None
            
            # On ajoute à la liste si on a trouvé AU MOINS une info permettant d'identifier le Gliffy
            if att_id or diagram_att_id_value or diagram_name or macro_id_value:
                # Debug : logger les IDs suspects ou les infos sur DC
                if att_id == 'test' or diagram_att_id_value == 'test' or not (att_id or diagram_att_id_value):
                    print(f"  🔍 Macro Gliffy détectée sur la page '{page_id}':")
                    if image_att_id: print(f"     - imageAttachmentId: {image_att_id.group(1)}")
                    if diagram_att_id: print(f"     - diagramAttachmentId: {diagram_att_id.group(1)}")
                    if name_param: print(f"     - name: {name_param.group(1)}")
                    if filename_param: print(f"     - filename: {filename_param.group(1)}")
                    if id_param: print(f"     - id: {id_param.group(1)}")
                    if macro_id_param: print(f"     - macroId: {macro_id_param.group(1)}")
                    
                    if att_id == 'test' or diagram_att_id_value == 'test':
                        print(f"  ℹ️  Valeur 'test' détectée. Sur Data Center, le script va tenter de résoudre l'image par son nom.")

                gliffy_attachments.append({
                    'attachmentId': att_id,
                    'diagramAttachmentId': diagram_att_id_value or att_id,
                    'macroId': macro_id_value,
                    'diagramName': diagram_name,
                    'macroHtml': macro
                })
        
        return gliffy_attachments
    
    def extract_treatment_date(self, body_storage: str, macro_html: str) -> Optional[datetime]:
        """
        Extrait la date de traitement depuis le marqueur dans la page.
        Retourne None si aucun marqueur trouvé.
        """
        # Échapper la macro pour la recherche
        escaped_macro = re.escape(macro_html)
        
        # Chercher la macro dans le body
        macro_match = re.search(escaped_macro, body_storage, re.DOTALL | re.IGNORECASE)
        if not macro_match:
            return None
        
        # Extraire le texte après la macro (les 2000 premiers caractères)
        after_macro = body_storage[macro_match.end():macro_match.end() + 2000]
        
        # Chercher le marqueur de date de traitement dans un commentaire HTML
        # Format: <!-- GLIFFY_TREATED: 2025-12-30T14:27:19.123456 -->
        # Pattern plus flexible pour gérer les variations d'espacement
        date_patterns = [
            r'<!--\s*GLIFFY_TREATED:\s*([0-9T:\-\.]+)\s*-->',  # Format standard
            r'<!--GLIFFY_TREATED:\s*([0-9T:\-\.]+)-->',  # Sans espaces autour des --
            r'<!--\s*GLIFFY_TREATED:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?)\s*-->',  # Format plus strict
        ]
        
        for date_pattern in date_patterns:
            date_match = re.search(date_pattern, after_macro, re.IGNORECASE)
            if date_match:
                try:
                    date_str = date_match.group(1)
                    # Nettoyer la date et parser
                    date_str = date_str.strip()
                    # Gérer le format avec ou sans timezone
                    if 'Z' in date_str:
                        date_str = date_str.replace('Z', '+00:00')
                    elif '+' not in date_str and '-' not in date_str[-6:]:
                        # Pas de timezone, ajouter UTC
                        date_str = date_str + '+00:00'
                    # Parser la date ISO
                    return datetime.fromisoformat(date_str)
                except (ValueError, AttributeError) as e:
                    # Essayer avec un format plus simple si le parsing complet échoue
                    try:
                        # Format simplifié sans microsecondes ni timezone
                        simple_date_str = date_str.split('.')[0]  # Enlever les microsecondes
                        return datetime.fromisoformat(simple_date_str)
                    except:
                        continue
        
        return None
    
    def find_macro_in_body(self, body_storage: str, gliffy_att: Union[str, Dict]) -> Optional[re.Match]:
        """
        Trouve la macro Gliffy dans le body en utilisant plusieurs stratégies.
        Retourne le match de la macro trouvée ou None.
        """
        if isinstance(gliffy_att, dict):
            macro_html = gliffy_att.get('macroHtml', '')
        else:
            macro_html = gliffy_att

        if not macro_html:
            return None

        # Stratégie 1: Chercher avec la macro exacte
        escaped_macro = re.escape(macro_html)
        macro_match = re.search(escaped_macro, body_storage, re.DOTALL | re.IGNORECASE)
        if macro_match:
            return macro_match
        
        # Stratégie 2: Extraire l'ID de la macro ou du diagramme pour une recherche plus flexible
        macro_id_match = re.search(r'ac:parameter[^>]*ac:name=["\']macroId["\'][^>]*>([^<]+)</ac:parameter>', macro_html, re.IGNORECASE)
        diagram_att_id_match = re.search(r'ac:parameter[^>]*ac:name=["\']diagramAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro_html, re.IGNORECASE)
        image_att_id_match = re.search(r'ac:parameter[^>]*ac:name=["\']imageAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro_html, re.IGNORECASE)
        
        macro_id = macro_id_match.group(1).strip() if macro_id_match else None
        diagram_att_id = diagram_att_id_match.group(1).strip() if diagram_att_id_match else None
        image_att_id = image_att_id_match.group(1).strip() if image_att_id_match else None
        
        # Chercher toutes les macros Gliffy
        gliffy_macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
        all_macros = list(re.finditer(gliffy_macro_pattern, body_storage, re.DOTALL | re.IGNORECASE))
        
        if not all_macros:
            return None
        
        # Si on a un macroId, chercher la macro correspondante (le plus fiable)
        if macro_id:
            for macro in all_macros:
                macro_content = macro.group(0)
                # Chercher le macroId dans cette macro
                macro_id_in_content = re.search(r'ac:parameter[^>]*ac:name=["\']macroId["\'][^>]*>([^<]+)</ac:parameter>', macro_content, re.IGNORECASE)
                if macro_id_in_content and macro_id_in_content.group(1).strip() == macro_id:
                    return macro
        
        # Si on a un diagramAttachmentId ou imageAttachmentId, chercher la macro correspondante
        if diagram_att_id or image_att_id:
            for macro in all_macros:
                macro_content = macro.group(0)
                # Chercher les IDs dans cette macro
                diagram_id_in_content = re.search(r'ac:parameter[^>]*ac:name=["\']diagramAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro_content, re.IGNORECASE)
                image_id_in_content = re.search(r'ac:parameter[^>]*ac:name=["\']imageAttachmentId["\'][^>]*>([^<]+)</ac:parameter>', macro_content, re.IGNORECASE)
                
                diagram_id_value = diagram_id_in_content.group(1).strip() if diagram_id_in_content else None
                image_id_value = image_id_in_content.group(1).strip() if image_id_in_content else None
                
                if (diagram_att_id and diagram_id_value == diagram_att_id) or (image_att_id and image_id_value == image_att_id):
                    return macro
        
        # Sinon, utiliser la première macro trouvée (on suppose qu'on traite dans l'ordre)
        return all_macros[0] if all_macros else None
    
    def is_page_already_processed(self, body_storage: str, gliffy_att: Dict) -> Tuple[bool, Optional[str]]:
        """
        Vérifie si cette macro spécifique a déjà été traitée.
        """
        macro_match = self.find_macro_in_body(body_storage, gliffy_att)
        if not macro_match:
            return False, None
            
        # Extraire le texte après la macro
        after_macro_start = macro_match.end()
        after_macro_full = body_storage[after_macro_start:]
        
        # Trouver la fin du bloc de cette macro (jusqu'à la prochaine macro Gliffy)
        # On limite la recherche pour ne pas détecter l'image d'un AUTRE Gliffy plus loin sur la page
        next_macro_match = re.search(r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\']', after_macro_full, re.IGNORECASE)
        if next_macro_match:
            after_macro = after_macro_full[:next_macro_match.start()]
        else:
            # Si pas d'autre macro, on limite à 5000 caractères après la macro
            after_macro = after_macro_full[:5000]
        
        # ID à chercher
        att_id = gliffy_att.get('attachmentId')
        diag_id = gliffy_att.get('diagramAttachmentId')
        
        # Stratégie 1 : Chercher l'ID unique dans le bloc (le plus fiable)
        if att_id and f"ID:{att_id}" in after_macro:
            return True, "id_found_in_alt"
        if diag_id and f"ID:{diag_id}" in after_macro:
            return True, "diag_id_found_in_alt"
            
        # Stratégie 2 : Chercher le marqueur de traitement dans CE bloc précis
        if "GLIFFY_TREATED:" in after_macro:
            return True, "marker_found"
                
        # Stratégie 3 : Pattern d'image standard avec data:image dans CE bloc
        if 'src="data:image/' in after_macro or "src='data:image/" in after_macro:
            return True, "image_found_directly_after"
                
        return False, None
    
    def remove_existing_image(self, body_storage: str, gliffy_att: Dict) -> str:
        """
        Supprime l'image existante après la macro Gliffy.
        """
        macro_match = self.find_macro_in_body(body_storage, gliffy_att)
        if not macro_match:
            return body_storage
            
        after_macro_start = macro_match.end()
        after_macro = body_storage[after_macro_start:after_macro_start + 5000]
        
        # Pattern pour supprimer le bloc complet (marqueur + paragraphe avec image)
        # On cherche un paragraphe qui contient une image data:image
        block_pattern = r'(?:<!--\s*GLIFFY_TREATED:[^>]*-->[\s\n]*)?<p><strong>📊?\s*Diagramme\s+Gliffy[^<]*</strong>.*?<img[^>]*src=["\']data:image/[^"\']*;base64,[^"\']*["\'][^>]*>.*?</p>'
        
        match = re.search(block_pattern, after_macro, re.IGNORECASE | re.DOTALL)
        if match:
            # Vérifier qu'aucune autre macro n'est au milieu
            between_text = after_macro[:match.start()]
            if "<ac:structured-macro" not in between_text:
                return body_storage[:after_macro_start + match.start()] + body_storage[after_macro_start + match.end():]
                
        return body_storage
    
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
                    last_error = f"Contenu invalide (404/Missing) pour l'attachment {attachment_id}"
            else:
                last_error = f"HTTP {download_response.status_code}"
            
            # Essayer sans le préfixe 'att'
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
                        last_error = f"Contenu invalide (404/Missing) pour l'attachment {attachment_id_no_prefix}"
                else:
                    last_error = f"HTTP {download_response.status_code} (avec et sans préfixe 'att')"
            
            # Nouveau fallback pour Data Center : si l'ID n'est pas numérique, essayer de trouver par nom
            if attachment_id and not attachment_id.isdigit() and not attachment_id.startswith('att'):
                print(f"     🔍 Recherche de l'attachment par nom '{attachment_id}' (Data Center fallback)...")
                page_attachments = self.get_attachments(page_id)
                
                # Nettoyer le nom au cas où (supprimer les éventuels tags HTML si mal extraits)
                search_name = attachment_id.strip()
                
                # Chercher une correspondance exacte d'abord
                for att in page_attachments:
                    title = att.get('title', '')
                    if title == search_name or title == f"{search_name}.png" or title == f"{search_name}.svg" or title == f"{search_name}.gliffy":
                        att_real_id = att.get('id')
                        if att_real_id:
                            print(f"     ✅ Trouvé ID {att_real_id} pour '{title}'")
                            return self.download_attachment_direct(page_id, att_real_id, is_draft)
                
                # Sinon chercher si le nom est contenu dans le titre (plus souple)
                for att in page_attachments:
                    title = att.get('title', '').lower()
                    sn_lower = search_name.lower()
                    if (sn_lower in title) and (title.endswith('.png') or title.endswith('.svg') or title.endswith('.gliffy')):
                        att_real_id = att.get('id')
                        if att_real_id:
                            print(f"     ✅ Trouvé ID {att_real_id} par recherche souple pour '{att.get('title')}'")
                            return self.download_attachment_direct(page_id, att_real_id, is_draft)
                
                print(f"     ❌ Impossible de trouver un attachment correspondant à '{search_name}'")
            
            return (None, None, last_error or "Échec du téléchargement")
            
        except requests.exceptions.Timeout:
            return (None, None, "Timeout (30s)")
        except requests.exceptions.RequestException as e:
            return (None, None, f"Erreur réseau: {str(e)}")
        except Exception as e:
            return (None, None, f"Exception: {str(e)}")
    
    def insert_image_after_macro(
        self,
        page_id: str,
        page_title: str,
        space_key: str,
        image_content: bytes,
        mime_type: str,
        gliffy_att: Dict,
        is_draft: bool = False,
        current_body: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Insère une image PNG après la macro Gliffy."""
        try:
            attachment_id = gliffy_att.get('attachmentId')
            diagram_name = gliffy_att.get('diagramName')
            macro_html = gliffy_att.get('macroHtml', '')
            
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
            
            # Vérifier idempotence encore une fois juste avant l'insertion
            if not self.force:
                is_processed, reason = self.is_page_already_processed(current_body, gliffy_att)
                if is_processed:
                    return (False, "already_processed")
                else:
                    current_body = self.remove_existing_image(current_body, gliffy_att)
            
            # ... (compression code) ...
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            
            # ID unique pour le marquage dans l'alt
            unique_tag = f"[ID:{attachment_id}]"
            if diagram_name:
                escaped_name = escape(diagram_name)
                title_text = f"📊 Diagramme Gliffy exporté: {escaped_name}"
                alt_text = f"Diagramme Gliffy exporté: {escaped_name} {unique_tag}"
            else:
                title_text = "📊 Diagramme Gliffy exporté"
                alt_text = f"Diagramme Gliffy exporté {unique_tag}"
            
            treatment_date = datetime.now(timezone.utc).isoformat()
            treatment_marker = f'<!-- GLIFFY_TREATED: {treatment_date} -->'
            
            image_data_url = f"data:{mime_type};base64,{image_base64}"
            image_html = f'{treatment_marker}\n<p><strong>{title_text}</strong><br/><img src="{image_data_url}" alt="{escape(alt_text)}" title="{escape(alt_text)}" /></p>'
            
            # Trouver la position de la macro
            macro_match = self.find_macro_in_body(current_body, gliffy_att)
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
        
        # Récupérer la date de modification de la page
        page_modified_date = None
        version_info = page.get('version', {})
        if 'when' in version_info:
            try:
                page_modified_date = datetime.fromisoformat(version_info['when'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        if not body_storage:
            return {
                'page_id': page_id,
                'page_title': page_title,
                'status': 'skipped',
                'reason': 'no_content',
                'gliffy_count': 0,
                'images_inserted': 0
            }
        
        gliffy_attachments = self.extract_gliffy_attachments_from_content(body_storage, page_id)
        
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
            macro_id = gliffy_att.get('macroId')
            
            if not attachment_id:
                continue
            
            # Récupérer le contenu à jour
            current_page_data = self.get_page_details(page_id)
            current_body_storage = current_page_data.get('body', {}).get('storage', {}).get('value', '') if current_page_data else body_storage
            
            # Vérifier idempotence
            if not self.force:
                is_processed, reason = self.is_page_already_processed(current_body_storage, gliffy_att)
                if is_processed:
                    already_processed_count += 1
                    continue
            else:
                current_body_storage = self.remove_existing_image(current_body_storage, gliffy_att)
            
            # Télécharger l'image
            image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id, is_draft=is_draft)
            
            if not image_content and is_draft:
                # Réessayer en forçant le status draft si pas déjà fait
                image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id, True)
            
            if not image_content and attachment_id.startswith('att'):
                attachment_id_no_prefix = attachment_id[3:]
                image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id_no_prefix, is_draft=is_draft)
                if not image_content and is_draft:
                    image_content, mime_type, download_error = self.download_attachment_direct(page_id, attachment_id_no_prefix, True)
            
            if image_content:
                # Insérer l'image
                try:
                    insert_success, result_msg = self.insert_image_after_macro(
                        page_id, page_title, space_key, image_content, mime_type,
                        gliffy_att, is_draft, current_body_storage
                    )
                    
                    if insert_success:
                        images_inserted += 1
                        self.stats['images_inserted'] += 1
                        # Ne pas mettre à jour body_storage localement car on récupère depuis l'API à chaque fois
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
                errors.append(f"Gliffy {idx + 1}: Impossible de télécharger l'image (attachment_id: {attachment_id}) - {download_error}")
        
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

