#!/usr/bin/env python3
"""
Module de conversion Gliffy vers Excalidraw.

Ce module convertit les fichiers Gliffy (.gliffy) au format Excalidraw (.excalidraw).
Il gère la conversion des éléments graphiques, des styles, des textes et des images.

Fonctionnalités :
- Conversion des formes et éléments graphiques Gliffy vers Excalidraw
- Préservation des styles (couleurs, bordures, remplissages)
- Gestion des textes et polices
- Support du mapper TID pour les images d'icônes
- Conversion des coordonnées et transformations

Inspiré du script PowerShell convert-gliffy.ps1.

Auteur: Sanae Basraoui
"""

import json
import re
import random
import time
import math
import base64
from typing import Dict, List, Optional, Tuple, Any
from html import unescape
from bs4 import BeautifulSoup
from pathlib import Path


def get_unix_milliseconds() -> int:
    """Retourne le timestamp Unix courant en millisecondes."""
    return int(time.time() * 1000)


def new_excalidraw_base(element_type: str) -> Dict[str, Any]:
    """Crée la structure de base d'un élément Excalidraw."""
    base = {
        'id': f'{element_type}_{random.randint(100000, 999999)}',
        'type': element_type,
        'x': 0,
        'y': 0,
        'width': 0,
        'height': 0,
        'angle': 0,
        'strokeColor': '#1e1e1e',
        'backgroundColor': 'transparent',
        'fillStyle': 'solid',
        'strokeWidth': 2,
        'strokeStyle': 'solid',
        'roughness': 1,  # Excalidraw utilise 1 par défaut
        'opacity': 100,
        'groupIds': [],
        'frameId': None,  # Ajouter frameId pour compatibilité
        'roundness': None,  # Ajouter roundness pour compatibilité
        'boundElements': None,
        'locked': False,
        'seed': random.randint(100000, 999999),
        'versionNonce': random.randint(100000, 999999),
        'isDeleted': False,
        'link': None,
        'updated': get_unix_milliseconds()
    }
    return base


def get_gliffy_numeric_property(source: Dict, property_name: str, default: float = 0.0) -> float:
    """Récupère une propriété numérique depuis un objet Gliffy."""
    if not source:
        return default
    value = source.get(property_name)
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_gliffy_text_content(gliffy_object: Dict) -> str:
    """Extrait le texte lisible d'un objet Gliffy."""
    if gliffy_object.get('text'):
        return str(gliffy_object['text'])
    
    graphic = gliffy_object.get('graphic', {})
    text_data = graphic.get('Text', {})
    html_content = text_data.get('html', '')
    
    if not html_content:
        return ''
    
    # Utiliser BeautifulSoup pour extraire le texte proprement
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    
    # Nettoyer les espaces multiples mais garder les retours à la ligne
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def get_gliffy_stroke_color(gliffy_object: Dict, default: str = '#1e1e1e') -> str:
    """Récupère la couleur de trait définie dans un objet Gliffy."""
    if gliffy_object.get('strokeColor'):
        return str(gliffy_object['strokeColor'])
    
    graphic = gliffy_object.get('graphic', {})
    if graphic.get('Line') and graphic['Line'].get('strokeColor'):
        return str(graphic['Line']['strokeColor'])
    if graphic.get('Shape') and graphic['Shape'].get('strokeColor'):
        return str(graphic['Shape']['strokeColor'])
    
    return default


def get_gliffy_fill_color(gliffy_object: Dict, default: str = 'transparent') -> str:
    """Détermine la couleur de remplissage d'un objet Gliffy."""
    fill_color = gliffy_object.get('fillColor')
    if fill_color:
        fill_str = str(fill_color)
        if fill_str.lower() in ('none', 'transparent', ''):
            return default
        return fill_str
    
    graphic = gliffy_object.get('graphic')
    if graphic and isinstance(graphic, dict):
        shape = graphic.get('Shape')
        if shape and isinstance(shape, dict) and shape.get('fillColor'):
            fill_str = str(shape['fillColor'])
            if fill_str.lower() in ('none', 'transparent', ''):
                return default
            return fill_str
    
    return default


def get_gliffy_stroke_width(gliffy_object: Dict, default: float = 2.0) -> float:
    """Récupère l'épaisseur de trait d'un objet Gliffy."""
    if gliffy_object.get('strokeWidth') is not None:
        return float(gliffy_object['strokeWidth'])
    
    graphic = gliffy_object.get('graphic')
    if graphic and isinstance(graphic, dict):
        line_data = graphic.get('Line')
        if line_data and isinstance(line_data, dict) and line_data.get('strokeWidth') is not None:
            return float(line_data['strokeWidth'])
        shape_data = graphic.get('Shape')
        if shape_data and isinstance(shape_data, dict) and shape_data.get('strokeWidth') is not None:
            return float(shape_data['strokeWidth'])
    
    return default


def get_gliffy_object_type(gliffy_object: Dict) -> Optional[str]:
    """Détecte le type logique d'un objet Gliffy."""
    if gliffy_object.get('type'):
        return str(gliffy_object['type']).lower()
    
    uid = gliffy_object.get('uid', '')
    if uid:
        uid_lower = str(uid).lower()
        if '.text' in uid_lower:
            return 'text'
        if '.rectangle' in uid_lower or '.square' in uid_lower:
            # Ne pas détecter automatiquement les cercles - seulement si explicitement spécifié
            return 'rectangle'
        if '.ellipse' in uid_lower or '.oval' in uid_lower or '.circle' in uid_lower or '.diamond' in uid_lower:
            return 'ellipse'
        if '.arrow' in uid_lower or '.line' in uid_lower:
            return 'arrow'
    
    graphic = gliffy_object.get('graphic')
    if graphic and isinstance(graphic, dict):
        graphic_type = graphic.get('type', '')
        if graphic_type:
            graphic_type_lower = str(graphic_type).lower()
            if graphic_type_lower == 'text':
                return 'text'
            if graphic_type_lower == 'line':
                return 'arrow'
            if graphic_type_lower == 'shape':
                shape = graphic.get('Shape')
                if shape and isinstance(shape, dict):
                    tid = str(shape.get('tid', '')).lower()
                    if 'ellipse' in tid or 'oval' in tid or 'circle' in tid:
                        return 'ellipse'
                    if 'diamond' in tid:
                        return 'ellipse'  # Les diamants sont traités comme des ellipses en Excalidraw
                # Ne pas détecter automatiquement les cercles - seulement si explicitement spécifié
                return 'rectangle'
    
    # Si aucun type n'est détecté, retourner None (sera converti en rectangle par défaut)
    # Ne pas détecter automatiquement les cercles basés sur les dimensions
    # Le seul fallback acceptable est le rectangle/carré
    return None


