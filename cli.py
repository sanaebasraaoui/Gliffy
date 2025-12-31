#!/usr/bin/env python3
"""
CLI principal pour l'application Gliffy.

Ce module expose une interface en ligne de commande pour gérer les diagrammes Gliffy
dans Confluence et les convertir vers Excalidraw.

Commandes disponibles :
1. scan - Scan global de Confluence (inventaire complet des pages)
2. migrate - Migration des images Gliffy dans les pages Confluence
3. web - Interface web pour la conversion Gliffy → Excalidraw

Auteur: Sanae Basraoui
"""


import argparse
import sys
from pathlib import Path
from confluence_scanner import ConfluenceScanner
from gliffy_migrator import GliffyMigrator
from web_converter import run_server


def parse_common_args(parser):
    """
    Ajoute les arguments communs à toutes les commandes Confluence.
    
    Args:
        parser: L'objet ArgumentParser auquel ajouter les arguments
        
    Les arguments ajoutés sont :
    - --url : URL de base de Confluence (requis)
    - --username : Nom d'utilisateur ou email Confluence (requis)
    - --token : Token API Confluence (requis)
    """
    parser.add_argument(
        '--url',
        required=True,
        help='URL de base de Confluence (ex: https://confluence.example.com)'
    )
    parser.add_argument(
        '--username',
        required=False,
        help='Nom d\'utilisateur ou email Confluence (requis pour Cloud, optionnel pour PAT Data Center)'
    )
    parser.add_argument(
        '--token',
        required=True,
        help='Token API Confluence'
    )


def cmd_scan(args):
    """
    Commande pour scanner Confluence et créer un inventaire.
    
    Cette fonction lance le scan de Confluence et génère un inventaire
    complet des pages avec leurs métadonnées (création, modification,
    hiérarchie, présence de Gliffy, etc.).
    
    Args:
        args: Arguments de la ligne de commande contenant :
            - url: URL de Confluence
            - username: Nom d'utilisateur
            - token: Token API
            - spaces: Liste d'espaces à scanner (optionnel)
            - page: ID de page spécifique (optionnel)
            - format: Format d'export (txt/json)
            - output: Nom du fichier de sortie
    
    Returns:
        int: Code de retour (0 = succès, 1 = erreur)
    """
    scanner = ConfluenceScanner(
        confluence_url=args.url,
        username=args.username,
        api_token=args.token,
        spaces=args.spaces,
        page_id=args.page
    )
    
    inventory = scanner.scan()
    
    if not inventory:
        print("❌ Aucune page trouvée")
        return 1
    
    # Exporter selon le format demandé
    if args.format == 'json':
        scanner.export_json(args.output)
    else:
        # Par défaut, exporter uniquement le TXT dans reports/
        scanner.export_txt()
    
    print(f"\n✅ {len(inventory)} page(s) inventoriée(s)")
    return 0


def cmd_migrate(args):
    """
    Commande pour migrer les images Gliffy dans les pages Confluence.
    
    Cette fonction lance la migration des images Gliffy depuis les attachments
    Confluence et les insère directement dans les pages sous les diagrammes.
    
    Args:
        args: Arguments de la ligne de commande contenant :
            - url: URL de Confluence
            - username: Nom d'utilisateur
            - token: Token API
            - spaces: Liste d'espaces à traiter (optionnel)
            - page: ID de page spécifique (optionnel)
            - report: Nom du fichier de rapport (optionnel)
            - force: Forcer la réinsertion même si déjà présent (optionnel)
    
    Returns:
        int: Code de retour (0 = succès)
    """
    migrator = GliffyMigrator(
        confluence_url=args.url,
        username=args.username,
        api_token=args.token,
        spaces=args.spaces,
        page_id=args.page,
        force=args.force
    )
    
    report = migrator.migrate()
    
    # Toujours exporter le rapport (avec le nom par défaut si non spécifié)
    migrator.export_report(args.report)
    
    return 0


