#!/usr/bin/env python3
"""
Module utilitaire pour générer des rapports en format texte lisible.
Tous les rapports sont sauvegardés dans le dossier 'reports/'.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


REPORTS_DIR = Path("reports")


def ensure_reports_dir():
    """Crée le dossier reports s'il n'existe pas."""
    REPORTS_DIR.mkdir(exist_ok=True)
    return REPORTS_DIR


def add_timestamp_to_filename(filename: str) -> str:
    """
    Ajoute un horodatage au nom de fichier pour éviter l'écrasement.
    
    Args:
        filename: Nom de fichier (avec ou sans extension)
        
    Returns:
        Nom de fichier avec horodatage (ex: gliffy_pages_2025-12-24_15-30-45.txt)
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    path = Path(filename)
    
    if path.suffix:
        # Fichier avec extension
        return f"{path.stem}_{timestamp}{path.suffix}"
    else:
        # Fichier sans extension
        return f"{filename}_{timestamp}"


def export_gliffy_pages_txt(pages_data: List[Dict], output_file: str = "gliffy_pages.txt"):
    """Exporte la liste des pages Gliffy en format texte lisible."""
    if not pages_data:
        return
    
    reports_dir = ensure_reports_dir()
    # Ajouter l'horodatage au nom de fichier
    timestamped_filename = add_timestamp_to_filename(output_file)
    output_path = reports_dir / timestamped_filename
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("RAPPORT DES PAGES CONFLUENCE AVEC GLIFFY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Nombre total de pages: {len(pages_data)}\n\n")
        f.write("=" * 80 + "\n\n")
        
        for idx, page in enumerate(pages_data, 1):
            f.write(f"PAGE {idx}/{len(pages_data)}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Titre: {page.get('title', 'Sans titre')}\n")
            f.write(f"ID: {page.get('id', 'N/A')}\n")
            f.write(f"Espace: {page.get('space_name', 'N/A')} ({page.get('space_key', 'N/A')})\n")
            f.write(f"Statut: {page.get('status', 'N/A')}\n")
            f.write(f"URL: {page.get('url', 'N/A')}\n")
            
            if 'macros' in page and page['macros']:
                f.write(f"Macros Gliffy trouvées: {', '.join(page['macros'])}\n")
            else:
                f.write("Macros Gliffy: Aucune\n")
            
            f.write("\n")
    
    print(f"💾 Rapport texte sauvegardé: {output_path.absolute()}")