def expand_gliffy_objects(objects: List[Dict], offset_x: float = 0.0, offset_y: float = 0.0, parent: Optional[Dict] = None) -> List[Dict]:
    """Aplatit récursivement la hiérarchie Gliffy en coordonnées absolues."""
    result = []
    
    if not objects:
        return result
    
    for obj in objects:
        if not obj or not isinstance(obj, dict):
            continue
        
        # Créer une copie pour éviter de modifier l'original
        obj_copy = dict(obj)
        
        current_x = float(obj_copy.get('x', 0)) + offset_x
        current_y = float(obj_copy.get('y', 0)) + offset_y
        
        # Convertir en coordonnées absolues
        obj_copy['x'] = current_x
        obj_copy['y'] = current_y
        
        # Traiter les points des polylignes
        if obj_copy.get('points'):
            points_copy = []
            for point in obj_copy['points']:
                if isinstance(point, list) and len(point) >= 2:
                    points_copy.append([float(point[0]) + offset_x, float(point[1]) + offset_y])
                else:
                    points_copy.append(point)
            obj_copy['points'] = points_copy
        
        # Détecter le type
        detected_type = get_gliffy_object_type(obj_copy)
        # Toujours stocker le type détecté (même si None) pour le fallback
        obj_copy['_detected_type'] = detected_type
        
        # Stocker l'ordre de superposition (z-index) pour respecter l'ordre avant/arrière-plan
        # Dans Gliffy, order détermine l'ordre de superposition (plus petit = arrière-plan)
        order = obj_copy.get('order')
        if order is None:
            order = 0  # Par défaut, mettre en arrière-plan
        obj_copy['_order'] = int(order)
        
        # Stocker le parent pour les textes enfants
        if parent and isinstance(parent, dict) and parent.get('id') is not None:
            obj_copy['_parentId'] = str(parent['id'])
        
        result.append(obj_copy)
        
        # Traiter les enfants récursivement
        children = obj_copy.get('children', [])
        if children and isinstance(children, list):
            child_offset_x = current_x
            child_offset_y = current_y
            result.extend(expand_gliffy_objects(children, child_offset_x, child_offset_y, obj_copy))
    
    return result


def get_constraint_point(constraint: Dict, object_info: Dict[str, Dict]) -> Optional[Tuple[float, float]]:
    """Résout une contrainte Gliffy en coordonnées absolues."""
    if not constraint or not constraint.get('nodeId'):
        return None
    
    node_id = str(constraint['nodeId'])
    if node_id not in object_info:
        return None
    
    info = object_info[node_id]
    px = float(constraint.get('px', 0.5))
    py = float(constraint.get('py', 0.5))
    
    x = info['x'] + (info['width'] * px)
    y = info['y'] + (info['height'] * py)
    
    return (x, y)


def wrap_text_content(text: str, max_width: float, font_size: float) -> str:
    """Enveloppe le texte pour qu'il rentre dans une largeur maximale."""
    if not text or max_width <= 0 or font_size <= 0:
        return text
    
    # Approximation de la largeur moyenne d'un caractère
    average_char_width = max(3, font_size * 0.6)
    max_chars = int(max_width / average_char_width)
    if max_chars < 1:
        return text
    
    lines = []
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if len(line) <= max_chars:
            lines.append(line)
            continue
        
        words = line.split()
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                    current = word
                else:
                    # Mot plus long que la largeur : découpe forfaitaire
                    offset = 0
                    while offset < len(word):
                        slice_length = min(max_chars, len(word) - offset)
                        lines.append(word[offset:offset + slice_length])
                        offset += slice_length
                    current = ''
        if current:
            lines.append(current)
    
    return '\n'.join(lines)


def get_excalidraw_arrowhead(arrow_code: Optional[int], default: str = 'none') -> str:
    """Convertit un code de flèche Gliffy en type Excalidraw."""
    if arrow_code is None:
        return default
    
    try:
        code = int(arrow_code)
    except (ValueError, TypeError):
        return default
    
    # Codes Gliffy pour les flèches :
    # 0 = aucune flèche
    # 1 = flèche simple
    # 2 = flèche ouverte
    # 3 = flèche remplie
    # 10, 11, 12 = cardinalités ERD (crowfoot, barre double...) - non supportées par Excalidraw
    
    if code == 0 or code in (10, 11, 12):
        return 'none'
    
    # Codes 1, 2, 3, etc. sont tous des flèches
    return 'arrow'


def get_gliffy_tid(gliffy_obj: Dict) -> Optional[str]:
    """Extrait le TID (Type ID) d'un objet Gliffy."""
    graphic = gliffy_obj.get('graphic')
    if graphic and isinstance(graphic, dict):
        shape = graphic.get('Shape')
        if shape and isinstance(shape, dict):
            tid = shape.get('tid')
            if tid:
                return str(tid)
    return None


def _create_excalidraw_image_from_data(gliffy_obj: Dict, image_data: bytes, id_map: Dict[str, str]) -> Optional[Dict]:
    """Crée un élément image Excalidraw depuis un objet Gliffy et des données d'image en mémoire."""
    try:
        # Détecter le type MIME depuis les données
        if image_data.startswith(b'\x89PNG'):
            mime_type = 'image/png'
        elif image_data.startswith(b'\xff\xd8\xff'):
            mime_type = 'image/jpeg'
        elif image_data.startswith(b'<svg') or image_data.startswith(b'<?xml'):
            mime_type = 'image/svg+xml'
        else:
            mime_type = 'image/png'  # Par défaut
        
        # Encoder en base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        data_url = f"data:{mime_type};base64,{image_base64}"
        
        # Créer l'élément image Excalidraw
        base = new_excalidraw_base('image')
        base['x'] = float(gliffy_obj.get('x', 0))
        base['y'] = float(gliffy_obj.get('y', 0))
        base['width'] = float(gliffy_obj.get('width', 100))
        base['height'] = float(gliffy_obj.get('height', 100))
        base['angle'] = float(gliffy_obj.get('rotation', 0))
        
        # Propriétés spécifiques aux images
        base['fileId'] = f"image_{random.randint(100000, 999999)}"
        base['scale'] = [1, 1]
        
        # Stocker l'image dans les fichiers du document
        base['_imageData'] = data_url
        
        return base
    except Exception as e:
        print(f"⚠️ Erreur lors de la création de l'image depuis données: {e}")
        return None

def _create_excalidraw_image(gliffy_obj: Dict, image_path: str, id_map: Dict[str, str], image_data: Optional[bytes] = None) -> Optional[Dict]:
    """Crée un élément image Excalidraw depuis un objet Gliffy et un chemin d'image ou des données bytes."""
    try:
        # Si on a déjà les données en bytes, les utiliser directement
        if image_data:
            return _create_excalidraw_image_from_data(gliffy_obj, image_data, id_map)
        
        # Sinon, lire depuis le fichier
        image_file = Path(image_path)
        if not image_file.exists():
            return None
        
        with open(image_file, 'rb') as f:
            image_data = f.read()
        
        # Utiliser la fonction générique avec les données
        return _create_excalidraw_image_from_data(gliffy_obj, image_data, id_map)
    except Exception as e:
        print(f"⚠️ Erreur lors de la création de l'image: {e}")
        return None


