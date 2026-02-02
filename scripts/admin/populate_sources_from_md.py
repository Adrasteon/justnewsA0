import os
import sys
import argparse

# Add project root to path
sys.path.insert(0, os.getcwd())

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("populate_sources")

def parse_markdown_table(file_path):
    sources = []
    with open(file_path) as f:
        lines = f.readlines()

    # Skip header lines (start from line with |BBC News|)
    # Finding the separator line |---|
    start_idx = 0
    for i, line in enumerate(lines):
        if '|---|' in line:
            start_idx = i + 1
            break

    for line in lines[start_idx:]:
        if not line.strip().startswith('|'):
            continue

        parts = [p.strip() for p in line.split('|')]
        # Parts will look like: ['', 'Name', 'Domain', 'URL', 'Country', 'Language', 'Region/Desc', 'Desc/Region', 'EditorialAngle', '']
        # Supports 6-column (old), 7-column (with Region), and 8-column (with Editorial Angle) formats
        # 6-col: | Name | Domain | URL | Country | Language | Description |
        # 7-col: | Name | Domain | URL | Country | Language | Region | Description |
        # 8-col: | Name | Domain | URL | Country | Language | Region | Description | Editorial Angle |
        
        # Need at least 8 parts (considering split includes empty first and last elements)
        if len(parts) < 8:
            continue
            
        # Skip header rows and separator rows
        if not parts[1] or parts[1] in ['Name', '---']:
            continue
            
        # Check if this is 8-column format (both Region and Editorial Angle present)
        if len(parts) >= 10 and parts[6] and not parts[6].startswith('http') and not parts[6].startswith('www'):
            # Could be 7-col or 8-col; check if parts[7] looks like a description or Editorial Angle
            # 8-col: parts[7] is Description, parts[8] is Editorial Angle
            # 7-col: parts[7] is Description
            # Editorial angles often contain "/" or specific keywords
            sources.append({
                'name': parts[1],
                'domain': parts[2],
                'url': parts[3],
                'country': parts[4],
                'language': parts[5],
                'description': parts[7] if len(parts) >= 8 else parts[6],
                # Region is at parts[6], Editorial Angle at parts[8] (if 8-col), but we store description
            })
        elif len(parts) >= 8:
            # 6-column old format: Name | Domain | URL | Country | Language | Description
            sources.append({
                'name': parts[1],
                'domain': parts[2],
                'url': parts[3],
                'country': parts[4],
                'language': parts[5],
                'description': parts[6]
            })
    return sources

def populate_db(sources):
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor()

        updated = 0

        # Check if table exists
        cursor.execute("SHOW TABLES LIKE 'sources'")
        if not cursor.fetchone():
            print("Table 'sources' does not exist! Creating it based on rough schema...")
            # Basic schema just in case, though it should exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    domain VARCHAR(255) UNIQUE,
                    url VARCHAR(500),
                    name VARCHAR(255),
                    description TEXT,
                    country VARCHAR(10),
                    language VARCHAR(10),
                    last_verified DATETIME,
                    paywall BOOLEAN DEFAULT FALSE,
                    paywall_type VARCHAR(50),
                    metadata JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        insert_query = """
        INSERT INTO sources (domain, url, name, description, country, language, last_verified, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            url = VALUES(url),
            name = VALUES(name),
            description = VALUES(description),
            country = VALUES(country),
            language = VALUES(language),
            last_verified = NOW(),
            updated_at = NOW()
        """

        for s in sources:
            try:
                cursor.execute(insert_query, (
                    s['domain'],
                    s['url'],
                    s['name'],
                    s['description'],
                    s['country'],
                    s['language']
                ))
                updated += 1
            except Exception as e:
                logger.error(f"Error inserting {s['domain']}: {e}")
                print(f"Error inserting {s['domain']}: {e}")

        conn.commit()
        logger.info(f"Processed {len(sources)} sources. Succesfully upserted {updated}.")
        print(f"Processed {len(sources)} sources. Succesfully upserted {updated}.")
        cursor.close()
        db_service.close()
    except Exception as e:
        logger.error(f"Database error: {e}")
        print(f"Database error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Populate sources from markdown file')
    parser.add_argument('--file', default='top_100_sources.md', help='Markdown file to parse')
    args = parser.parse_args()
    
    md_file = args.file
    if not os.path.exists(md_file):
        print(f"File {md_file} not found.")
        sys.exit(1)

    sources = parse_markdown_table(md_file)
    print(f"Components found in MD: {len(sources)}")
    populate_db(sources)