def export_migration_report_txt(report_data: Dict, output_file: str = "migration_report.txt"):
    """Exporte le rapport de migration en format texte lisible."""
    if not report_data or 'pages' not in report_data:
        return
    
    reports_dir = ensure_reports_dir()
    # Ajouter l'horodatage au nom de fichier
    timestamped_filename = add_timestamp_to_filename(output_file)
    output_path = reports_dir / timestamped_filename
    
    stats = report_data.get('stats', {})
    pages = report_data.get('pages', [])
    timestamp = report_data.get('timestamp', datetime.now().isoformat())
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("RAPPORT DE MIGRATION GLIFFY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Date de migration: {timestamp}\n\n")
        
        f.write("STATISTIQUES GLOBALES\n")
        f.write("-" * 80 + "\n")
        f.write(f"Pages traitées: {stats.get('pages_processed', 0)}\n")
        f.write(f"Pages modifiées: {stats.get('pages_modified', 0)}\n")
        f.write(f"Pages ignorées: {stats.get('pages_skipped', 0)}\n")
        f.write(f"Gliffy trouvés: {stats.get('gliffy_found', 0)}\n")
        f.write(f"Images insérées: {stats.get('images_inserted', 0)}\n")
        f.write(f"Erreurs: {stats.get('errors', 0)}\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("DÉTAILS PAR PAGE\n")
        f.write("=" * 80 + "\n\n")
        
        for idx, page in enumerate(pages, 1):
            f.write(f"PAGE {idx}/{len(pages)}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Titre: {page.get('page_title', 'Sans titre')}\n")
            f.write(f"ID: {page.get('page_id', 'N/A')}\n")
            f.write(f"Statut: {page.get('status', 'N/A').upper()}\n")
            
            if page.get('status') == 'modified':
                f.write(f"✓ Page modifiée avec succès\n")
                f.write(f"  • Gliffy trouvés: {page.get('gliffy_count', 0)}\n")
                f.write(f"  • Images insérées: {page.get('images_inserted', 0)}\n")
            elif page.get('status') == 'skipped':
                f.write(f"⊘ Page ignorée\n")
                f.write(f"  • Raison: {page.get('reason', 'N/A')}\n")
            elif page.get('status') == 'error':
                f.write(f"✗ Erreur lors du traitement\n")
                f.write(f"  • Gliffy trouvés: {page.get('gliffy_count', 0)}\n")
                f.write(f"  • Images insérées: {page.get('images_inserted', 0)}\n")
                f.write(f"  • Raison: {page.get('reason', 'N/A')}\n")
                if page.get('errors'):
                    f.write(f"  • Erreurs détaillées:\n")
                    for error in page['errors']:
                        f.write(f"    - {error}\n")
            
            f.write("\n")
    
    print(f"💾 Rapport texte sauvegardé: {output_path.absolute()}")


def export_tids_mapping_txt(tid_mapping: Dict, output_file: str = "tids_mapping.txt"):
    """Exporte le mapping des TID en format texte lisible."""
    if not tid_mapping:
        return
    
    reports_dir = ensure_reports_dir()
    # Ajouter l'horodatage au nom de fichier
    timestamped_filename = add_timestamp_to_filename(output_file)
    output_path = reports_dir / timestamped_filename
    
    # Trier par nombre d'occurrences (décroissant)
    sorted_tids = sorted(tid_mapping.items(), key=lambda x: x[1].get('count', 0), reverse=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("MAPPING DES TID GLIFFY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Nombre total de TID uniques: {len(tid_mapping)}\n\n")
        f.write("=" * 80 + "\n\n")
        
        total_occurrences = sum(info.get('count', 0) for info in tid_mapping.values())
        f.write(f"Total d'occurrences: {total_occurrences}\n\n")
        
        for tid, info in sorted_tids:
            f.write(f"TID: {tid}\n")
            f.write("-" * 80 + "\n")
            f.write(f"  Occurrences: {info.get('count', 0)}\n")
            
            image_path = info.get('image_path')
            if image_path:
                f.write(f"  Chemin image: {image_path}\n")
            else:
                f.write(f"  Chemin image: Non défini\n")
            
            description = info.get('description', '').strip()
            if description:
                f.write(f"  Description: {description}\n")
            
            f.write("\n")
    
    print(f"💾 Rapport texte sauvegardé: {output_path.absolute()}")


def export_inventory_txt(inventory: List[Dict], output_file: str = "confluence_inventory.txt"):
    """Exporte l'inventaire Confluence en format texte lisible."""
    if not inventory:
        return
    
    reports_dir = ensure_reports_dir()
    # Ajouter l'horodatage au nom de fichier
    timestamped_filename = add_timestamp_to_filename(output_file)
    output_path = reports_dir / timestamped_filename
    
    # Grouper par espace
    pages_by_space = {}
    for page in inventory:
        space_key = page.get('space_key', 'unknown')
        if space_key not in pages_by_space:
            pages_by_space[space_key] = []
        pages_by_space[space_key].append(page)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("INVENTAIRE CONFLUENCE\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Nombre total de pages: {len(inventory)}\n")
        f.write(f"Nombre d'espaces: {len(pages_by_space)}\n\n")
        f.write("=" * 80 + "\n\n")
        
        for space_key, pages in sorted(pages_by_space.items()):
            space_name = pages[0].get('space_name', space_key) if pages else space_key
            f.write(f"ESPACE: {space_name} ({space_key})\n")
            f.write("-" * 80 + "\n")
            f.write(f"Nombre de pages: {len(pages)}\n\n")
            
            for page in pages:
                f.write(f"  • {page.get('title', 'Sans titre')}\n")
                f.write(f"    ID: {page.get('id', 'N/A')}\n")
                f.write(f"    Statut: {page.get('status', 'N/A')}\n")
                f.write(f"    Version: {page.get('version', 'N/A')}\n")
                f.write(f"    URL: {page.get('url', 'N/A')}\n")
                f.write(f"    Créé le: {page.get('created_date', 'N/A')} par {page.get('created_by', 'N/A')}\n")
                f.write(f"    Modifié le: {page.get('last_updated_date', 'N/A')} par {page.get('last_updated_by', 'N/A')}\n")
                if page.get('parent_title'):
                    f.write(f"    Page parent: {page.get('parent_title')} (ID: {page.get('parent_id', 'N/A')})\n")
                f.write("\n")
            
            f.write("\n")
    
    print(f"💾 Rapport texte sauvegardé: {output_path.absolute()}")

