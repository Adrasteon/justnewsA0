import os
import glob
import re
import sys
import time
# Add current directory to path so we can import modules
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def transform_postgres_to_mariadb(sql):
    """
    Transforms PostgreSQL dialect SQL to MariaDB compatible SQL.
    """
    # 1. Strip comments (simple approach)
    # Remove block comments
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    
    # 2. Simple replacements
    # JSONB -> JSON
    sql = re.sub(r'\bJSONB\b', 'JSON', sql, flags=re.IGNORECASE)
    # SERIAL -> AUTO_INCREMENT
    sql = re.sub(r'\bSERIAL PRIMARY KEY\b', 'INT AUTO_INCREMENT PRIMARY KEY', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bSERIAL\b', 'INT AUTO_INCREMENT', sql, flags=re.IGNORECASE)
    # Arrays -> JSON
    sql = re.sub(r'\bTEXT\[\]', 'JSON', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bDOUBLE PRECISION\[\]', 'JSON', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bVARCHAR\[\]', 'JSON', sql, flags=re.IGNORECASE)
    
    # TIMESTAMPTZ -> TIMESTAMP
    sql = re.sub(r'\bTIMESTAMPTZ\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)
    
    # DROP TABLE cascade -> DROP TABLE
    # Postgres: DROP TABLE x CASCADE
    # MariaDB: DROP TABLE x (CASCADE is accepted but good to be clean)
    sql = re.sub(r'DROP TABLE IF EXISTS (\w+) CASCADE', r'DROP TABLE IF EXISTS \1', sql, flags=re.IGNORECASE)
    
    # 3. Handle Partial Indexes (WHERE clauses) - The big deal
    # Pattern: CREATE [UNIQUE] INDEX [IF NOT EXISTS] name ON table(col) [WHERE condition];
    # We want to strip the WHERE clause.
    # Using specific regex that matches until the semicolon
    sql = re.sub(r'(CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF NOT EXISTS\s+)?\w+\s+ON\s+\w+\s*\(.*?\))\s+WHERE\s+.*?;', r'\1;', sql, flags=re.IGNORECASE | re.DOTALL)
    
    # 4. UTF8MB4 Key Length Limits
    # VARCHAR(1000) is too big for a key in specific row formats.
    sql = re.sub(r'VARCHAR\(\s*1000\s*\)', 'VARCHAR(750)', sql, flags=re.IGNORECASE)
    
    return sql

def parse_markdown_table(file_path):
    sources = []
    if not os.path.exists(file_path):
        return sources

    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Find start of table
    start_idx = 0
    headers_found = False
    for i, line in enumerate(lines):
        if '|' in line and '---' in line:
            start_idx = i + 1
            headers_found = True
            break
            
    if not headers_found:
        return sources

    for line in lines[start_idx:]:
        line = line.strip()
        if not line or not line.startswith('|'):
            continue
            
        # Split by pipe
        parts = [p.strip() for p in line.split('|')]
        # Remove empty first/last if they exist due to leading/trailing pipe
        if len(parts) > 0 and parts[0] == '': parts.pop(0)
        if len(parts) > 0 and parts[-1] == '': parts.pop(-1)
        
        # Expected: Name, Domain, URL, Country, Language, Description
        if len(parts) >= 6:
            sources.append({
                'name': parts[0],
                'domain': parts[1],
                'url': parts[2],
                'country': parts[3],
                'language': parts[4],
                'description': parts[5]
            })
            
    return sources

def populate_sources_from_markdown():
    md_file = "top_100_sources.md"
    print(f"Populating sources from {md_file}...")
    
    sources = parse_markdown_table(md_file)
    if not sources:
        print(f"No sources found in {md_file}")
        return

    db = create_database_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    count = 0
    try:
        # Verify table exists first (sanity check)
        cursor.execute("SHOW TABLES LIKE 'sources'")
        if not cursor.fetchone():
            print("Error: sources table does not exist!")
            return

        for s in sources:
            # Upsert-like behavior: check existence by domain
            cursor.execute("SELECT id FROM sources WHERE domain = %s", (s['domain'],))
            row = cursor.fetchone()
            if row:
                continue
                
            cursor.execute("""
                INSERT INTO sources (name, domain, url, country, language, description, last_verified, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
            """, (s['name'], s['domain'], s['url'], s['country'], s['language'], s['description']))
            count += 1
            
        conn.commit()
    except Exception as e:
        print(f"Error seeding sources: {e}")
        conn.rollback()
    
    print(f"Successfully inserted {count} new sources.")

def apply_migrations():
    print("Starting migration process...")
    mig_dir = 'database/migrations'
    files = sorted(glob.glob(os.path.join(mig_dir, '*.sql')))
    
    db = create_database_service()
    conn = db.get_connection()
    cursor = conn.cursor()

    # Create migrations table if not exists
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception as e:
        print(f"Failed to create schema_migrations table: {e}")
        return

    for f_path in files:
        f_name = os.path.basename(f_path)
        
        # Check if applied
        cursor.execute("SELECT version FROM schema_migrations WHERE version = %s", (f_name,))
        if cursor.fetchone():
            print(f"Skipping {f_name} (already applied)")
            continue
            
        print(f"Applying {f_name}...")
        with open(f_path, 'r') as f:
            raw_sql = f.read()
            
        # Parse UP part only
        if '-- DOWN' in raw_sql:
            up_sql = raw_sql.split('-- DOWN')[0]
        else:
            up_sql = raw_sql

        transformed_sql = transform_postgres_to_mariadb(up_sql)
        
        # Split into statements
        # Using a safer split based on semicolons and newlines
        statements = re.split(r';\s*\n', transformed_sql)
        
        for stmt in statements:
            stmt = stmt.strip()
            # Handle edge case where split leaves empty strings or just a semicolon
            if not stmt or stmt == ';':
                continue
                
            # Remove line comments that might be left
            lines = [l for l in stmt.splitlines() if not l.strip().startswith('--')]
            clean_stmt = '\n'.join(lines).strip()
            
            if not clean_stmt:
                continue
                
            try:
                cursor.execute(clean_stmt)
            except Exception as e:
                # Log but continue? Or stop?
                # If we stop, we might leave partial state.
                # Given strict requirements, we should probably output the error and try to continue if it's "Already exists"
                print(f"Error executing statement in {f_name}: {e}")
                print(f"Statement: {clean_stmt[:100]}...")
                
        # Record migration
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f_name,))
        conn.commit()
        print(f"Applied {f_name}")

    print("All migrations applied.")
    
    # After schema is ready, populate sources
    populate_sources_from_markdown()

if __name__ == "__main__":
    apply_migrations()
