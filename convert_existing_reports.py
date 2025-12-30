#!/usr/bin/env python3
"""
Script pour convertir les fichiers JSON existants en format texte lisible.

Ce module permet de convertir des rapports JSON existants (inventaires, migrations)
en format texte lisible pour faciliter la consultation.

Fonctionnalités :
- Conversion des rapports JSON en format TXT
- Support des rapports de migration et d'inventaire
- Génération de rapports avec horodatage
- Formatage lisible pour les humains

Auteur: Sanae Basraoui
"""

import json
from pathlib import Path
from report_utils import (
    export_gliffy_pages_txt,
    export_migration_report_txt,
    export_tids_mapping_txt,
    export_inventory_txt
)


def convert_gliffy_pages():
    """Convertit gliffy_pages.json en gliffy_pages.txt"""
    json_file = Path('gliffy_pages.json')
    if json_file.exists():
        print(f"📖 Lecture de {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            pages_data = json.load(f)
        export_gliffy_pages_txt(pages_data)
        print("✅ Conversion terminée\n")
    else:
        print(f"⚠️  {json_file} n'existe pas\n")


def convert_migration_report():
    """Convertit migration_report.json en migration_report.txt"""
    json_file = Path('migration_report.json')
    if json_file.exists():
        print(f"📖 Lecture de {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        export_migration_report_txt(report_data)
        print("✅ Conversion terminée\n")
    else:
        print(f"⚠️  {json_file} n'existe pas\n")


def convert_tids_mapping():
    """Convertit tids_mapping.json en tids_mapping.txt"""
    json_file = Path('tids_mapping.json')
    if json_file.exists():
        print(f"📖 Lecture de {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            tid_mapping = json.load(f)
        export_tids_mapping_txt(tid_mapping)
        print("✅ Conversion terminée\n")
    else:
        print(f"⚠️  {tids_mapping.json} n'existe pas\n")


def convert_inventory():
    """Convertit les fichiers d'inventaire JSON en TXT"""
    # Chercher tous les fichiers d'inventaire JSON
    for json_file in Path('.').glob('*inventory*.json'):
        print(f"📖 Lecture de {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            inventory = json.load(f)
        txt_file = json_file.stem + '.txt'
        export_inventory_txt(inventory, txt_file)
        print("✅ Conversion terminée\n")


def main():
    """Convertit tous les fichiers JSON existants en TXT."""
    print("=" * 80)
    print("CONVERSION DES RAPPORTS JSON EXISTANTS EN FORMAT TEXTE")
    print("=" * 80 + "\n")
    
    convert_gliffy_pages()
    convert_migration_report()
    convert_tids_mapping()
    convert_inventory()
    
    print("=" * 80)
    print("✅ Conversion terminée ! Tous les fichiers sont dans reports/")
    print("=" * 80)


if __name__ == '__main__':
    main()

