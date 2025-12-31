#!/usr/bin/env python3
"""
Classe de base pour les opérations Confluence communes.

Ce module fournit une classe de base qui encapsule les opérations communes
pour interagir avec l'API REST de Confluence (Cloud et Server/Data Center).

Fonctionnalités :
- Détection automatique du type de Confluence (Cloud vs Server/Data Center)
- Gestion de l'authentification via API token
- Récupération des espaces et pages
- Support des drafts (brouillons)

Auteur: Sanae Basraoui
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
        
        # Détecter si c'est Atlassian Cloud ou Confluence Server/Data Center
        is_cloud = 'atlassian.net' in self.confluence_url.lower()
        
        if is_cloud:
            # Atlassian Cloud
            if '/wiki' in self.confluence_url.lower():
                self.api_base = f"{self.confluence_url.rstrip('/wiki')}/wiki/rest/api"
            else:
                self.api_base = f"{self.confluence_url}/wiki/rest/api"
        else:
            # Confluence Server/Data Center
            self.api_base = f"{self.confluence_url}/rest/api"
        
        # Session HTTP avec validation SSL
        self.session = requests.Session()
        
        # Configuration de l'authentification
        if is_cloud:
            # Cloud utilise Basic Auth (Email + API Token)
            self.session.auth = (username, api_token)
            auth_type = "Basic (Cloud)"
        else:
            # Data Center utilise souvent Bearer Auth pour les PAT (Personal Access Tokens)
            # On n'utilise pas self.session.auth pour Bearer, on l'ajoute aux headers
            self.session.headers.update({
                'Authorization': f'Bearer {api_token}'
            })
            auth_type = "Bearer (Data Center PAT)"
            
        self.session.verify = True
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Log discret de la méthode d'auth utilisée
        # print(f"ℹ️ Authentification: {auth_type}")
    
    def get_all_spaces(self, spaces_filter: Optional[List[str]] = None) -> List[Dict]:
        """
        Récupère tous les espaces Confluence.
        
        Cette méthode interroge l'API REST de Confluence pour obtenir la liste
        de tous les espaces accessibles. La pagination est gérée automatiquement.
        
        Args:
            spaces_filter: Liste optionnelle de clés d'espaces à filtrer.
                          Si None, retourne tous les espaces.
        
        Returns:
            List[Dict]: Liste des espaces avec leurs métadonnées (key, name, etc.)
        """
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
                if hasattr(e, 'response') and e.response is not None:
                    print(f"   Code HTTP: {e.response.status_code}")
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message') or error_data.get('errorMessage') or str(error_data)
                        print(f"   Détails: {error_msg}")
                    except:
                        print(f"   Réponse: {e.response.text[:200]}")
                break
        
        # Filtrer si des espaces spécifiques sont demandés
        if spaces_filter:
            # Convertir en set pour une recherche plus efficace
            spaces_filter_set = set(spaces_filter) if isinstance(spaces_filter, list) else spaces_filter
            spaces = [s for s in spaces if s.get('key') in spaces_filter_set]
        
        return spaces
    
    def get_all_pages(self, space_key: str, include_drafts: bool = True, expand: str = 'body.storage') -> List[Dict]:
        """
        Récupère toutes les pages d'un espace.
        
        Cette méthode récupère toutes les pages publiées d'un espace Confluence,
        avec option d'inclure les brouillons (drafts). La pagination est gérée
        automatiquement.
        
        Args:
            space_key: Clé de l'espace Confluence (ex: 'DEV', 'PROD')
            include_drafts: Si True, inclut aussi les pages en brouillon
            expand: Champs à étendre dans la réponse API (ex: 'body.storage,version')
        
        Returns:
            List[Dict]: Liste des pages avec leurs métadonnées complètes
        """
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
            except requests.exceptions.RequestException as e:
                print(f"❌ Erreur lors de la récupération des pages: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"   Code HTTP: {e.response.status_code}")
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
        """
        Récupère les détails d'une page spécifique.
        
        Cette méthode récupère les informations complètes d'une page Confluence
        par son ID, incluant le contenu, les métadonnées et les informations
        d'espace et de version.
        
        Args:
            page_id: ID de la page Confluence
            expand: Champs à étendre dans la réponse API
        
        Returns:
            Optional[Dict]: Dictionnaire contenant les détails de la page,
                           ou None si la page n'existe pas ou n'est pas accessible
        """
        url = f"{self.api_base}/content/{page_id}"
        params = {'expand': expand}
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de la page {page_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Code HTTP: {e.response.status_code}")
        
        return None

