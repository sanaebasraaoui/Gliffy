#!/usr/bin/env python3
"""
Script pour convertir les fichiers .gliffy locaux en Excalidraw.
"""

import json
import re
from pathlib import Path
from gliffy_to_excalidraw import convert_gliffy_to_excalidraw

def convert_local_gliffy_files():
    """Convertit tous les fichiers .gliffy locaux en Excalidraw."""
    gliffy_dir = Path("gliffy_images/gliffy_files")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    if not gliffy_dir.exists():
        print(f"❌ Le dossier {gliffy_dir} n'existe pas")
        return
    
    gliffy_files = list(gliffy_dir.glob("*.gliffy"))
    
    if not gliffy_files:
        print(f"❌ Aucun fichier .gliffy trouvé dans {gliffy_dir}")
        return
    
    print(f"📁 Trouvé {len(gliffy_files)} fichier(s) .gliffy\n")
    
    # Importer le mapper TID si disponible
    try:
        from tid_image_mapper import TIDImageMapper
        tid_mapper = TIDImageMapper()
        print("✅ Mapper TID chargé\n")
    except ImportError:
        tid_mapper = None
        print("⚠️ Mapper TID non disponible\n")
    
    converted = 0
    errors = 0
    
    for gliffy_file in gliffy_files:
        print(f"🔄 Conversion de {gliffy_file.name}...", end=" ")
        
        try:
            # Lire le fichier Gliffy
            with open(gliffy_file, 'r', encoding='utf-8') as f:
                gliffy_data = json.load(f)
            
            # Convertir en Excalidraw
            excalidraw_data = convert_gliffy_to_excalidraw(gliffy_data, tid_image_mapper=tid_mapper)
            
            if not excalidraw_data:
                print("❌ (conversion retournée vide)")
                errors += 1
                continue
            
            # Générer le nom du fichier de sortie
            safe_name = re.sub(r'[^\w\s-]', '', gliffy_file.stem).strip()
            safe_name = re.sub(r'[-\s]+', '_', safe_name)
            excalidraw_filename = f"{safe_name}.excalidraw"
            excalidraw_filepath = output_dir / excalidraw_filename
            
            # Sauvegarder
            excalidraw_content = json.dumps(excalidraw_data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with open(excalidraw_filepath, 'wb') as f:
                f.write(excalidraw_content)
            
            print(f"✅ Sauvegardé dans output/{excalidraw_filename}")
            converted += 1
            
        except json.JSONDecodeError as e:
            print(f"❌ (erreur JSON: {e})")
            errors += 1
        except Exception as e:
            print(f"❌ (erreur: {e})")
            errors += 1
    
    print("\n" + "=" * 60)
    print("📊 Résumé:")
    print(f"  • Fichiers convertis: {converted}")
    print(f"  • Erreurs: {errors}")
    print(f"  • Fichiers Excalidraw dans: {output_dir.absolute()}")
    print("=" * 60)

if __name__ == '__main__':
    convert_local_gliffy_files()

