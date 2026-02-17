#!/usr/bin/env python3
"""
Load Real News Sources into JustNews Database

This script parses top_100_sources.md and populates the sources 
table in MariaDB with real news sources for end-to-end testing.
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, '/app')

# Load environment
env_file = Path('/app/global.env')
if env_file.exists():
    for line in env_file.read_text().strip().split('\n'):
        if line and not line.startswith('#'):
            key, _, value = line.partition('=')
            os.environ[key] = value

import mysql.connector

def parse_sources_markdown(file_path):
    """Parse global_news_sources.md and extract source data"""
    print(f"Parsing sources from {file_path}...")
    
    sources = []
    try:
        content = Path(file_path).read_text()
        
        # Skip header lines to get to table data
        lines = content.split('\n')
        in_table = False
        
        for line in lines:
            line = line.strip()
            # Detect table start: | Name | Domain | URL | ...
            if '| Name | Domain |' in line:
                in_table = True
                continue
            
            # Skip horizontal separator: | :--- | :--- | ...
            if in_table and '| :---' in line:
                continue
            
            # Parse table rows
            if in_table and line.startswith('|'):
                # Split by pipe and clean
                parts = [p.strip() for p in line.split('|')[1:-1]]  # Remove first/last empty
                
                if len(parts) >= 6:
                    try:
                        source = {
                            'name': parts[0],
                            'domain': parts[1],
                            'url': parts[2],
                            'country': parts[3],
                            'language': parts[4],
                            'type': parts[5],
                            'description': parts[6] if len(parts) > 6 else '',
                        }
                        
                        # Validate URL
                        if source['url'].startswith('http'):
                            sources.append(source)
                    except Exception as e:
                        continue
        
        print(f"✓ Parsed {len(sources)} sources from markdown\n")
        return sources
    except Exception as e:
        print(f"✗ Error parsing markdown: {e}")
        return []


def create_sources_table(cursor):
    """Ensure sources table exists with correct schema"""
    print("Checking sources table schema...")
    
    # Check if table exists
    cursor.execute("SHOW TABLES LIKE 'sources'")
    if cursor.fetchone():
        print("✓ Sources table exists\n")
        return
    
    # Create table if it doesn't exist
    print("Creating sources table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            domain VARCHAR(255) NOT NULL UNIQUE,
            url TEXT NOT NULL,
            country VARCHAR(10),
            language VARCHAR(10),
            description TEXT,
            last_crawl_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_domain (domain)
        )
    """)
    print("✓ Sources table created\n")


def load_sources_to_database(sources, host, port, user, password, database):
    """Load sources into MariaDB"""
    print(f"Connecting to database: {user}@{host}:{port}/{database}")
    
    try:
        cnx = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        cursor = cnx.cursor()
        
        print("✓ Connected to database\n")
        
        # Ensure table exists
        create_sources_table(cursor)
        
        # Load sources
        print(f"Loading {len(sources)} sources into database...\n")
        
        loaded = 0
        skipped = 0
        updated = 0
        
        for i, source in enumerate(sources, 1):
            try:
                # Try to insert
                cursor.execute("""
                    INSERT INTO sources 
                    (name, domain, url, country, language, description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    source['name'],
                    source['domain'],
                    source['url'],
                    source['country'],
                    source['language'],
                    source['description']
                ))
                loaded += 1
                
                if i % 10 == 0:
                    print(f"  ✓ Loaded {i}/100 sources...")
                    
            except mysql.connector.errors.IntegrityError:
                # Source already exists
                skipped += 1
            except Exception as e:
                print(f"  ✗ Error loading {source['name']}: {e}")
                skipped += 1
        
        cnx.commit()
        cursor.close()
        cnx.close()
        
        print(f"\n" + "="*70)
        print("SOURCES LOADED SUCCESSFULLY")
        print("="*70)
        print(f"✓ Inserted: {loaded}")
        print(f"⚠ Skipped (already exist): {skipped}")
        print(f"✓ Total in database: {loaded + skipped}")
        print()
        
        # Verify
        verify_sources(host, port, user, password, database)
        
        return True
        
    except mysql.connector.Error as err:
        print(f"✗ Database error: {err}")
        return False


def verify_sources(host, port, user, password, database):
    """Verify sources were loaded"""
    print("VERIFICATION")
    print("-" * 70)
    
    try:
        cnx = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        cursor = cnx.cursor()
        
        # Total count
        cursor.execute("SELECT COUNT(*) FROM sources")
        total = cursor.fetchone()[0]
        print(f"✓ Total sources in database: {total}")
        
        # Countries represented
        cursor.execute("SELECT COUNT(DISTINCT country) FROM sources")
        countries = cursor.fetchone()[0]
        print(f"✓ Countries: {countries}")
        
        # Languages
        cursor.execute("SELECT COUNT(DISTINCT language) FROM sources")
        languages = cursor.fetchone()[0]
        print(f"✓ Languages: {languages}")
        
        # Sample sources
        cursor.execute("SELECT name, domain, url FROM sources LIMIT 5")
        samples = cursor.fetchall()
        print(f"\n✓ Sample sources:")
        for name, domain, url in samples:
            print(f"    - {name} ({domain})")
        
        # Database size
        cursor.execute("""
            SELECT ROUND(((data_length + index_length) / 1024), 2) as size_kb
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'sources'
        """, (database,))
        size_result = cursor.fetchone()
        if size_result:
            size_kb = size_result[0]
            print(f"\n✓ Sources table size: {size_kb:.2f} KB")
        
        cursor.close()
        cnx.close()
        
        print()
        return True
        
    except Exception as e:
        print(f"✗ Verification error: {e}")
        return False


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("JUSTNEWS SOURCES LOADER")
    print("="*70 + "\n")
    
    # Get database config from environment
    host = os.environ.get('MARIADB_HOST', 'mariadb')
    port = int(os.environ.get('MARIADB_PORT', 3306))
    user = os.environ.get('MARIADB_USER', 'justnews')
    password = os.environ.get('MARIADB_PASSWORD', 'dev_justnews_password')
    database = os.environ.get('MARIADB_DB', 'justnews')
    
    print("Configuration:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")
    print(f"  User: {user}\n")
    
    # Parse sources
    sources = parse_sources_markdown('/app/global_news_sources.md')
    
    if not sources:
        print("✗ No sources found to load")
        return False
    
    # Load to database
    success = load_sources_to_database(sources, host, port, user, password, database)
    
    if success:
        print("="*70)
        print("✅ SOURCES READY FOR CRAWLING")
        print("="*70)
        print("\nNext steps:")
        print("  1. Start justnews system: python run_memory_agent.py")
        print("  2. Run crawl: python run_full_crawl.py")
        print("  3. Monitor: mysql -h mariadb -u {user} -p{password} {database}")
        print()
        return True
    else:
        print("✗ Failed to load sources")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
