# ChromaDB Embeddings Persistence Strategy

## Overview

This guide explains how JustNews DevContainer manages ChromaDB embeddings to ensure they are preserved across container rebuilds and development workflows.

## Configuration Changes

### Before (Ephemeral)
```yaml
chromadb:
  image: chromadb/chroma:0.4.18
  environment:
    - IS_PERSISTENT=FALSE  # ❌ Embeddings lost on container removal
  # NO volumes - embeddings stored only in container memory
```

**Problem:** Every time containers are removed/rebuilt, all embeddings (vector representations of crawled content) are lost. This means re-ingesting data and re-generating embeddings for every dev cycle.

### After (Persistent)
```yaml
chromadb:
  image: chromadb/chroma:0.4.18
  environment:
    - IS_PERSISTENT=TRUE  # ✅ Embeddings persisted to disk
  volumes:
    - chromadb_data:/chroma/data  # ✅ Named volume for embeddings
```

**Benefit:** Embeddings are now preserved across container lifecycles, enabling:
- Fast iteration during development
- Preservation of embedding work between rebuilds
- Backup and recovery of embeddings

## Data Archival Strategy

### Pre-Build Cleanup Script

The pre-build cleanup script ([`.devcontainer/scripts/pre-build-cleanup.sh`](.devcontainer/scripts/pre-build-cleanup.sh)) has been enhanced to archive ChromaDB embeddings before removing containers/volumes.

#### Archival Process

1. **Detect ChromaDB Volumes**
   ```bash
   chromadb_volume=$(docker volume ls --format "{{.Name}}" | grep -i chromadb)
   ```

2. **Archive Volume Data**
   ```bash
   docker run --rm -v "$volume:/chroma_data" -v "$BACKUP_PATH:$BACKUP_PATH" \
       alpine cp -r /chroma_data "$BACKUP_PATH/chromadb_${volume}"
   ```

3. **Archive Container Data**
   ```bash
   docker cp "$container_id:/chroma/data" "$BACKUP_PATH/chromadb_container_${name}"
   ```

4. **Backup Location**
   ```
   ~/.justnews_backups/
   ├── mariadb_20240115_143022/
   │   └── mysql_data_mariadb/
   └── chromadb/
       ├── chromadb_chromadb_data/
       └── chromadb_container_chromadb/
   ```

### Backup Locations

| Data | Location | Persistence |
|------|----------|-------------|
| **MariaDB** | `~/.justnews_backups/mariadb_*/mysql_data*/` | Named volume `mariadb_data:/var/lib/mysql` |
| **ChromaDB** | `~/.justnews_backups/chromadb_/` | Named volume `chromadb_data:/chroma/data` |
| **App Data** | `~/.justnews_backups/app_data/` | Named volume `justnews_data:/app/data` |

## Restoration Workflow

### Quick Restore

If you need to restore embeddings from a backup:

```bash
# List available backups
ls -la ~/.justnews_backups/

# View embeddings in backup
ls -la ~/.justnews_backups/chromadb_*/

# Manually restore (after container is running)
docker cp ~/.justnews_backups/chromadb_chromadb_data/chroma_data \
    <chromadb_container_id>:/chroma/data
```

### Verify Embeddings

```bash
# Check if embeddings are persisted
docker exec chromadb ls -lah /chroma/data/

# Query using ChromaDB HTTP API
curl http://localhost:3307/api/v1/heartbeat
curl http://localhost:3307/api/v1/collections
```

## Environment Variables

### ChromaDB Configuration

| Variable | Value | Purpose |
|----------|-------|---------|
| `IS_PERSISTENT` | `TRUE` | Enable persistence to disk |
| `CHROMA_HOST` | `0.0.0.0` | Listen on all interfaces |
| `CHROMA_PORT` | `8000` | Internal port |
| `CHROMA_API_VERSION` | `v1` | API version to use |

### Related Settings

```yaml
# In docker-compose.yaml
chromadb:
  environment:
    - IS_PERSISTENT=TRUE  # Enable persistence
    - CHROMA_LOG_LEVEL=INFO
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

```bash
# In global.env
CHROMADB_HOST=chromadb
CHROMADB_PORT=8000
CHROMADB_API_VERSION=v1
CHROMADB_TIMEOUT=30
```

## Volume Management

### Named Volumes

```bash
# List all volumes
docker volume ls | grep justnews