def convert_gliffy_to_excalidraw(gliffy_data: Dict, tid_image_mapper=None) -> Dict:
    """Convertit un fichier Gliffy JSON en Excalidraw JSON."""
    if not gliffy_data:
        return _create_empty_excalidraw()
    
    # Importer le mapper si disponible
    if tid_image_mapper is None:
        try:
            from tid_image_mapper import TIDImageMapper
            tid_image_mapper = TIDImageMapper()
        except ImportError:
            tid_image_mapper = None
    
    elements = []
    id_map = {}  # Gliffy ID -> Excalidraw ID
    element_registry = {}  # Gliffy ID -> Excalidraw element
    object_info = {}  # Gliffy ID -> {x, y, width, height}
    arrow_geometries = {}  # Gliffy ID -> {points, startArrow, endArrow}
    image_files = {}  # fileId -> image data
    
    # Récupérer les objets depuis la structure Gliffy
    objects = []
    if gliffy_data.get('stage') and gliffy_data['stage'].get('objects'):
        objects = expand_gliffy_objects(gliffy_data['stage']['objects'])
    elif gliffy_data.get('pages'):
        for page in gliffy_data['pages']:
            if page and page.get('scene') and page['scene'].get('objects'):
                objects.extend(expand_gliffy_objects(page['scene']['objects']))
    
    if not objects:
        return _create_empty_excalidraw()
    
    # Construire object_info pour les contraintes
    for obj in objects:
        obj_id = obj.get('id')
        if obj_id is not None:
            obj_id_str = str(obj_id)
            object_info[obj_id_str] = {
                'x': float(obj.get('x', 0)),
                'y': float(obj.get('y', 0)),
                'width': float(obj.get('width', 0)),
                'height': float(obj.get('height', 0))
            }
    
    # Première passe : créer toutes les formes (rectangles, ellipses, images, etc.) d'abord
    # pour que leurs IDs soient disponibles pour les textes enfants
    for obj in objects:
        if not obj or not isinstance(obj, dict):
            continue
        if obj.get('hidden', False):
            continue
        
        obj_type = obj.get('_detected_type') or get_gliffy_object_type(obj)
        
        # Ignorer les textes et les flèches dans cette passe (ils seront traités plus tard)
        if obj_type == 'text' or obj_type == 'arrow':
            continue
        
        obj_id = obj.get('id')
        
        # Vérifier si cet objet doit être converti en image (basé sur le TID)
        tid = get_gliffy_tid(obj)
        use_image = False
        image_path = None
        image_data = None
        
        if tid_image_mapper and tid:
            if tid_image_mapper.should_use_image(tid):
                # Essayer d'abord de récupérer les données bytes directement
                image_data = tid_image_mapper.get_image_data_for_tid(tid)
                if image_data:
                    use_image = True
                else:
                    # Fallback sur le chemin de fichier
                    image_path = tid_image_mapper.get_image_for_tid(tid)
                    if image_path:
                        use_image = True
        
        try:
            if use_image:
                # Convertir en image Excalidraw (avec bytes si disponible, sinon chemin)
                element = _create_excalidraw_image(obj, image_path or '', id_map, image_data=image_data)
                
                if element:
                    elements.append(element)
                    if obj_id is not None:
                        id_map[str(obj_id)] = element['id']
                        element_registry[str(obj_id)] = element
                    
                    # Stocker l'image dans les fichiers du document
                    file_id = element.get('fileId')
                    if file_id and '_imageData' in element:
                        image_files[file_id] = {
                            'mimeType': element['_imageData'].split(';')[0].split(':')[1],
                            'dataURL': element['_imageData']
                        }
            elif obj_type == 'rectangle':
                element = _create_excalidraw_rectangle(obj, objects, object_info, id_map)
                if element:
                    elements.append(element)
                    if obj_id is not None:
                        id_map[str(obj_id)] = element['id']
                        element_registry[str(obj_id)] = element
            
            elif obj_type == 'ellipse':
                element = _create_excalidraw_ellipse(obj, objects, object_info, id_map)
                if element:
                    elements.append(element)
                    if obj_id is not None:
                        id_map[str(obj_id)] = element['id']
                        element_registry[str(obj_id)] = element
            else:
                # Si le type n'est pas reconnu OU si c'est un type inattendu, convertir en rectangle par défaut (fallback)
                obj_type = 'rectangle'
                element = _create_excalidraw_rectangle(obj, objects, object_info, id_map)
                if element:
                    elements.append(element)
                    if obj_id is not None:
                        id_map[str(obj_id)] = element['id']
                        element_registry[str(obj_id)] = element
        except Exception as e:
            # Ignorer les erreurs de conversion pour continuer avec les autres objets
            # Mais essayer quand même de créer un rectangle de base si possible avec le texte
            try:
                # Fallback d'urgence : utiliser _create_excalidraw_rectangle pour avoir le texte
                element = _create_excalidraw_rectangle(obj, objects, object_info, id_map)
                if element:
                    elements.append(element)
                    if obj_id is not None:
                        id_map[str(obj_id)] = element['id']
                        element_registry[str(obj_id)] = element
                else:
                    # Si _create_excalidraw_rectangle échoue, créer un rectangle minimal
                    if obj.get('width', 0) > 0 and obj.get('height', 0) > 0:
                        base = new_excalidraw_base('rectangle')
                        base['x'] = float(obj.get('x', 0))
                        base['y'] = float(obj.get('y', 0))
                        base['width'] = float(obj.get('width', 100))
                        base['height'] = float(obj.get('height', 100))
                        base['strokeColor'] = '#000000'
                        base['backgroundColor'] = '#f9f9f9'
                        
                        # Essayer d'extraire le texte même dans le fallback minimal
                        text_content = get_gliffy_text_content(obj)
                        if not text_content:
                            # Chercher dans les enfants
                            # MAIS exclure les textes qui sont des labels de flèches
                            obj_id_str = str(obj_id) if obj_id is not None else None
                            if obj_id_str:
                                for child_obj in objects:
                                    child_parent_id = child_obj.get('_parentId')
                                    if child_parent_id and str(child_parent_id) == obj_id_str:
                                        child_type = get_gliffy_object_type(child_obj)
                                        if child_type == 'text':
                                            # Vérifier si ce texte est un label de flèche
                                            is_arrow_label = False
                                            if child_parent_id:
                                                for parent_obj in objects:
                                                    parent_obj_id = parent_obj.get('id')
                                                    if parent_obj_id and str(parent_obj_id) == str(child_parent_id):
                                                        parent_obj_type = get_gliffy_object_type(parent_obj)
                                                        if parent_obj_type == 'arrow':
                                                            is_arrow_label = True
                                                            break
                                            
                                            # Ne pas inclure les labels de flèches dans les formes
                                            if not is_arrow_label:
                                                child_text = get_gliffy_text_content(child_obj)
                                                if child_text:
                                                    text_content = child_text
                                                    break
                        
                        if text_content:
                            base['text'] = text_content
                            base['fontSize'] = 20
                            base['fontFamily'] = 1
                            base['textAlign'] = 'center'
                            base['verticalAlign'] = 'middle'
                            base['baseline'] = 17
                            base['originalText'] = text_content
                            base['lineHeight'] = 1.25
                        
                        elements.append(base)
                        if obj_id is not None:
                            id_map[str(obj_id)] = base['id']
                            element_registry[str(obj_id)] = base
            except:
                pass
            continue
    
    # Préparer arrow_geometries AVANT de créer les textes pour que les labels de flèches soient détectés
    # Parcourir les flèches et stocker leurs géométries sans créer les éléments Excalidraw
    for obj in objects:
        if not obj or not isinstance(obj, dict):
            continue
        if obj.get('hidden', False):
            continue
        
        obj_type = obj.get('_detected_type') or get_gliffy_object_type(obj)
        if obj_type != 'arrow':
            continue
        
        obj_id = obj.get('id')
        if obj_id is None:
            continue
        
        obj_id_str = str(obj_id)
        
        # Récupérer les points de la ligne
        points = []
        graphic = obj.get('graphic')
        line_data = {}
        if graphic and isinstance(graphic, dict):
            if graphic.get('type') == 'Line':
                line_data = graphic.get('Line', {}) or {}
            else:
                line_data = graphic.get('Line', {}) or {}
        
        control_path = line_data.get('controlPath', []) if isinstance(line_data, dict) else []
        
        if control_path:
            obj_x = float(obj.get('x', 0))
            obj_y = float(obj.get('y', 0))
            for point in control_path:
                if isinstance(point, list) and len(point) >= 2:
                    points.append([obj_x + float(point[0]), obj_y + float(point[1])])
        
        # Si pas de controlPath, utiliser les contraintes
        if not points:
            constraints = obj.get('constraints', {})
            if constraints:
                start_constraint = constraints.get('startConstraint', {})
                end_constraint = constraints.get('endConstraint', {})
                
                if start_constraint:
                    start_constraint_data = start_constraint.get('StartPositionConstraint', {})
                    start_point = get_constraint_point(start_constraint_data, object_info)
                    if start_point:
                        points.append(list(start_point))
                
                if end_constraint:
                    end_constraint_data = end_constraint.get('EndPositionConstraint', {})
                    end_point = get_constraint_point(end_constraint_data, object_info)
                    if end_point:
                        points.append(list(end_point))
        
        if len(points) >= 2:
            # Stocker la géométrie pour les labels
            arrow_geometries[obj_id_str] = {
                'points': points,
                'startArrow': line_data.get('startArrow', 0) if isinstance(line_data, dict) else 0,
                'endArrow': line_data.get('endArrow', 0) if isinstance(line_data, dict) else 0
            }
    
    # Deuxième passe : créer les textes maintenant que les formes sont créées
    # Les textes enfants utiliseront containerId pour s'intégrer dans les formes
    for obj in objects:
        if not obj or not isinstance(obj, dict):
            continue
        if obj.get('hidden', False):
            continue
        
        obj_type = obj.get('_detected_type') or get_gliffy_object_type(obj)
        if obj_type != 'text':
            continue
        
        obj_id = obj.get('id')
        
        try:
            element = _create_excalidraw_text(obj, object_info, arrow_geometries, id_map)
            if element:
                elements.append(element)
                if obj_id is not None:
                    id_map[str(obj_id)] = element['id']
                    element_registry[str(obj_id)] = element
        except Exception as e:
            # Ignorer les erreurs de conversion pour continuer avec les autres objets
            continue
    
    # Deuxième passe : créer les lignes avec leurs contraintes
    for obj in objects:
        if not obj or not isinstance(obj, dict):
            continue
        if obj.get('hidden', False):
            continue
        
        obj_type = obj.get('_detected_type') or get_gliffy_object_type(obj)
        if obj_type != 'arrow':
            continue
        
        try:
            element = _create_excalidraw_line(obj, object_info, id_map, element_registry, arrow_geometries)
            if element:
                elements.append(element)
                obj_id = obj.get('id')
                if obj_id is not None:
                    id_map[str(obj_id)] = element['id']
                    element_registry[str(obj_id)] = element
                
                # Ajouter la flèche dans boundElements des formes connectées
                start_binding = element.get('startBinding')
                end_binding = element.get('endBinding')
                
                if start_binding:
                    start_element_id = start_binding.get('elementId')
                    # Trouver l'élément de forme correspondant et ajouter la flèche dans boundElements
                    for shape_element in elements:
                        if shape_element.get('id') == start_element_id:
                            if shape_element.get('boundElements') is None:
                                shape_element['boundElements'] = []
                            shape_element['boundElements'].append({
                                'id': element['id'],
                                'type': 'arrow'
                            })
                            break
                
                if end_binding:
                    end_element_id = end_binding.get('elementId')
                    # Trouver l'élément de forme correspondant et ajouter la flèche dans boundElements
                    for shape_element in elements:
                        if shape_element.get('id') == end_element_id:
                            if shape_element.get('boundElements') is None:
                                shape_element['boundElements'] = []
                            shape_element['boundElements'].append({
                                'id': element['id'],
                                'type': 'arrow'
                            })
                            break
        except Exception as e:
            # Ignorer les erreurs de conversion pour continuer avec les autres objets
            continue
    
    # Trier les éléments selon l'ordre de superposition (z-index) de Gliffy
    # Les éléments avec un order plus petit doivent être en arrière-plan (d'abord dans le tableau)
    # Les éléments avec un order plus grand doivent être en avant-plan (après dans le tableau)
    # Dans Excalidraw, l'ordre du tableau détermine l'ordre de superposition
    def get_element_order(element):
        # Récupérer l'ordre depuis l'objet Gliffy original via l'ID
        element_id = element.get('id', '')
        for obj in objects:
            obj_id = obj.get('id')
            if obj_id is not None:
                obj_id_str = str(obj_id)
                if obj_id_str in id_map and id_map[obj_id_str] == element_id:
                    return obj.get('_order', 0)
        return 0  # Par défaut, mettre en arrière-plan
    
    elements.sort(key=get_element_order)
    
    excalidraw_doc = _create_empty_excalidraw()
    excalidraw_doc['elements'] = elements
    
    # Ajouter les fichiers d'images si disponibles
    if image_files:
        excalidraw_doc['files'] = image_files
    
    # Calculer le viewport pour centrer le diagramme
    if elements:
        try:
            all_x = []
            all_y = []
            
            for elem in elements:
                elem_type = elem.get('type')
                if elem_type == 'arrow':
                    points = elem.get('points', [])
                    if points:
                        start_x = elem.get('x', 0)
                        start_y = elem.get('y', 0)
                        for point in points:
                            if isinstance(point, list) and len(point) >= 2:
                                all_x.append(start_x + point[0])
                                all_y.append(start_y + point[1])
                else:
                    all_x.append(elem.get('x', 0))
                    all_y.append(elem.get('y', 0))
                    all_x.append(elem.get('x', 0) + elem.get('width', 0))
                    all_y.append(elem.get('y', 0) + elem.get('height', 0))
            
            if all_x and all_y:
                min_x = min(all_x)
                min_y = min(all_y)
                max_x = max(all_x)
                max_y = max(all_y)
                
                center_x = (min_x + max_x) / 2
                center_y = (min_y + max_y) / 2
                
                viewport_width = 1200
                viewport_height = 800
                
                excalidraw_doc['appState']['scrollX'] = center_x - viewport_width / 2
                excalidraw_doc['appState']['scrollY'] = center_y - viewport_height / 2
                
                diagram_width = max_x - min_x
                diagram_height = max_y - min_y
                
                zoom_x = (viewport_width * 0.9) / diagram_width if diagram_width > 0 else 1
                zoom_y = (viewport_height * 0.9) / diagram_height if diagram_height > 0 else 1
                zoom = min(zoom_x, zoom_y, 1.0)
                zoom = max(zoom, 0.2)
                
                excalidraw_doc['appState']['zoom'] = {'value': zoom}
        except Exception:
            pass
    
    return excalidraw_doc


