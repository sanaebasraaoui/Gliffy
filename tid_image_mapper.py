#!/usr/bin/env python3
"""
Gestionnaire de mapping TID -> images pour les icônes Gliffy.
"""

import json
import base64
from pathlib import Path
from typing import Dict, Optional

class TIDImageMapper:
    """Gère le mapping entre les TID Gliffy et les images à utiliser dans Excalidraw."""
    
    def __init__(self, mapping_file: str = 'tids_mapping.json', images_dir: str = 'tid_images'):
        self.mapping_file = Path(mapping_file)
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(exist_ok=True)
        self.mapping = self._load_mapping()
    
    def _load_mapping(self) -> Dict:
        """Charge le mapping depuis le fichier JSON."""
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Erreur lors du chargement du mapping: {e}")
                return {}
        return {}
    
    def save_mapping(self):
        """Sauvegarde le mapping dans le fichier JSON."""
        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.mapping, f, indent=2, ensure_ascii=False)
    
    def get_image_for_tid(self, tid: str) -> Optional[str]:
        """Retourne le chemin de l'image pour un TID donné, ou None si pas de mapping."""
        tid_str = str(tid)
        if tid_str in self.mapping:
            image_path = self.mapping[tid_str].get('image_path')
            if image_path:
                # Si c'est un chemin relatif, le convertir en chemin absolu
                image_path_obj = Path(image_path)
                if not image_path_obj.is_absolute():
                    image_path_obj = self.images_dir / image_path_obj
                
                if image_path_obj.exists():
                    return str(image_path_obj)
        return None
    
    def get_image_data_for_tid(self, tid: str) -> Optional[bytes]:
        """Retourne les données bytes de l'image pour un TID donné, ou None si pas de mapping."""
        image_path = self.get_image_for_tid(tid)
        if image_path:
            try:
                with open(image_path, 'rb') as f:
                    return f.read()
            except Exception:
                return None
        return None
    
    def set_image_for_tid(self, tid: str, image_path: str, description: str = ''):
        """Définit une image pour un TID."""
        tid_str = str(tid)
        if tid_str not in self.mapping:
            self.mapping[tid_str] = {'count': 0, 'image_path': None, 'description': ''}
        
        self.mapping[tid_str]['image_path'] = image_path
        if description:
            self.mapping[tid_str]['description'] = description
        self.save_mapping()
    
    def should_use_image(self, tid: str) -> bool:
        """Détermine si un TID doit être converti en image plutôt qu'en forme."""
        tid_str = str(tid)
        if tid_str in self.mapping:
            return self.mapping[tid_str].get('image_path') is not None
        return False

