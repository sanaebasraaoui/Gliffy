#!/usr/bin/env python3
"""
Script pour identifier les pages Confluence contenant des macros Gliffy.

Ce module scanne une instance Confluence pour trouver toutes les pages contenant
des diagrammes Gliffy, en utilisant uniquement l'API REST Confluence.

Fonctionnalités :
- Détection des macros Gliffy dans les pages
- Recherche dans le contenu source (body.storage) et rendu HTML
- Support de tous les espaces ou espaces spécifiques
- Génération de rapports détaillés

Auteur: Sanae Basraoui
"""

import argparse
import re
import requests
from typing import List, Dict, Optional, Set
from pathlib import Path
import json


class GliffyPageFinder:
    def __init__(
        self,
        confluence_url: str,
        username: str,
        api_token: str,
        spaces: Optional[List[str]] = None,
    ):
        """
        Initialise le finder de pages Gliffy.
        
        Args:
            confluence_url: URL de base de Confluence (ex: https://confluence.example.com)
            username: Nom d'utilisateur Confluence
            api_token: Token API Confluence
            spaces: Liste des clés d'espaces à traiter (None = tous les espaces)
        """
        self.confluence_url = confluence_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.spaces_filter = set(spaces) if spaces else None
        
        # Détecter si c'est Atlassian Cloud (atlassian.net)
        if 'atlassian.net' in self.confluence_url.lower():
            if '/wiki' in self.confluence_url.lower():
                self.api_base = f"{self.confluence_url}/rest/api"
            else:
                self.api_base = f"{self.confluence_url}/wiki/rest/api"
        else:
            self.api_base = f"{self.confluence_url}/rest/api"
        
        # Session HTTP pour l'API Confluence
        self.session = requests.Session()
        self.session.auth = (username, api_token)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Résultats
        self.pages_with_gliffy = []
        self.total_pages_analyzed = 0
        self.total_spaces_analyzed = 0

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
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Erreur lors de la récupération des espaces: {e}")
                break
        
        # Filtrer si des espaces spécifiques sont demandés
        if self.spaces_filter:
            spaces = [s for s in spaces if s.get('key') in self.spaces_filter]
            print(f"✅ {len(spaces)} espace(s) sélectionné(s): {', '.join([s['key'] for s in spaces])}")
        else:
            print(f"✅ {len(spaces)} espace(s) trouvé(s)")
        
        return spaces

    def get_all_pages(self, space_key: str, include_drafts: bool = True) -> List[Dict]:
        """Récupère toutes les pages d'un espace, y compris les drafts si demandé."""
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
                
            except requests.exceptions.RequestException as e:
                print(f"⚠️  Erreur lors de la récupération des pages de l'espace {space_key}: {e}")
                break
        
        # Chercher aussi les drafts avec pagination complète
        if include_drafts:
            # Méthode 1: Chercher via l'endpoint content avec status=draft (avec pagination)
            try:
                draft_start = 0
                draft_limit = 100
                existing_ids = {p.get('id') for p in pages}
                
                while True:
                    draft_url = f"{self.api_base}/content"
                    draft_params = {
                        'spaceKey': space_key,
                        'type': 'page',
                        'status': 'draft',
                        'start': draft_start,
                        'limit': draft_limit,
                        'expand': 'body.storage,version'
                    }
                    draft_response = self.session.get(draft_url, params=draft_params)
                    if draft_response.status_code == 200:
                        draft_data = draft_response.json()
                        draft_results = draft_data.get('results', [])
                        if not draft_results:
                            break
                        
                        # Éviter les doublons
                        new_drafts = [d for d in draft_results if d.get('id') not in existing_ids]
                        if new_drafts:
                            pages.extend(new_drafts)
                            existing_ids.update({d.get('id') for d in new_drafts})
                        
                        if len(draft_results) < draft_limit:
                            break
                        
                        draft_start += draft_limit
                    else:
                        break
            except Exception as e:
                pass
            
            # Méthode 2: Chercher via CQL avec pagination complète
            try:
                cql_start = 0
                cql_limit = 100
                existing_ids = {p.get('id') for p in pages}
                
                while True:
                    cql_url = f"{self.api_base}/content/search"
                    cql_params = {
                        'cql': f'space = "{space_key}" AND type = page',
                        'start': cql_start,
                        'limit': cql_limit,
                        'expand': 'body.storage,version'
                    }
                    cql_response = self.session.get(cql_url, params=cql_params)
                    if cql_response.status_code == 200:
                        cql_data = cql_response.json()
                        cql_results = cql_data.get('results', [])
                        if not cql_results:
                            break
                        
                        # Filtrer les drafts et éviter les doublons
                        draft_results = [r for r in cql_results if r.get('status') == 'draft' and r.get('id') not in existing_ids]
                        if draft_results:
                            pages.extend(draft_results)
                            existing_ids.update({d.get('id') for d in draft_results})
                        
                        if len(cql_results) < cql_limit:
                            break
                        
                        cql_start += cql_limit
                    else:
                        break
            except Exception as e:
                pass
        
        return pages

    def page_contains_gliffy(self, page_id: str) -> tuple[bool, List[str]]:
        """
        Vérifie si une page contient des Gliffy.
        Les Gliffy peuvent être stockés comme :
        1. Macros Gliffy (<ac:structured-macro ac:name="gliffy">)
        2. Images embed via confluence-connect.gliffy.net
        3. Références dans les paramètres de macros
        Retourne (True/False, liste des références Gliffy trouvées).
        """
        url = f"{self.api_base}/content/{page_id}"
        params = {
            'expand': 'body.storage,body.view'
        }
        
        found_references = []
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Chercher dans body.storage (contenu source)
            body_storage = data.get('body', {}).get('storage', {}).get('value', '')
            if body_storage:
                # 1. Chercher les macros Gliffy classiques
                gliffy_macro_patterns = [
                    (r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\'][^>]*>', 'macro gliffy'),
                    (r'<ac:structured-macro[^>]*ac:name=["\']Gliffy["\'][^>]*>', 'macro Gliffy'),
                ]
                
                for pattern, ref_type in gliffy_macro_patterns:
                    if re.search(pattern, body_storage, re.IGNORECASE):
                        found_references.append(ref_type)
                
                # 2. Chercher les URLs Gliffy (confluence-connect.gliffy.net)
                gliffy_url_patterns = [
                    (r'confluence-connect\.gliffy\.net[^"\'>\s]*', 'URL gliffy.net'),
                    (r'gliffy\.net[^"\'>\s]*', 'URL gliffy'),
                    (r'gliffy\.com[^"\'>\s]*', 'URL gliffy.com'),
                ]
                
                for pattern, ref_type in gliffy_url_patterns:
                    matches = re.findall(pattern, body_storage, re.IGNORECASE)
                    if matches:
                        # Extraire les IDs Gliffy uniques
                        gliffy_ids = set()
                        for match in matches:
                            # Chercher les IDs Gliffy dans l'URL (format UUID)
                            id_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', match, re.IGNORECASE)
                            if id_match:
                                gliffy_ids.add(id_match.group(1))
                        if gliffy_ids:
                            found_references.append(f'{ref_type} ({len(gliffy_ids)} diagramme(s))')
                
                # 3. Chercher les paramètres de macros qui référencent Gliffy
                # Format: <ac:parameter ac:name="...">...gliffy...</ac:parameter>
                gliffy_param_pattern = r'<ac:parameter[^>]*>.*?gliffy.*?</ac:parameter>'
                if re.search(gliffy_param_pattern, body_storage, re.IGNORECASE | re.DOTALL):
                    found_references.append('paramètre macro gliffy')
                
                # 4. Chercher les images avec des IDs Gliffy
                # Format: <img src="...gliffy..." />
                img_gliffy_pattern = r'<img[^>]*src=["\'][^"\']*gliffy[^"\']*["\'][^>]*>'
                if re.search(img_gliffy_pattern, body_storage, re.IGNORECASE):
                    found_references.append('image gliffy')
            
            # Chercher aussi dans body.view (HTML rendu)
            body_view = data.get('body', {}).get('view', {}).get('value', '')
            if body_view:
                # Chercher les URLs Gliffy dans le HTML rendu
                if re.search(r'confluence-connect\.gliffy\.net', body_view, re.IGNORECASE):
                    found_references.append('URL gliffy.net (HTML rendu)')
                
                # Chercher les macros Gliffy dans le HTML rendu
                if re.search(r'data-macro-name=["\']gliffy["\']', body_view, re.IGNORECASE):
                    found_references.append('macro gliffy (HTML rendu)')
            
            if found_references:
                return True, found_references
            
            return False, []
            
        except requests.exceptions.RequestException as e:
            # Si la page n'existe pas ou n'est pas accessible, retourner False
            if response.status_code == 404:
                return False, []
            print(f"  ⚠️  Erreur lors de la vérification de la page {page_id}: {e}")
            return False, []

    def process_space(self, space: Dict):
        """Traite toutes les pages d'un espace."""
        space_key = space.get('key')
        space_name = space.get('name', space_key)
        
        print(f"\n📄 Analyse de l'espace: {space_name} ({space_key})")
        
        # Récupérer toutes les pages (y compris les drafts)
        pages = self.get_all_pages(space_key, include_drafts=True)
        
        if not pages:
            print(f"  ℹ️  Aucune page trouvée dans cet espace")
            return
        
        # Séparer les drafts des pages publiées pour les statistiques
        drafts_count = len([p for p in pages if p.get('status') == 'draft'])
        published_count = len([p for p in pages if p.get('status') != 'draft'])
        
        print(f"  📋 {len(pages)} page(s) trouvée(s) au total:")
        print(f"     - {published_count} page(s) publiée(s)")
        if drafts_count > 0:
            print(f"     - {drafts_count} draft(s)")
        print(f"  🔍 Analyse en cours...")
        
        self.total_pages_analyzed += len(pages)
        
        # Séparer les drafts des pages publiées
        drafts = [p for p in pages if p.get('status') == 'draft']
        published_pages = [p for p in pages if p.get('status') != 'draft']
        
        # Identifier les drafts avec Gliffy
        if drafts:
            for draft in drafts:
                draft_id = draft.get('id')
                draft_title = draft.get('title', 'Untitled')
                body_storage = draft.get('body', {}).get('storage', {}).get('value', '')
                
                # Vérifier si le draft contient des Gliffy
                has_gliffy = False
                gliffy_refs = []
                if body_storage:
                    if 'confluence-connect.gliffy.net' in body_storage.lower() or 'gliffy.net' in body_storage.lower():
                        has_gliffy = True
                        urls = re.findall(r'https?://[^"\'\\s<>]*gliffy[^"\'\\s<>]*', body_storage, re.IGNORECASE)
                        gliffy_refs.extend([f'URL: {url[:60]}...' for url in set(urls)[:2]])
                    elif re.search(r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\']', body_storage, re.IGNORECASE):
                        has_gliffy = True
                        gliffy_refs.append('Macro gliffy')
                
                if has_gliffy:
                    print(f"  ✅ Draft avec Gliffy trouvé: '{draft_title}' (ID: {draft_id})")
                    for ref in gliffy_refs[:2]:
                        print(f"     - {ref}")
                    
                    # Identifier le draft comme ayant des Gliffy
                    page_info = {
                        'id': draft_id,
                        'title': draft_title,
                        'space_key': space_key,
                        'space_name': space_name,
                        'status': 'draft',
                        'macros': gliffy_refs,
                        'body_storage': body_storage,  # Sauvegarder le contenu pour l'extraction des IDs Gliffy
                        'url': f"{self.confluence_url.rstrip('/wiki')}/wiki/pages/viewpage.action?pageId={draft_id}" if 'atlassian.net' in self.confluence_url.lower() else f"{self.confluence_url}/pages/viewpage.action?pageId={draft_id}"
                    }
                    self.pages_with_gliffy.append(page_info)
        
        # Vérifier chaque page publiée
        for page in published_pages:
            page_id = page.get('id')
            page_title = page.get('title', 'Untitled')
            page_status = page.get('status', 'current')
            
            # Si le body.storage est déjà dans la réponse, l'utiliser directement
            body_storage = page.get('body', {}).get('storage', {}).get('value', '')
            if body_storage:
                # Vérifier directement dans le body_storage
                has_gliffy = False
                gliffy_refs = []
                
                # Chercher URLs gliffy
                if 'confluence-connect.gliffy.net' in body_storage.lower() or 'gliffy.net' in body_storage.lower():
                    has_gliffy = True
                    urls = re.findall(r'https?://[^"\'\\s<>]*gliffy[^"\'\\s<>]*', body_storage, re.IGNORECASE)
                    gliffy_refs.extend([f'URL: {url[:80]}...' for url in set(urls)[:2]])
                
                # Chercher macros gliffy
                if re.search(r'<ac:structured-macro[^>]*ac:name=["\']gliffy["\']', body_storage, re.IGNORECASE):
                    has_gliffy = True
                    gliffy_refs.append('Macro gliffy')
                
                if has_gliffy:
                    # Récupérer le body_storage si disponible
                    page_body_storage = page.get('body', {}).get('storage', {}).get('value', '')
                    
                    page_info = {
                        'id': page_id,
                        'title': page_title,
                        'space_key': space_key,
                        'space_name': space_name,
                        'status': page_status,
                        'macros': gliffy_refs,
                        'body_storage': page_body_storage,  # Sauvegarder le contenu pour l'extraction des IDs Gliffy
                        'url': f"{self.confluence_url.rstrip('/wiki')}/wiki/pages/viewpage.action?pageId={page_id}" if 'atlassian.net' in self.confluence_url.lower() else f"{self.confluence_url}/pages/viewpage.action?pageId={page_id}"
                    }
                    self.pages_with_gliffy.append(page_info)
                    status_label = f" [{page_status}]" if page_status != 'current' else ""
                    print(f"  ✅ '{page_title}' (ID: {page_id}){status_label}")
                    for ref in gliffy_refs[:3]:
                        print(f"     - {ref}")
            else:
                # Sinon, utiliser la méthode normale
                has_gliffy, macros_found = self.page_contains_gliffy(page_id)
                
                if has_gliffy:
                    page_info = {
                        'id': page_id,
                        'title': page_title,
                        'space_key': space_key,
                        'space_name': space_name,
                        'status': page_status,
                        'macros': macros_found,
                        'url': f"{self.confluence_url.rstrip('/wiki')}/wiki/pages/viewpage.action?pageId={page_id}" if 'atlassian.net' in self.confluence_url.lower() else f"{self.confluence_url}/pages/viewpage.action?pageId={page_id}"
                    }
                    self.pages_with_gliffy.append(page_info)
                    status_label = f" [{page_status}]" if page_status != 'current' else ""
                    print(f"  ✅ '{page_title}' (ID: {page_id}){status_label} - {', '.join(macros_found)}")

    def run(self):
        """Lance le processus de recherche."""
        print("🚀 Recherche des pages contenant des macros Gliffy\n")
        
        if self.spaces_filter:
            print(f"🎯 Espaces sélectionnés: {', '.join(self.spaces_filter)}")
        else:
            print(f"🌐 Mode: Tous les espaces")
        
        print()
        
        # Récupérer tous les espaces
        spaces = self.get_all_spaces()
        
        if not spaces:
            print("❌ Aucun espace trouvé")
            return
        
        # Traiter chaque espace
        for space in spaces:
            self.process_space(space)
            self.total_spaces_analyzed += 1
        
        # Afficher les résultats
        print("\n" + "="*60)
        print("📊 Résultats:")
        print(f"  • Espaces analysés: {self.total_spaces_analyzed}")
        print(f"  • Pages totales analysées: {self.total_pages_analyzed}")
        print(f"  • Pages avec Gliffy trouvées: {len(self.pages_with_gliffy)}")
        print("="*60)
        
        if self.pages_with_gliffy:
            print("\n📋 Liste des pages avec Gliffy:")
            for idx, page in enumerate(self.pages_with_gliffy, 1):
                print(f"\n{idx}. {page['title']}")
                print(f"   Espace: {page['space_name']} ({page['space_key']})")
                print(f"   URL: {page['url']}")
                print(f"   ID: {page['id']}")
                if 'status' in page:
                    print(f"   Statut: {page['status']}")
                if 'macros' in page:
                    print(f"   Macros Gliffy trouvées: {', '.join(page['macros'])}")
            
            # Sauvegarder les résultats dans un fichier JSON
            output_file = Path('gliffy_pages.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.pages_with_gliffy, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Résultats sauvegardés dans: {output_file.absolute()}")
            
            # Sauvegarder également en format texte lisible
            try:
                from report_utils import export_gliffy_pages_txt
                export_gliffy_pages_txt(self.pages_with_gliffy)
            except ImportError:
                pass
        else:
            print("\n❌ Aucune page avec Gliffy trouvée")


def main():
    parser = argparse.ArgumentParser(
        description='Identifie les pages Confluence contenant des macros Gliffy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Chercher dans tous les espaces
  python find_gliffy_pages.py --url https://confluence.example.com --username user --token TOKEN

  # Chercher dans des espaces spécifiques
  python find_gliffy_pages.py --url https://confluence.example.com --username user --token TOKEN --spaces DEV PROD
        """
    )
    
    parser.add_argument(
        '--url',
        required=True,
        help='URL de base de Confluence (ex: https://confluence.example.com)'
    )
    
    parser.add_argument(
        '--username',
        required=True,
        help='Nom d\'utilisateur Confluence'
    )
    
    parser.add_argument(
        '--token',
        required=True,
        help='Token API Confluence'
    )
    
    parser.add_argument(
        '--spaces',
        nargs='+',
        help='Clés d\'espaces à traiter (ex: DEV PROD). Si non spécifié, traite tous les espaces.'
    )
    
    args = parser.parse_args()
    
    # Créer et lancer le finder
    finder = GliffyPageFinder(
        confluence_url=args.url,
        username=args.username,
        api_token=args.token,
        spaces=args.spaces
    )
    
    finder.run()


if __name__ == '__main__':
    main()