def _create_empty_excalidraw() -> Dict:
    """Crée un document Excalidraw vide."""
    return {
        'type': 'excalidraw',
        'version': 2,
        'source': 'https://excalidraw.com',  # Utiliser la source standard Excalidraw
        'elements': [],
        'appState': {
            'gridSize': None,
            'viewBackgroundColor': '#ffffff'
            # Simplifier appState pour correspondre au format Excalidraw standard
            # Les autres champs peuvent être ajoutés si nécessaire mais ne sont pas requis
        },
        'files': {}
    }


def _create_excalidraw_text(gliffy_obj: Dict, object_info: Dict[str, Dict], arrow_geometries: Dict, id_map: Dict[str, str]) -> Optional[Dict]:
    """Convertit un objet texte Gliffy en élément texte Excalidraw."""
    base = new_excalidraw_base('text')
    
    base['x'] = float(gliffy_obj.get('x', 0))
    base['y'] = float(gliffy_obj.get('y', 0))
    base['width'] = float(gliffy_obj.get('width', 0))
    base['height'] = float(gliffy_obj.get('height', 0))
    base['angle'] = float(gliffy_obj.get('rotation', 0))
    base['backgroundColor'] = 'transparent'
    
    text = get_gliffy_text_content(gliffy_obj)
    if not text:
        return None
    
    base['text'] = text
    base['strokeColor'] = get_gliffy_stroke_color(gliffy_obj, '#000000')
    
    # Déterminer si c'est un label de flèche AVANT d'extraire la taille
    parent_id = gliffy_obj.get('_parentId')
    # arrow_geometries utilise des clés string (obj_id_str), donc convertir parent_id en string
    is_arrow_label = False
    if parent_id is not None:
        parent_id_str = str(parent_id)
        is_arrow_label = parent_id_str in arrow_geometries
    
    # Extraire les styles depuis le HTML
    graphic = gliffy_obj.get('graphic', {})
    text_graphic = graphic.get('Text', {})
    html_content = text_graphic.get('html', '')
    
    # Déterminer la taille par défaut selon le contexte
    # Pour les labels de flèches, utiliser une taille plus petite
    default_font_size = 12 if is_arrow_label else 20  # Plus petit pour les labels de flèches
    
    font_size = default_font_size
    if html_content:
        # Méthode 1 : Utiliser BeautifulSoup pour extraire les styles depuis les balises
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Chercher dans toutes les balises qui ont un style
            for tag in soup.find_all(True):  # Toutes les balises
                style = tag.get('style', '')
                if style:
                    # Chercher font-size dans le style
                    font_size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                    if font_size_match:
                        try:
                            font_size = int(float(font_size_match.group(1)))
                            break
                        except (ValueError, TypeError):
                            continue
        except:
            pass
        
        # Méthode 2 : Si pas trouvé avec BeautifulSoup, chercher dans le HTML brut
        if font_size == default_font_size:
            font_size_patterns = [
                r'font-size:\s*(\d+(?:\.\d+)?)\s*px',  # font-size: 12px ou font-size: 12.5px
                r'font-size:\s*(\d+(?:\.\d+)?)px',      # font-size:12px (sans espace)
                r'style="[^"]*font-size:\s*(\d+(?:\.\d+)?)\s*px[^"]*"',  # Dans un attribut style
            ]
            
            for pattern in font_size_patterns:
                font_size_match = re.search(pattern, html_content, re.IGNORECASE)
                if font_size_match:
                    try:
                        font_size = int(float(font_size_match.group(1)))  # Convertir en int (arrondir)
                        break
                    except (ValueError, TypeError):
                        continue
    
    # Pour les labels de flèches, réduire la taille si elle est trop grande
    # Les labels doivent être plus petits que le texte dans les formes
    # (is_arrow_label a déjà été défini plus haut)
    if is_arrow_label:
        # Pour les labels de flèches, toujours utiliser une taille plus petite (max 12px)
        # même si une taille plus grande a été extraite depuis Gliffy
        font_size = min(font_size, 12)  # Forcer une taille max de 12px pour les labels
    
    base['fontSize'] = font_size
    base['fontFamily'] = 1
    base['textAlign'] = 'center'
    base['verticalAlign'] = 'middle'
    base['baseline'] = int(font_size * 0.85)
    base['originalText'] = text
    base['lineHeight'] = 1.25
    
    # Gérer le texte dans les formes parentes - utiliser containerId pour l'intégrer
    
    if parent_id and str(parent_id) in id_map and not is_arrow_label:
        # Le texte est enfant d'une forme (mais pas une flèche), utiliser containerId pour l'intégrer
        parent_excalidraw_id = id_map[str(parent_id)]
        base['containerId'] = parent_excalidraw_id
        
        # Ajuster la taille et position pour qu'il rentre dans la forme
        if str(parent_id) in object_info:
            parent_info = object_info[str(parent_id)]
            available_width = parent_info['width'] - 20  # Marges
            if available_width > 0:
                base['width'] = available_width
                wrapped_text = wrap_text_content(text, available_width, font_size)
                if wrapped_text:
                    base['text'] = wrapped_text
    else:
        base['containerId'] = None
    
    # Gérer les labels de flèches - ne pas utiliser containerId, positionner manuellement
    if is_arrow_label:
        geometry = arrow_geometries[parent_id]
        points = geometry.get('points', [])
        if points:
            # Positionner au milieu de la flèche
            mid_idx = len(points) // 2
            if mid_idx < len(points):
                mid_point = points[mid_idx]
                
                # Recalculer width/height basé sur le texte et la taille réduite
                # Estimer la largeur du texte (approximatif)
                text_length = len(text.replace('\n', ' '))  # Compter les caractères sans retours à la ligne
                estimated_width = text_length * font_size * 0.6  # Estimation approximative
                base['width'] = min(max(estimated_width, 50), 200)  # Entre 50px et 200px
                base['height'] = max(font_size * 1.5, font_size * (text.count('\n') + 1) * 1.2)  # Ajuster selon le nombre de lignes
                
                base['x'] = mid_point[0] - base['width'] / 2
                base['y'] = mid_point[1] - base['height'] / 2
    
    return base