def cmd_web(args):
    """
    Commande pour lancer l'interface web de conversion.
    
    Cette fonction démarre le serveur Flask pour l'interface web permettant
    de convertir des fichiers Gliffy en Excalidraw via une interface graphique.
    
    Args:
        args: Arguments de la ligne de commande contenant :
            - host: Adresse IP du serveur (défaut: 127.0.0.1)
            - port: Port du serveur (défaut: 5000)
            - debug: Mode debug (optionnel)
    
    Returns:
        int: Code de retour (0 = succès)
    """
    run_server(host=args.host, port=args.port, debug=args.debug)
    return 0


def main():
    """
    Point d'entrée principal du CLI.
    
    Cette fonction configure le parser d'arguments, définit les sous-commandes
    (scan, migrate, web) et leurs options, puis exécute la commande demandée.
    
    Returns:
        int: Code de retour (0 = succès, 1 = erreur)
    """
    parser = argparse.ArgumentParser(
        description='Application Gliffy - Outils pour Confluence et Excalidraw',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:

  # Scanner tout Confluence et exporter en TXT (dans reports/)
  python cli.py scan --url https://confluence.example.com --username user --token TOKEN --format txt --output confluence_inventory

  # Scanner un espace spécifique
  python cli.py scan --url https://confluence.example.com --username user --token TOKEN --spaces DEV PROD

  # Scanner une page spécifique
  python cli.py scan --url https://confluence.example.com --username user --token TOKEN --page 123456

  # Migrer les images Gliffy dans tous les espaces
  python cli.py migrate --url https://confluence.example.com --username user --token TOKEN --report migration_report.json

  # Migrer les images Gliffy dans un espace spécifique
  python cli.py migrate --url https://confluence.example.com --username user --token TOKEN --spaces DEV --report migration_report.json

  # Migrer les images Gliffy dans une page spécifique
  python cli.py migrate --url https://confluence.example.com --username user --token TOKEN --page 123456

  # Forcer la réinsertion des images (même si déjà présentes)
  python cli.py migrate --url https://confluence.example.com --username user --token TOKEN --spaces DEV --force

  # Lancer l'interface web de conversion
  python cli.py web --host 0.0.0.0 --port 5000
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande scan
    scan_parser = subparsers.add_parser(
        'scan',
        help='Scanner Confluence et créer un inventaire des pages'
    )
    parse_common_args(scan_parser)
    scan_parser.add_argument(
        '--spaces',
        nargs='+',
        help='Clés d\'espaces à scanner (ex: DEV PROD). Si non spécifié, scanne tous les espaces.'
    )
    scan_parser.add_argument(
        '--page',
        help='ID d\'une page spécifique à scanner'
    )
    scan_parser.add_argument(
        '--format',
        choices=['txt', 'json'],
        default='txt',
        help='Format d\'export (défaut: txt dans reports/)'
    )
    scan_parser.add_argument(
        '--output',
        default='confluence_inventory',
        help='Nom du fichier de sortie (sans extension) (défaut: confluence_inventory). Le fichier .txt sera dans reports/'
    )
    
    # Commande migrate
    migrate_parser = subparsers.add_parser(
        'migrate',
        help='Migrer les images Gliffy dans les pages Confluence'
    )
    parse_common_args(migrate_parser)
    migrate_parser.add_argument(
        '--spaces',
        nargs='+',
        help='Clés d\'espaces à traiter (ex: DEV PROD). Si non spécifié, traite tous les espaces.'
    )
    migrate_parser.add_argument(
        '--page',
        help='ID d\'une page spécifique à traiter'
    )
    migrate_parser.add_argument(
        '--report',
        default='migration_report.json',
        help='Fichier de rapport de migration (défaut: migration_report.json)'
    )
    migrate_parser.add_argument(
        '--force',
        action='store_true',
        help='Forcer la réinsertion des images même si elles existent déjà (ignore l\'idempotence)'
    )
    
    # Commande web
    web_parser = subparsers.add_parser(
        'web',
        help='Lancer l\'interface web pour convertir Gliffy → Excalidraw'
    )
    web_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Adresse IP du serveur (défaut: 127.0.0.1)'
    )
    web_parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port du serveur (défaut: 5000)'
    )
    web_parser.add_argument(
        '--debug',
        action='store_true',
        help='Mode debug'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Exécuter la commande appropriée
    if args.command == 'scan':
        return cmd_scan(args)
    elif args.command == 'migrate':
        return cmd_migrate(args)
    elif args.command == 'web':
        return cmd_web(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())

