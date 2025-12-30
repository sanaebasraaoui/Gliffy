#!/usr/bin/env python3
"""
Module pour scanner Confluence et créer un inventaire complet des pages.

Ce module permet de scanner une instance Confluence et de générer un inventaire
détaillé de toutes les pages avec leurs métadonnées (création, modification,
hiérarchie, présence de Gliffy, etc.).

Fonctionnalités :
- Scan de tous les espaces ou espaces spécifiques
- Scan d'une page spécifique par son ID
- Détection automatique des diagrammes Gliffy dans les pages
- Export en format TXT (lisible) ou JSON (structuré)

Auteur: Sanae Basraoui
"""

import csv
import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from confluence_base import ConfluenceBase


class ConfluenceScanner(ConfluenceBase):
    """Scanner pour créer un inventaire complet de Confluence."""
    
    def __init__(
        self,
        confluence_url: str,
        username: str,
        api_token: str,
        spaces: Optional[List[str]] = None,
        page_id: Optional[str] = None,
    ):
        """
        Initialise le scanner Confluence.
        
        Args:
            confluence_url: URL de base de Confluence
            username: Nom d'utilisateur Confluence
            api_token: Token API Confluence
            spaces: Liste des clés d'espaces à scanner (None = tous)
            page_id: ID d'une page spécifique à scanner (None = toutes les pages)
        """
        super().__init__(confluence_url, username, api_token)
        self.spaces_filter = set(spaces) if spaces else None
        self.page_id_filter = page_id
        self.inventory = []
    
    def get_all_spaces(self) -> List[Dict]:
        """Récupère tous les espaces Confluence."""
        print("📂 Récupération de la liste des espaces...")
        # Convertir le set en liste pour get_all_spaces
        spaces_filter_list = list(self.spaces_filter) if self.spaces_filter else None
        spaces = super().get_all_spaces(spaces_filter_list)
        
        if self.spaces_filter:
            print(f"✅ {len(spaces)} espace(s) sélectionné(s)")
        else:
            print(f"✅ {len(spaces)} espace(s) trouvé(s)")
        
        return spaces
    
    def get_all_pages(self, space_key: str, include_drafts: bool = True) -> List[Dict]:
        """Récupère toutes les pages d'un espace."""
        return super().get_all_pages(space_key, include_drafts, expand='space,version,history,ancestors,body.storage')
    
    def get_page_details(self, page_id: str) -> Optional[Dict]:
        """Récupère les détails d'une page spécifique."""
        return super().get_page_details(page_id, expand='space,version,history,ancestors,body.storage')
    
    def format_date(self, date_str: Optional[str]) -> str:
        """Formate une date ISO en format lisible."""
        if not date_str:
            return ''
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return date_str
    
    def extract_gliffy_info(self, body_storage: str) -> Dict:
        """
        Extrait les informations sur les Gliffy présents dans une page.
        
        Returns:
            Dict avec 'count' (nombre de Gliffy) et 'titles' (liste des titres)
        """
        if not body_storage:
            return {'count': 0, 'titles': []}
        
        gliffy_titles = []
        
        # Chercher les macros Gliffy et extraire leurs titres
        gliffy_macro_pattern = r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>.*?</ac:structured-macro>'
        gliffy_macros = re.findall(gliffy_macro_pattern, body_storage, re.DOTALL | re.IGNORECASE)
        
        for macro in gliffy_macros:
            # Extraire le paramètre "name" qui contient le titre du diagramme
            name_param = re.search(r'<ac:parameter[^>]*ac:name=["\']name["\'][^>]*>([^<]+)</ac:parameter>', macro, re.IGNORECASE)
            if name_param:
                diagram_name = name_param.group(1).strip()
                if diagram_name:
                    gliffy_titles.append(diagram_name)
            else:
                # Si pas de nom, utiliser un titre par défaut
                gliffy_titles.append("(sans titre)")
        
        return {
            'count': len(gliffy_titles),
            'titles': gliffy_titles
        }
    
    def extract_page_info(self, page: Dict, space_key: str, space_name: str) -> Dict:
        """Extrait les informations d'une page pour l'inventaire."""
        page_id = page.get('id', '')
        title = page.get('title', 'Sans titre')
        status = page.get('status', 'current')
        
        # Informations de version
        version = page.get('version', {})
        version_number = version.get('number', 0)
        
        # Informations de création/modification
        history = page.get('history', {})
        created_date = history.get('createdDate', '')
        created_by = history.get('createdBy', {})
        created_by_name = created_by.get('displayName', created_by.get('username', ''))
        
        last_updated = history.get('lastUpdated', {})
        last_updated_date = last_updated.get('when', '') if last_updated else ''
        last_updated_by = last_updated.get('by', {}) if last_updated else {}
        last_updated_by_name = last_updated_by.get('displayName', last_updated_by.get('username', '')) if last_updated_by else ''
        
        # Si lastUpdated est vide, utiliser createdDate comme fallback
        # (certaines pages peuvent ne pas avoir de lastUpdated si jamais modifiées)
        if not last_updated_date and created_date:
            last_updated_date = created_date
            last_updated_by_name = created_by_name
        
        # Ancêtres (hiérarchie)
        ancestors = page.get('ancestors', [])
        parent_id = ancestors[-1].get('id') if ancestors else ''
        parent_title = ancestors[-1].get('title', '') if ancestors else ''
        
        # URL
        if 'atlassian.net' in self.confluence_url.lower():
            page_url = f"{self.confluence_url.rstrip('/wiki')}/wiki/pages/viewpage.action?pageId={page_id}"
        else:
            page_url = f"{self.confluence_url}/pages/viewpage.action?pageId={page_id}"
        
        # Extraire les informations Gliffy
        body_storage = page.get('body', {}).get('storage', {}).get('value', '')
        gliffy_info = self.extract_gliffy_info(body_storage)
        
        return {
            'id': page_id,
            'title': title,
            'space_key': space_key,
            'space_name': space_name,
            'status': status,
            'version': version_number,
            'created_date': self.format_date(created_date),
            'created_by': created_by_name,
            'last_updated_date': self.format_date(last_updated_date),
            'last_updated_by': last_updated_by_name,
            'parent_id': parent_id,
            'parent_title': parent_title,
            'url': page_url,
            'ancestors_count': len(ancestors),
            'gliffy_count': gliffy_info['count'],
            'gliffy_titles': gliffy_info['titles']
        }
    
    def scan(self) -> List[Dict]:
        """Lance le scan complet."""
        print("🚀 Démarrage du scan Confluence\n")
        
        # Si une page spécifique est demandée
        if self.page_id_filter:
            print(f"🎯 Mode: Page spécifique (ID: {self.page_id_filter})\n")
            page_data = self.get_page_details(self.page_id_filter)
            if page_data:
                space = page_data.get('space', {})
                space_key = space.get('key', 'unknown')
                space_name = space.get('name', space_key)
                page_info = self.extract_page_info(page_data, space_key, space_name)
                self.inventory.append(page_info)
                print(f"✅ Page trouvée: {page_info['title']}")
            else:
                print(f"❌ Page {self.page_id_filter} non trouvée")
            return self.inventory
        
        # Scan par espace(s)
        if self.spaces_filter:
            spaces_list = list(self.spaces_filter)
            print(f"🎯 Mode: Espaces spécifiques ({', '.join(spaces_list)})\n")
        else:
            print(f"🌐 Mode: Tous les espaces\n")
        
        spaces = self.get_all_spaces()
        
        if not spaces:
            if self.spaces_filter:
                print(f"❌ Aucun espace trouvé parmi: {', '.join(list(self.spaces_filter))}")
            else:
                print("❌ Aucun espace trouvé")
            return []
        
        total_pages = 0
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name', space_key)
            
            print(f"\n📄 Analyse de l'espace: {space_name} ({space_key})")
            
            pages = self.get_all_pages(space_key, include_drafts=True)
            
            if not pages:
                print(f"  ℹ️  Aucune page trouvée")
                continue
            
            drafts_count = len([p for p in pages if p.get('status') == 'draft'])
            published_count = len([p for p in pages if p.get('status') != 'draft'])
            
            print(f"  📋 {len(pages)} page(s) trouvée(s):")
            print(f"     - {published_count} page(s) publiée(s)")
            if drafts_count > 0:
                print(f"     - {drafts_count} draft(s)")
            
            for page in pages:
                page_info = self.extract_page_info(page, space_key, space_name)
                self.inventory.append(page_info)
            
            total_pages += len(pages)
        
        print(f"\n✅ Scan terminé: {total_pages} page(s) inventoriée(s)")
        return self.inventory
    
    def export_csv(self, output_file: str):
        """Exporte l'inventaire en CSV."""
        if not self.inventory:
            print("❌ Aucune donnée à exporter")
            return
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fieldnames = [
            'id', 'title', 'space_key', 'space_name', 'status', 'version',
            'created_date', 'created_by', 'last_updated_date', 'last_updated_by',
            'parent_id', 'parent_title', 'ancestors_count', 'url'
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.inventory)
        
        print(f"💾 Inventaire exporté en CSV: {output_path.absolute()}")
    
    def export_json(self, output_file: str):
        """Exporte l'inventaire en JSON."""
        if not self.inventory:
            print("❌ Aucune donnée à exporter")
            return
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.inventory, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Inventaire exporté en JSON: {output_path.absolute()}")
    
    def export_txt(self, output_file: str = "confluence_inventory.txt"):
        """Exporte l'inventaire en format texte lisible dans reports/."""
        if not self.inventory:
            print("❌ Aucune donnée à exporter")
            return
        
        try:
            from report_utils import export_inventory_txt
            export_inventory_txt(self.inventory, output_file)
        except ImportError:
            print("❌ Erreur: module report_utils non trouvé")