def _create_excalidraw_rectangle(gliffy_obj: Dict, all_objects: List[Dict], object_info: Dict[str, Dict], id_map: Dict[str, str]) -> Optional[Dict]:
    """Convertit un rectangle Gliffy en élément rectangle Excalidraw."""
    base = new_excalidraw_base('rectangle')
    
    base['x'] = float(gliffy_obj.get('x', 0))
    base['y'] = float(gliffy_obj.get('y', 0))
    
    # S'assurer que width et height ont des valeurs valides (minimum 10 pour être visible)
    width = gliffy_obj.get('width', 0)
    height = gliffy_obj.get('height', 0)
    try:
        width_f = float(width) if width else 0
        height_f = float(height) if height else 0
    except (ValueError, TypeError):
        width_f = 0
        height_f = 0
    
    # Si les dimensions sont invalides ou nulles, utiliser des valeurs par défaut
    if width_f <= 0:
        width_f = 100  # Valeur par défaut pour les formes non reconnues
    if height_f <= 0:
        height_f = 100  # Valeur par défaut pour les formes non reconnues
    
    base['width'] = width_f
    base['height'] = height_f
    base['angle'] = float(gliffy_obj.get('rotation', 0))
    base['strokeColor'] = get_gliffy_stroke_color(gliffy_obj)
    base['backgroundColor'] = get_gliffy_fill_color(gliffy_obj, '#f9f9f9')
    base['strokeWidth'] = get_gliffy_stroke_width(gliffy_obj)
    
    # Gérer les coins arrondis
    graphic = gliffy_obj.get('graphic')
    if graphic and isinstance(graphic, dict):
        shape = graphic.get('Shape')
        if shape and isinstance(shape, dict) and shape.get('cornerRadius'):
            corner_radius = float(shape['cornerRadius'])
            if corner_radius > 0:
                base['roundness'] = {'type': 3, 'value': corner_radius}
    
    # Chercher le texte dans les enfants de cette forme
    obj_id = gliffy_obj.get('id')
    obj_id_str = str(obj_id) if obj_id is not None else None
    text_content = None
    font_size = 20  # Taille par défaut pour le texte dans les formes (pas les labels de flèches)
    
    # D'abord, essayer de récupérer le texte directement depuis l'objet
    # MAIS vérifier que ce n'est pas un label de flèche (si l'objet lui-même est une flèche, ne pas extraire le texte)
    obj_type_check = get_gliffy_object_type(gliffy_obj)
    if obj_type_check != 'arrow':  # Ne pas extraire le texte si l'objet est une flèche
        text_content = get_gliffy_text_content(gliffy_obj)
        # Si on a trouvé du texte directement, essayer d'extraire la taille depuis l'objet lui-même
        if text_content:
            graphic = gliffy_obj.get('graphic', {})
            text_graphic = graphic.get('Text', {})
            html_content = text_graphic.get('html', '')
            if html_content:
                # Extraire la taille de police depuis l'objet
                # Essayer d'abord avec BeautifulSoup
                font_size_found = False
                try:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    for tag in soup.find_all(True):
                        style = tag.get('style', '')
                        if style:
                            font_size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                            if font_size_match:
                                try:
                                    font_size = int(float(font_size_match.group(1)))
                                    font_size_found = True
                                    break
                                except (ValueError, TypeError):
                                    continue
                except:
                    pass
                
                # Si pas trouvé avec BeautifulSoup, chercher dans le HTML brut
                if not font_size_found:
                    font_size_patterns = [
                        r'font-size:\s*(\d+(?:\.\d+)?)\s*px',
                        r'font-size:\s*(\d+(?:\.\d+)?)px',
                        r'style="[^"]*font-size:\s*(\d+(?:\.\d+)?)\s*px[^"]*"',
                    ]
                    
                    for pattern in font_size_patterns:
                        font_size_match = re.search(pattern, html_content, re.IGNORECASE)
                        if font_size_match:
                            try:
                                font_size = int(float(font_size_match.group(1)))
                                font_size_found = True
                                break
                            except (ValueError, TypeError):
                                continue
    
    # Si pas de texte direct, chercher dans les enfants
    if not text_content and obj_id_str:
        for child_obj in all_objects:
            child_parent_id = child_obj.get('_parentId')
            if child_parent_id and str(child_parent_id) == obj_id_str:
                child_type = get_gliffy_object_type(child_obj)
                if child_type == 'text':
                    # Vérifier si ce texte est un label de flèche (son parent est une flèche)
                    # Si c'est le cas, ne pas l'inclure dans la forme
                    is_arrow_label = False
                    if child_parent_id:
                        # Vérifier si le parent est une flèche
                        # Comparer les IDs en string pour éviter les problèmes de type
                        child_parent_id_str = str(child_parent_id)
                        for parent_obj in all_objects:
                            parent_obj_id = parent_obj.get('id')
                            if parent_obj_id is not None:
                                parent_obj_id_str = str(parent_obj_id)
                                if parent_obj_id_str == child_parent_id_str:
                                    parent_obj_type = get_gliffy_object_type(parent_obj)
                                    if parent_obj_type == 'arrow':
                                        is_arrow_label = True
                                        break
                    
                    # Ne pas inclure les labels de flèches dans les formes
                    if not is_arrow_label:
                        child_text = get_gliffy_text_content(child_obj)
                        if child_text:
                            text_content = child_text
                            # Extraire la taille de police depuis l'enfant
                            child_graphic = child_obj.get('graphic', {})
                            child_text_graphic = child_graphic.get('Text', {})
                            html_content = child_text_graphic.get('html', '')
                            if html_content:
                                # Méthode 1 : Utiliser BeautifulSoup pour extraire les styles depuis les balises
                                font_size_found = False
                                try:
                                    soup = BeautifulSoup(html_content, 'html.parser')
                                    for tag in soup.find_all(True):  # Toutes les balises
                                        style = tag.get('style', '')
                                        if style:
                                            font_size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                                            if font_size_match:
                                                try:
                                                    font_size = int(float(font_size_match.group(1)))
                                                    font_size_found = True
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                                except:
                                    pass
                                
                                # Méthode 2 : Si pas trouvé avec BeautifulSoup, chercher dans le HTML brut
                                if not font_size_found:
                                    font_size_patterns = [
                                        r'font-size:\s*(\d+(?:\.\d+)?)\s*px',
                                        r'font-size:\s*(\d+(?:\.\d+)?)px',
                                        r'style="[^"]*font-size:\s*(\d+(?:\.\d+)?)\s*px[^"]*"',
                                    ]
                                    
                                    for pattern in font_size_patterns:
                                        font_size_match = re.search(pattern, html_content, re.IGNORECASE)
                                        if font_size_match:
                                            try:
                                                font_size = int(float(font_size_match.group(1)))
                                                font_size_found = True
                                                break
                                            except (ValueError, TypeError):
                                                continue
                            break
    
    # Ajouter le texte intégré dans la forme
    if text_content:
        # Réduire la taille du texte pour qu'il soit plus petit
        # Appliquer un facteur de réduction de 0.5 pour rendre le texte beaucoup plus petit
        font_size = int(font_size * 0.5)
        # Taille minimale de 8px et maximale de 10px pour que le texte soit petit mais lisible
        if font_size < 8:
            font_size = 8
        if font_size > 10:
            font_size = 10
        
        # Wrapper le texte pour qu'il rentre dans la forme
        available_width = base['width'] - 20  # Marges gauche/droite
        available_height = base['height'] - 20  # Marges haut/bas
        
        if available_width > 0:
            wrapped_text = wrap_text_content(text_content, available_width, font_size)
            base['text'] = wrapped_text
        else:
            base['text'] = text_content
        
        base['fontSize'] = font_size
        base['fontFamily'] = 1
        base['textAlign'] = 'center'
        base['verticalAlign'] = 'middle'
        base['baseline'] = int(font_size * 0.85)
        # S'assurer que fontSize est bien un nombre et non une chaîne
        if isinstance(base['fontSize'], str):
            try:
                base['fontSize'] = int(float(base['fontSize']))
            except (ValueError, TypeError):
                base['fontSize'] = 20
        base['originalText'] = text_content
        base['lineHeight'] = 1.25
    
    return base


