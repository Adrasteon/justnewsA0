#!/usr/bin/env python
"""
Crawl profile assignment and validation.
Ensures all sources have appropriate crawl profiles configured.
"""

import os
import sys
import yaml

sys.path.insert(0, os.getcwd())

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("crawl_profiles")


def load_crawl_profiles(config_file: str = 'config/crawl_profiles.yaml') -> dict:
    """Load crawl profile definitions from YAML."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Failed to load crawl profiles: {e}")
        return {}


def get_profile_for_domain(domain: str, profiles_config: dict) -> str:
    """
    Determine the crawl profile to use for a given domain.
    Checks domain-specific profiles first, then returns default.
    """
    profiles = profiles_config.get('profiles', {})
    
    # Check for domain-specific profile definition
    for profile_name, profile_config in profiles.items():
        domains = profile_config.get('domains', [])
        if domain in domains:
            return profile_name
    
    # Return default profile
    return profiles_config.get('defaults', {}).get('profile', 'standard_crawl4ai')


def assign_profiles_to_sources(update_db: bool = False):
    """
    Load profiles and assign to all sources in database.
    """
    try:
        profiles_config = load_crawl_profiles()
        
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        # Get all sources
        cursor.execute("SELECT id, domain FROM sources ORDER BY domain")
        sources = cursor.fetchall()
        total = len(sources)
        
        print(f"\n🔧 Crawl Profile Assignment")
        print("=" * 80)
        print(f"Sources to process: {total}")
        print(f"Updating database: {update_db}\n")
        
        # Count profile assignments
        profile_counts = {}
        assignments = []
        
        for source in sources:
            source_id = source['id']
            domain = source['domain']
            profile = get_profile_for_domain(domain, profiles_config)
            
            profile_counts[profile] = profile_counts.get(profile, 0) + 1
            assignments.append({
                'id': source_id,
                'domain': domain,
                'profile': profile
            })
        
        # Display summary
        print("📊 Profile Assignment Summary")
        print("-" * 80)
        for profile, count in sorted(profile_counts.items(), key=lambda x: -x[1]):
            pct = (count / total) * 100
            print(f"  {profile:30s} : {count:4d} sources ({pct:5.1f}%)")
        
        # Update database if requested
        if update_db:
            update_query = """
            UPDATE sources 
            SET metadata = JSON_SET(
                    COALESCE(metadata, '{}'),
                    '$.crawl_profile', %s
                )
            WHERE id = %s
            """
            
            for assignment in assignments:
                cursor.execute(update_query, (
                    assignment['profile'],
                    assignment['id']
                ))
            
            conn.commit()
            print(f"\n✅ Updated {len(assignments)} sources in database")
            logger.info(f"Assigned crawl profiles to {len(assignments)} sources")
        else:
            print("\n⚠️  Dry-run mode. Use --update-db to save assignments.")
        
        # Show sample assignments
        print("\n📋 Sample Profile Assignments (first 10)")
        print("-" * 80)
        for assignment in assignments[:10]:
            print(f"  {assignment['domain']:30s} → {assignment['profile']}")
        
        sql_state = cursor.execute("SELECT COUNT(*) as c FROM sources WHERE metadata IS NOT NULL AND JSON_EXTRACT(metadata, '$.crawl_profile') IS NOT NULL")
        result = cursor.fetchone()
        existing = result['c'] if result else 0
        print(f"\n📈 Database status: {existing} sources now have profiles configured")
        
        return assignments
        
    except Exception as e:
        logger.error(f"Profile assignment error: {e}")
        raise
    finally:
        cursor.close()
        db_service.close()


def validate_profile_config():
    """
    Validate that crawl profile configuration is complete and valid.
    """
    try:
        profiles_config = load_crawl_profiles()
        
        print("\n✓ Crawl Profile Configuration Validation")
        print("=" * 80)
        
        # Check structure
        if 'profiles' not in profiles_config:
            print("❌ No profiles found in configuration")
            return False
        
        if 'defaults' not in profiles_config:
            print("❌ No defaults found in configuration")
            return False
        
        default_profile = profiles_config['defaults'].get('profile')
        if not default_profile:
            print("❌ No default profile specified")
            return False
        
        profiles = profiles_config['profiles']
        print(f"✅ {len(profiles)} profiles defined")
        print(f"✅ Default profile: {default_profile}")
        
        # List all profiles
        print("\n📋 Defined Profiles:")
        for profile_name in sorted(profiles.keys()):
            profile = profiles[profile_name]
            desc = profile.get('description', 'No description')
            domains = len(profile.get('domains', []))
            print(f"  • {profile_name:30s} : {desc} ({domains} domains)")
        
        print("\n✅ Profile configuration is valid")
        return True
        
    except Exception as e:
        logger.error(f"Configuration validation error: {e}")
        print(f"❌ Configuration validation failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage crawl profile assignments')
    parser.add_argument('--validate', action='store_true', help='Validate profile configuration')
    parser.add_argument('--assign', action='store_true', help='Perform profile assignments')
    parser.add_argument('--update-db', action='store_true', help='Update database with assignments')
    args = parser.parse_args()
    
    if args.validate or (not args.validate and not args.assign):
        validate_profile_config()
    
    if args.assign or args.update_db:
        assign_profiles_to_sources(update_db=args.update_db)