# Inspect ChromaDB volume
docker volume inspect ${PROJECT}_chromadb_data

# View volume contents
docker run --rm -v chromadb_data:/data alpine ls -la /data

# Backup volume
docker run --rm -v chromadb_data:/data -v /tmp:/backup alpine \
    cp -r /data /backup/chromadb_backup
```

### Volume Cleanup

```bash
# CAUTION: This will delete embeddings permanently!
docker volume rm chromadb_data

# Safe alternative: Archive first
bash .devcontainer/scripts/pre-build-cleanup.sh
# Then rebuild
docker-compose up
```

## Development Workflow

### Full Clean Rebuild (with archival)
```bash
# Your backup is automatically created
bash .devcontainer/scripts/pre-build-cleanup.sh

# Start fresh with new containers
docker-compose up -d

# ChromaDB starts with same embeddings from backup
# (because volume persists)
```

### Preserve Embeddings Across Rebuilds
```bash
# All embeddings are preserved automatically
# Just run your next build
docker-compose down
docker-compose up -d
# Embeddings are intact
```

### Start Fresh (Discard Embeddings)
```bash
# Keep backup, but create new volume
docker volume rm chromadb_data
docker-compose up -d
# New empty ChromaDB, embeddings recreated from scratch
```

## Troubleshooting

### Embeddings Lost After Rebuild

**Issue:** ChromaDB seems empty after rebuild
**Cause:** Volume was deleted before rebuild (deprecated IS_PERSISTENT=FALSE)
**Solution:**
```bash
# Check backup
ls -la ~/.justnews_backups/chromadb_*/

# Stop containers
docker-compose down

# Restore volume (if available)
docker volume create chromadb_data
docker run --rm -v chromadb_data:/chroma_data -v ~/.justnews_backups/chromadb_:/backup \
    alpine cp -r /backup/* /chroma_data/

# Restart
docker-compose up -d
```

### Volume Permission Errors

**Issue:** "Permission denied" when accessing embeddings
**Solution:**
```bash
# Fix permissions
docker exec chromadb chmod 755 /chroma/data
docker exec chromadb chown -R 1000:1000 /chroma/data
```

### ChromaDB Won't Start

**Issue:** ChromaDB container exits immediately
**Check logs:**
```bash
docker logs chromadb

# Verify volume exists
docker volume ls | grep chromadb

# Check volume health
docker run --rm -v chromadb_data:/data alpine ls -la /data
```

## Performance Considerations

| Aspect | Impact | Mitigation |
|--------|--------|-----------|
| **Disk Space** | Embeddings storage grows with data ingestion | Monitor volume size, archive old volumes |
| **Startup Time** | Embedding loading on startup (slight delay) | Normal, typically <5 seconds |
| **Backup Size** | ChromaDB backups can be large (~500MB+) | Optional: compress backups, rotate old ones |
| **Memory** | Loaded embeddings in memory | ChromaDB handles memory efficiently |

## Best Practices

✅ **DO:**
- Automatically archive before cleanup (script handles this)
- Keep backups in `~/.justnews_backups/` for recovery
- Monitor embeddings directory size
- Test restore procedures periodically
- Document embedding counts and sizes

❌ **DON'T:**
- Manually delete volumes without archival
- Delete backups without review
- Mix persistence modes (IS_PERSISTENT changes require rebuild)
- Assume embeddings survive container removal (volumes must persist)

## Related Files

- [Pre-Build Cleanup Script](.devcontainer/scripts/pre-build-cleanup.sh)
- [Docker Compose Configuration](.devcontainer/docker-compose.yaml)
- [DevContainer Configuration](.devcontainer/devcontainer.json)
- [Global Environment Variables](../../global.env)

## References

- [ChromaDB Persistence Documentation](https://docs.trychroma.com/)
- [Docker Volumes Guide](https://docs.docker.com/storage/volumes/)
- [Docker Compose Volumes](https://docs.docker.com/compose/compose-file/compose-file-v3/#volumes)