def _create_excalidraw_ellipse(gliffy_obj: Dict, all_objects: List[Dict], object_info: Dict[str, Dict], id_map: Dict[str, str]) -> Optional[Dict]:
    """Convertit une ellipse Gliffy en élément ellipse Excalidraw."""
    base = new_excalidraw_base('ellipse')
    
    base['x'] = float(gliffy_obj.get('x', 0))
    base['y'] = float(gliffy_obj.get('y', 0))
    base['width'] = float(gliffy_obj.get('width', 0))
    base['height'] = float(gliffy_obj.get('height', 0))
    base['angle'] = float(gliffy_obj.get('rotation', 0))
    base['strokeColor'] = get_gliffy_stroke_color(gliffy_obj)
    base['backgroundColor'] = get_gliffy_fill_color(gliffy_obj, '#f9f9f9')
    base['strokeWidth'] = get_gliffy_stroke_width(gliffy_obj)
    base['roundness'] = {'type': 2}
    
    # Détecter les cercles : si width ≈ height (à 10% près), c'est un cercle
    width = base['width']
    height = base['height']
    if width > 0 and height > 0:
        ratio = min(width, height) / max(width, height)
        if ratio > 0.9:
            # C'est un cercle, s'assurer que width == height pour un cercle parfait
            avg_size = (width + height) / 2
            base['width'] = avg_size
            base['height'] = avg_size
    
    # Détecter les diamants
    uid = str(gliffy_obj.get('uid', '')).lower()
    if 'diamond' in uid or 'decision' in uid:
        base['type'] = 'diamond'
    
    # Chercher le texte dans les enfants de cette forme
    obj_id = gliffy_obj.get('id')
    obj_id_str = str(obj_id) if obj_id is not None else None
    text_content = None
    font_size = 20  # Taille par défaut pour le texte dans les formes (pas les labels de flèches)
    
    # D'abord, essayer de récupérer le texte directement depuis l'objet
    # MAIS vérifier que ce n'est pas un label de flèche (si l'objet lui-même est une flèche, ne pas extraire le texte)
    obj_type_check = get_gliffy_object_type(gliffy_obj)
    if obj_type_check != 'arrow':  # Ne pas extraire le texte si l'objet est une flèche
        text_content = get_gliffy_text_content(gliffy_obj)
        # Si on a trouvé du texte directement, essayer d'extraire la taille depuis l'objet lui-même
        if text_content:
            graphic = gliffy_obj.get('graphic', {})
            text_graphic = graphic.get('Text', {})
            html_content = text_graphic.get('html', '')
            if html_content:
                # Extraire la taille de police depuis l'objet
                # Essayer d'abord avec BeautifulSoup
                font_size_found = False
                try:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    for tag in soup.find_all(True):
                        style = tag.get('style', '')
                        if style:
                            font_size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                            if font_size_match:
                                try:
                                    font_size = int(float(font_size_match.group(1)))
                                    font_size_found = True
                                    break
                                except (ValueError, TypeError):
                                    continue
                except:
                    pass
                
                # Si pas trouvé avec BeautifulSoup, chercher dans le HTML brut
                if not font_size_found:
                    font_size_patterns = [
                        r'font-size:\s*(\d+(?:\.\d+)?)\s*px',
                        r'font-size:\s*(\d+(?:\.\d+)?)px',
                        r'style="[^"]*font-size:\s*(\d+(?:\.\d+)?)\s*px[^"]*"',
                    ]
                    
                    for pattern in font_size_patterns:
                        font_size_match = re.search(pattern, html_content, re.IGNORECASE)
                        if font_size_match:
                            try:
                                font_size = int(float(font_size_match.group(1)))
                                font_size_found = True
                                break
                            except (ValueError, TypeError):
                                continue
    
    # Si pas de texte direct, chercher dans les enfants
    if not text_content and obj_id_str:
        for child_obj in all_objects:
            child_parent_id = child_obj.get('_parentId')
            if child_parent_id and str(child_parent_id) == obj_id_str:
                child_type = get_gliffy_object_type(child_obj)
                if child_type == 'text':
                    # Vérifier si ce texte est un label de flèche (son parent est une flèche)
                    # Si c'est le cas, ne pas l'inclure dans la forme
                    is_arrow_label = False
                    if child_parent_id:
                        # Vérifier si le parent est une flèche
                        # Comparer les IDs en string pour éviter les problèmes de type
                        child_parent_id_str = str(child_parent_id)
                        for parent_obj in all_objects:
                            parent_obj_id = parent_obj.get('id')
                            if parent_obj_id is not None:
                                parent_obj_id_str = str(parent_obj_id)
                                if parent_obj_id_str == child_parent_id_str:
                                    parent_obj_type = get_gliffy_object_type(parent_obj)
                                    if parent_obj_type == 'arrow':
                                        is_arrow_label = True
                                        break
                    
                    # Ne pas inclure les labels de flèches dans les formes
                    if not is_arrow_label:
                        child_text = get_gliffy_text_content(child_obj)
                        if child_text:
                            text_content = child_text
                            # Extraire la taille de police depuis l'enfant
                            child_graphic = child_obj.get('graphic', {})
                            child_text_graphic = child_graphic.get('Text', {})
                            html_content = child_text_graphic.get('html', '')
                            if html_content:
                                # Méthode 1 : Utiliser BeautifulSoup pour extraire les styles depuis les balises
                                font_size_found = False
                                try:
                                    soup = BeautifulSoup(html_content, 'html.parser')
                                    for tag in soup.find_all(True):  # Toutes les balises
                                        style = tag.get('style', '')
                                        if style:
                                            font_size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                                            if font_size_match:
                                                try:
                                                    font_size = int(float(font_size_match.group(1)))
                                                    font_size_found = True
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                                except:
                                    pass
                                
                                # Méthode 2 : Si pas trouvé avec BeautifulSoup, chercher dans le HTML brut
                                if not font_size_found:
                                    font_size_patterns = [
                                        r'font-size:\s*(\d+(?:\.\d+)?)\s*px',
                                        r'font-size:\s*(\d+(?:\.\d+)?)px',
                                        r'style="[^"]*font-size:\s*(\d+(?:\.\d+)?)\s*px[^"]*"',
                                    ]
                                    
                                    for pattern in font_size_patterns:
                                        font_size_match = re.search(pattern, html_content, re.IGNORECASE)
                                        if font_size_match:
                                            try:
                                                font_size = int(float(font_size_match.group(1)))
                                                font_size_found = True
                                                break
                                            except (ValueError, TypeError):
                                                continue
                            break
    
    # Ajouter le texte intégré dans la forme
    if text_content:
        # Réduire la taille du texte pour qu'il soit plus petit
        # Appliquer un facteur de réduction de 0.5 pour rendre le texte beaucoup plus petit
        font_size = int(font_size * 0.5)
        # Taille minimale de 8px et maximale de 10px pour que le texte soit petit mais lisible
        if font_size < 8:
            font_size = 8
        if font_size > 10:
            font_size = 10
        
        # Wrapper le texte pour qu'il rentre dans la forme
        available_width = base['width'] - 20  # Marges gauche/droite
        available_height = base['height'] - 20  # Marges haut/bas
        
        if available_width > 0:
            wrapped_text = wrap_text_content(text_content, available_width, font_size)
            base['text'] = wrapped_text
        else:
            base['text'] = text_content
        
        base['fontSize'] = font_size
        base['fontFamily'] = 1
        base['textAlign'] = 'center'
        base['verticalAlign'] = 'middle'
        base['baseline'] = int(font_size * 0.85)
        # S'assurer que fontSize est bien un nombre et non une chaîne
        if isinstance(base['fontSize'], str):
            try:
                base['fontSize'] = int(float(base['fontSize']))
            except (ValueError, TypeError):
                base['fontSize'] = 20
        base['originalText'] = text_content
        base['lineHeight'] = 1.25
    
    return base


