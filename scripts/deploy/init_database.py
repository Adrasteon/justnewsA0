#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add the project root to Python path FIRST
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.common.auth_models import create_user_tables  # noqa: E402
from agents.common.database import (  # noqa: E402
    execute_query,
    initialize_connection_pool,
)
from common.observability import get_logger  # noqa: E402

"""
Database initialization script for JustNews Authentication System

Creates all necessary tables for user authentication, sessions, and password resets.
Run this script once to set up the authentication database schema.
"""

# Set up logging
logger = get_logger(__name__)


def create_initial_admin_user():
    """Create an initial admin user for testing"""
    from agents.common.auth_models import UserCreate, UserRole, create_user

    try:
        admin_user = UserCreate(
            email="admin@justnews.com",
            username="admin",
            full_name="System Administrator",
            password="Admin123!@#",
            role=UserRole.ADMIN,
        )

        user_id = create_user(admin_user)
        if user_id:
            logger.info(f"✅ Created initial admin user with ID: {user_id}")
            logger.info("   Username: admin")
            logger.info("   Email: admin@justnews.com")
            logger.info("   Password: Admin123!@#")
            logger.info("   ⚠️  Please change this password after first login!")
        else:
            logger.warning("⚠️  Failed to create initial admin user")

    except Exception as e:
        logger.error(f"❌ Error creating initial admin user: {e}")


def create_knowledge_graph_tables():
    """Create tables for knowledge graph data if they don't exist"""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS articles (
            article_id VARCHAR(255) PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            domain VARCHAR(255),
            published_date TIMESTAMP,
            content TEXT,
            news_score DECIMAL(3,2),
            extraction_method VARCHAR(100),
            publisher VARCHAR(255),
            canonical_url TEXT,
            entities JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entities (
            entity_id VARCHAR(255) PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type VARCHAR(100),
            mention_count INTEGER DEFAULT 0,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            aliases JSONB,
            cluster_size INTEGER DEFAULT 1,
            confidence_score DECIMAL(3,2),
            properties JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationships (
            relationship_id SERIAL PRIMARY KEY,
            source_entity_id VARCHAR(255) REFERENCES entities(entity_id),
            target_entity_id VARCHAR(255) REFERENCES entities(entity_id),
            relationship_type VARCHAR(100) NOT NULL,
            strength DECIMAL(5,4),
            confidence DECIMAL(5,4),
            context TEXT,
            timestamp TIMESTAMP,
            co_occurrence_count INTEGER DEFAULT 0,
            proximity_score DECIMAL(5,4),
            properties JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles(domain)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_entity_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_entity_id)
        """,
    ]

    import re

    def adapt_sql_for_mariadb(sql: str) -> str:
        s = sql
        s = s.replace("JSONB", "JSON")
        s = re.sub(r"\bSERIAL\b", "INT AUTO_INCREMENT", s)
        s = s.replace("TIMESTAMPTZ", "TIMESTAMP")
        s = re.sub(r"\bTEXT\[\]|\bTEXT\s*\[\s*\]", "JSON", s)
        return s

    for i, query in enumerate(queries, 1):
        try:
            adapted_query = adapt_sql_for_mariadb(query)
            execute_query(adapted_query, fetch=False)
            logger.info(f"✅ Created knowledge graph table {i}/{len(queries)}")
        except Exception as e:
            logger.error(f"❌ Error creating knowledge graph table {i}: {e}")
            raise

    # Create orchestrator_leases table for GPU orchestrator durable leases
    lease_query = """
    CREATE TABLE IF NOT EXISTS orchestrator_leases (
        token VARCHAR(64) PRIMARY KEY,
        agent_name VARCHAR(255) NOT NULL,
        gpu_index INT NULL,
        mode VARCHAR(16) NOT NULL DEFAULT 'gpu',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NULL,
        last_heartbeat TIMESTAMP NULL,
        metadata JSON NULL
    ) ENGINE=InnoDB;
    """
    try:
        execute_query(lease_query, fetch=False)
        logger.info("✅ orchestrator_leases table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating orchestrator_leases table: {e}")
        raise

    pools_query = """
    CREATE TABLE IF NOT EXISTS worker_pools (
        pool_id VARCHAR(128) PRIMARY KEY,
        agent_name VARCHAR(255) NULL,
        model_id VARCHAR(255) NULL,
        adapter VARCHAR(255) NULL,
        desired_workers INT NOT NULL DEFAULT 0,
        spawned_workers INT NOT NULL DEFAULT 0,
        started_at TIMESTAMP NULL,
        last_heartbeat TIMESTAMP NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'starting',
        hold_seconds INT NOT NULL DEFAULT 600,
        metadata JSON NULL
    ) ENGINE=InnoDB;
    """
    try:
        execute_query(pools_query, fetch=False)
        logger.info("✅ worker_pools table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating worker_pools table: {e}")
        raise

    # Create orchestrator_jobs table for persistent job store
    jobs_query = """
    CREATE TABLE IF NOT EXISTS orchestrator_jobs (
        job_id VARCHAR(128) PRIMARY KEY,
        type VARCHAR(64) NOT NULL,
        payload JSON NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        owner_pool VARCHAR(128) NULL,
        attempts INT NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL,
        last_error TEXT NULL
    ) ENGINE=InnoDB;
    """
    try:
        execute_query(jobs_query, fetch=False)
        logger.info("✅ orchestrator_jobs table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating orchestrator_jobs table: {e}")
        raise


def main():
    """Main initialization function"""
    logger.info("🚀 Starting JustNews Database Initialization")
    logger.info("=" * 60)

    # Check environment variables (migrated to MariaDB)
    required_env_vars = [
        "MARIADB_HOST",
        "MARIADB_DB",
        "MARIADB_USER",
        "MARIADB_PASSWORD",
    ]

    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(
            f"❌ Missing required environment variables: {', '.join(missing_vars)}"
        )
        logger.error(
            "Please set these environment variables before running this script:"
        )
        for var in missing_vars:
            logger.error(f"  export {var}=<value>")
        sys.exit(1)

    logger.info("✅ Environment variables configured")

    try:
        # Initialize connection pool
        logger.info("🔌 Initializing database connection pool...")
        initialize_connection_pool()
        logger.info("✅ Database connection pool initialized")

        # Create authentication tables
        logger.info("🔐 Creating authentication tables...")
        create_user_tables()
        logger.info("✅ Authentication tables created")

        # Create knowledge graph tables
        logger.info("🕸️  Creating knowledge graph tables...")
        create_knowledge_graph_tables()
        logger.info("✅ Knowledge graph tables created")

        # Create initial admin user
        logger.info("👤 Creating initial admin user...")
        create_initial_admin_user()

        logger.info("=" * 60)
        logger.info("🎉 Database initialization completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Start the API server: python -m agents.archive.archive_api")
        logger.info("2. Test authentication: POST /auth/login with admin credentials")
        logger.info("3. Access API docs: http://localhost:8021/docs")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("Please check your database configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
