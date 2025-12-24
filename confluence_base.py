#!/usr/bin/env python3
"""
Classe de base pour les opérations Confluence communes.
"""

import requests
from typing import List, Dict, Optional


class ConfluenceBase:
    """Classe de base pour les opérations Confluence."""
    
    def __init__(self, confluence_url: str, username: str, api_token: str):
        """Initialise la connexion Confluence."""
        self.confluence_url = confluence_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        
        # Détecter si c'est Atlassian Cloud
        if 'atlassian.net' in self.confluence_url.lower():
            if '/wiki' in self.confluence_url.lower():
                self.api_base = f"{self.confluence_url}/rest/api"
            else:
                self.api_base = f"{self.confluence_url}/wiki/rest/api"
        else:
            self.api_base = f"{self.confluence_url}/rest/api"
        
        # Session HTTP
        self.session = requests.Session()
        self.session.auth = (username, api_token)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def get_all_spaces(self, spaces_filter: Optional[List[str]] = None) -> List[Dict]:
        """Récupère tous les espaces Confluence."""
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
                break
        
        # Filtrer si des espaces spécifiques sont demandés
        if spaces_filter:
            # Convertir en set pour une recherche plus efficace
            spaces_filter_set = set(spaces_filter) if isinstance(spaces_filter, list) else spaces_filter
            spaces = [s for s in spaces if s.get('key') in spaces_filter_set]
        
        return spaces
    
    def get_all_pages(self, space_key: str, include_drafts: bool = True, expand: str = 'body.storage') -> List[Dict]:
        """Récupère toutes les pages d'un espace."""
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
                'expand': expand
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
            except requests.exceptions.RequestException:
                break
        
        # Chercher aussi les drafts si demandé
        if include_drafts:
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
                        'expand': expand
                    }
                    draft_response = self.session.get(draft_url, params=draft_params)
                    if draft_response.status_code == 200:
                        draft_data = draft_response.json()
                        draft_results = draft_data.get('results', [])
                        if not draft_results:
                            break
                        
                        new_drafts = [d for d in draft_results if d.get('id') not in existing_ids]
                        if new_drafts:
                            pages.extend(new_drafts)
                            existing_ids.update({d.get('id') for d in new_drafts})
                        
                        if len(draft_results) < draft_limit:
                            break
                        
                        draft_start += draft_limit
                    else:
                        break
            except Exception:
                pass
        
        return pages
    
    def get_page_details(self, page_id: str, expand: str = 'body.storage,space,version') -> Optional[Dict]:
        """Récupère les détails d'une page spécifique."""
        url = f"{self.api_base}/content/{page_id}"
        params = {'expand': expand}
        
        try:
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        
        return None