def _create_excalidraw_line(gliffy_obj: Dict, object_info: Dict[str, Dict], id_map: Dict[str, str], 
                            element_registry: Dict[str, Dict], arrow_geometries: Dict) -> Optional[Dict]:
    """Convertit une ligne Gliffy en élément ligne Excalidraw."""
    # Déterminer si c'est une ligne simple ou une flèche
    # Si les deux extrémités n'ont pas de flèches, utiliser "line" au lieu de "arrow"
    graphic = gliffy_obj.get('graphic', {})
    line_data = graphic.get('Line', {}) if isinstance(graphic, dict) else {}
    start_arrow = line_data.get('startArrow', 0) if isinstance(line_data, dict) else 0
    end_arrow = line_data.get('endArrow', 0) if isinstance(line_data, dict) else 0
    
    # Utiliser "line" si aucune flèche, sinon "arrow"
    element_type = 'line' if (start_arrow == 0 and end_arrow == 0) else 'arrow'
    base = new_excalidraw_base(element_type)
    
    base['strokeColor'] = get_gliffy_stroke_color(gliffy_obj)
    base['backgroundColor'] = 'transparent'
    base['fillStyle'] = 'solid'
    base['strokeWidth'] = get_gliffy_stroke_width(gliffy_obj)
    base['roundness'] = {'type': 2}
    
    # Récupérer les points de la ligne
    points = []
    
    # Récupérer les données de ligne depuis graphic.Line
    graphic = gliffy_obj.get('graphic')
    line_data = {}
    if graphic and isinstance(graphic, dict):
        # Vérifier d'abord si c'est une ligne
        if graphic.get('type') == 'Line':
            line_data = graphic.get('Line', {}) or {}
        else:
            # Essayer quand même de récupérer Line même si type n'est pas 'Line'
            line_data = graphic.get('Line', {}) or {}
    
    control_path = line_data.get('controlPath', []) if isinstance(line_data, dict) else []
    
    if control_path:
        obj_x = float(gliffy_obj.get('x', 0))
        obj_y = float(gliffy_obj.get('y', 0))
        for point in control_path:
            if isinstance(point, list) and len(point) >= 2:
                points.append([obj_x + float(point[0]), obj_y + float(point[1])])
    
    # Si pas de controlPath, utiliser les contraintes
    if not points:
        constraints = gliffy_obj.get('constraints', {})
        if constraints:
            start_constraint = constraints.get('startConstraint', {})
            end_constraint = constraints.get('endConstraint', {})
            
            if start_constraint:
                start_constraint_data = start_constraint.get('StartPositionConstraint', {})
                start_point = get_constraint_point(start_constraint_data, object_info)
                if start_point:
                    points.append(list(start_point))
            
            if end_constraint:
                end_constraint_data = end_constraint.get('EndPositionConstraint', {})
                end_point = get_constraint_point(end_constraint_data, object_info)
                if end_point:
                    points.append(list(end_point))
    
    if len(points) < 2:
        return None
    
    # Récupérer les codes de flèche AVANT de manipuler les points
    start_arrow_code = None
    end_arrow_code = None
    
    # Essayer d'abord depuis line_data (déjà extrait)
    if isinstance(line_data, dict):
        start_arrow_code = line_data.get('startArrow')
        end_arrow_code = line_data.get('endArrow')
    
    # Si pas trouvé, essayer directement depuis graphic
    if (start_arrow_code is None or end_arrow_code is None) and graphic and isinstance(graphic, dict):
        line_data_direct = graphic.get('Line', {})
        if isinstance(line_data_direct, dict):
            if start_arrow_code is None:
                start_arrow_code = line_data_direct.get('startArrow')
            if end_arrow_code is None:
                end_arrow_code = line_data_direct.get('endArrow')
    
    # Valeurs par défaut si toujours None
    if start_arrow_code is None:
        start_arrow_code = 0
    if end_arrow_code is None:
        end_arrow_code = 0
    
    # Convertir en int pour être sûr
    try:
        start_arrow_code = int(start_arrow_code)
    except (ValueError, TypeError):
        start_arrow_code = 0
    
    try:
        end_arrow_code = int(end_arrow_code)
    except (ValueError, TypeError):
        end_arrow_code = 0
    
    # Convertir en points relatifs (Excalidraw utilise des points relatifs au premier point)
    # NE PAS inverser les points - garder l'ordre Gliffy tel quel
    first_point = points[0]
    base['x'] = first_point[0]
    base['y'] = first_point[1]
    
    relative_points = []
    for point in points:
        relative_points.append([point[0] - first_point[0], point[1] - first_point[1]])
    
    base['points'] = relative_points
    # Pour les lignes simples (type "line"), utiliser des points absolus si nécessaire
    # Mais garder les points relatifs pour compatibilité avec Excalidraw standard
    base['lastCommittedPoint'] = relative_points[-1] if relative_points else None
    
    # Calculer width et height
    if len(points) >= 2:
        last_point = points[-1]
        base['width'] = last_point[0] - first_point[0]
        base['height'] = last_point[1] - first_point[1]
    
    # Dans Excalidraw, les flèches sont définies par rapport à l'ordre des points :
    # - startArrowhead = flèche au début (premier point, points[0])
    # - endArrowhead = flèche à la fin (dernier point, points[-1])
    # Mapper directement : startArrow → startArrowhead, endArrow → endArrowhead
    # (Les points sont dans l'ordre Gliffy, mapper directement)
    start_arrow_result = get_excalidraw_arrowhead(start_arrow_code, 'none')
    end_arrow_result = get_excalidraw_arrowhead(end_arrow_code, 'none')
    
    # Dans Excalidraw, 'none' doit être None (pas la chaîne 'none')
    base['startArrowhead'] = None if start_arrow_result == 'none' else start_arrow_result
    base['endArrowhead'] = None if end_arrow_result == 'none' else end_arrow_result
    
    # Gérer les bindings
    # IMPORTANT: Pour les flèches unidirectionnelles, NE PAS mettre de bindings du tout
    # car Excalidraw peut créer une flèche visuelle supplémentaire avec les bindings
    obj_id = gliffy_obj.get('id')
    if obj_id:
        obj_id_str = str(obj_id)
        
        # Récupérer les contraintes
        start_constraint = gliffy_obj.get('constraints', {}).get('startConstraint', {})
        end_constraint = gliffy_obj.get('constraints', {}).get('endConstraint', {})
        
        start_node_id = None
        end_node_id = None
        
        if start_constraint:
            start_constraint_data = start_constraint.get('StartPositionConstraint', {})
            start_node_id = start_constraint_data.get('nodeId')
        
        if end_constraint:
            end_constraint_data = end_constraint.get('EndPositionConstraint', {})
            end_node_id = end_constraint_data.get('nodeId')
        
        # Créer les bindings pour TOUTES les flèches (unidirectionnelles et bidirectionnelles)
        # pour qu'elles suivent les formes quand on les déplace
        # Mettre les bindings même si la flèche n'a pas d'arrowhead à cette extrémité
        # car cela permet à la ligne de suivre la forme
        
        # Binding au début de la flèche
        # Utiliser gap: 0 pour que les bindings soient plus serrés et fonctionnent mieux
        if start_node_id and str(start_node_id) in id_map:
            base['startBinding'] = {
                'elementId': id_map[str(start_node_id)],
                'focus': 0.5,
                'gap': 0  # Gap à 0 pour un binding plus serré
            }
        else:
            base['startBinding'] = None
        
        # Binding à la fin de la flèche
        if end_node_id and str(end_node_id) in id_map:
            base['endBinding'] = {
                'elementId': id_map[str(end_node_id)],
                'focus': 0.5,
                'gap': 0  # Gap à 0 pour un binding plus serré
            }
        else:
            base['endBinding'] = None
        
        # Stocker la géométrie pour les labels
        absolute_points = []
        start_x = base['x']
        start_y = base['y']
        for rel_point in relative_points:
            absolute_points.append([start_x + rel_point[0], start_y + rel_point[1]])
        
        arrow_geometries[obj_id_str] = {
            'points': absolute_points,
            'startArrow': start_arrow_code,
            'endArrow': end_arrow_code
        }
    
    return base

