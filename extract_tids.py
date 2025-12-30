#!/usr/bin/env python3
"""
Script pour extraire tous les TID (Type ID) uniques depuis les fichiers Gliffy.

Ce module analyse les fichiers Gliffy pour extraire tous les Type IDs (TID) uniques
utilisés dans les diagrammes, permettant de créer un mapping TID -> images.

Fonctionnalités :
- Extraction des TID depuis les fichiers Gliffy
- Comptage des occurrences de chaque TID
- Génération d'un mapping avec statistiques
- Export en format JSON et texte

Auteur: Sanae Basraoui
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set

def extract_tids_from_gliffy(gliffy_data: Dict) -> Set[str]:
    """Extrait tous les TID uniques d'un fichier Gliffy."""
    tids = set()
    
    def process_object(obj):
        """Traite récursivement un objet Gliffy."""
        if not obj or not isinstance(obj, dict):
            return
        
        # Extraire le TID depuis graphic.Shape.tid
        graphic = obj.get('graphic')
        if graphic and isinstance(graphic, dict):
            shape = graphic.get('Shape')
            if shape and isinstance(shape, dict):
                tid = shape.get('tid')
                if tid:
                    tids.add(str(tid))
        
        # Traiter les enfants récursivement
        children = obj.get('children')
        if children is not None:
            # children peut être une liste ou None
            if isinstance(children, list):
                for child in children:
                    process_object(child)
    
    # Récupérer les objets depuis la structure Gliffy
    objects = []
    if gliffy_data.get('stage') and gliffy_data['stage'].get('objects'):
        objects = gliffy_data['stage']['objects']
    elif gliffy_data.get('pages'):
        for page in gliffy_data['pages']:
            if page and page.get('scene') and page['scene'].get('objects'):
                objects.extend(page['scene']['objects'])
    
    for obj in objects:
        process_object(obj)
    
    return tids

def extract_all_tids_from_directory(gliffy_dir: Path) -> Dict[str, int]:
    """Extrait tous les TID depuis tous les fichiers Gliffy dans un répertoire."""
    all_tids = defaultdict(int)
    
    # Chercher tous les fichiers .gliffy
    gliffy_files = list(gliffy_dir.rglob('*.gliffy'))
    
    if not gliffy_files:
        print(f"❌ Aucun fichier .gliffy trouvé dans {gliffy_dir}")
        return dict(all_tids)
    
    print(f"📂 Recherche de fichiers .gliffy dans {gliffy_dir}...")
    print(f"   Trouvé {len(gliffy_files)} fichier(s)\n")
    
    for gliffy_file in gliffy_files:
        try:
            with open(gliffy_file, 'r', encoding='utf-8') as f:
                gliffy_data = json.load(f)
            
            tids = extract_tids_from_gliffy(gliffy_data)
            for tid in tids:
                all_tids[tid] += 1
            
            print(f"  ✅ {gliffy_file.name}: {len(tids)} TID(s) unique(s)")
        except Exception as e:
            print(f"  ❌ Erreur lors du traitement de {gliffy_file.name}: {e}")
    
    return dict(all_tids)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Extrait tous les TID uniques depuis les fichiers Gliffy')
    parser.add_argument('--dir', default='gliffy_images/gliffy_files', help='Répertoire contenant les fichiers .gliffy (défaut: gliffy_images/gliffy_files)')
    parser.add_argument('--output', default='tids_mapping.json', help='Fichier JSON de sortie (défaut: tids_mapping.json)')
    
    args = parser.parse_args()
    
    gliffy_dir = Path(args.dir)
    if not gliffy_dir.exists():
        print(f"❌ Le répertoire {gliffy_dir} n'existe pas")
        sys.exit(1)
    
    print("🔍 Extraction des TID depuis les fichiers Gliffy...\n")
    
    all_tids = extract_all_tids_from_directory(gliffy_dir)
    
    if not all_tids:
        print("\n❌ Aucun TID trouvé")
        sys.exit(1)
    
    # Créer un mapping avec des chemins d'image vides
    tid_mapping = {}
    for tid, count in sorted(all_tids.items(), key=lambda x: x[1], reverse=True):
        tid_mapping[tid] = {
            'count': count,
            'image_path': None,  # À remplir manuellement ou automatiquement
            'description': ''  # Description optionnelle
        }
    
    # Sauvegarder le mapping
    output_file = Path(args.output)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tid_mapping, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(all_tids)} TID(s) unique(s) trouvé(s)")
    print(f"💾 Mapping sauvegardé dans: {output_file.absolute()}")
    
    # Sauvegarder également en format texte lisible
    try:
        from report_utils import export_tids_mapping_txt
        txt_output_file = output_file.stem + '.txt'
        export_tids_mapping_txt(tid_mapping, txt_output_file)
    except ImportError:
        pass
    
    print("\n📋 Top 10 TID les plus fréquents:")
    for tid, info in list(tid_mapping.items())[:10]:
        print(f"   TID {tid}: {info['count']} occurrence(s)")

if __name__ == '__main__':
    main()

