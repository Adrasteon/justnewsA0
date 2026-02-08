"""Model store helper for atomic per-agent model copies.

Provides a small API to stage, finalize, and resolve agent model paths.
Implements atomic swaps using directory rename and symlink updates, and
writes a minimal manifest.json with checksum metadata.

Design goals:
- Keep operations atomic on the same filesystem (rename / symlink swap).
- Minimal dependencies (std lib only).
- Clear failures and retries for robustness.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelManifest:
    version: str
    checksum: str
    metadata: dict

    def to_dict(self) -> dict:
        return {"version": self.version, "checksum": self.checksum, "metadata": self.metadata}


class ModelStoreError(Exception):
    pass


class ModelStore:
    """Manage per-agent canonical model directories.

    Layout:
      root/
        {agent}/
          versions/
            v{timestamp_or_tag}/...   # full model files
          current -> versions/v{...}  # symlink

    Usage:
      store = ModelStore(Path('/models'))
      with store.stage_new('scout', 'v20250826') as tmp_path:
          # write model files into tmp_path
      store.finalize('scout', 'v20250826')  # atomic swap

    Methods are implemented to be robust to partial writes and to prefer
    atomic rename/symlink operations.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.versions_name = "versions"
        self.current_name = "current"
        self.manifest_name = "manifest.json"
        os.makedirs(self.root, exist_ok=True)

    def agent_root(self, agent: str) -> Path:
        return self.root / agent

    def versions_root(self, agent: str) -> Path:
        return self.agent_root(agent) / self.versions_name

    def version_path(self, agent: str, version: str) -> Path:
        return self.versions_root(agent) / version

    def current_path(self, agent: str) -> Path:
        return self.agent_root(agent) / self.current_name

    @contextmanager
    def stage_new(self, agent: str, version: str) -> Iterator[Path]:
        """Context manager returns a tmp path to write model files.

        The caller must write the full model into the tmp path. On success the
        caller should exit the context normally and then call finalize(). If an
        exception occurs, the tmp directory is removed.
        """
        versions = self.versions_root(agent)
        tmp = versions / f"{version}.tmp"
        try:
            os.makedirs(tmp, exist_ok=False)
        except FileExistsError:
            raise ModelStoreError(f"Staging path already exists: {tmp}")
        try:
            yield tmp
        except Exception:
            # clean up on error
            try:
                shutil.rmtree(tmp)
            except Exception:
                pass
            raise

    def compute_checksum(self, path: Path) -> str:
        """Compute a checksum for the contents of a directory.

        This walks files in sorted order and computes a sha256 over their bytes
        to produce a deterministic checksum for the model directory.
        """
        h = hashlib.sha256()
        if not path.exists():
            return ""
        for root, _, files in os.walk(path):
            files = sorted(files)
            for fname in files:
                # skip manifest file to allow writing manifest after checksum
                if fname == self.manifest_name:
                    continue
                fpath = Path(root) / fname
                # include relative path so structure changes affect checksum
                rel = str(fpath.relative_to(path)).encode("utf-8")
                h.update(rel)
                with open(fpath, "rb") as fh:
                    while True:
                        chunk = fh.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
        return h.hexdigest()

    def write_manifest(self, version_dir: Path, manifest: ModelManifest) -> None:
        mf = version_dir / self.manifest_name
        with open(mf, "w", encoding="utf-8") as fh:
            json.dump(manifest.to_dict(), fh, indent=2)

    def finalize(
        self,
        agent: str,
        version: str,
        *,
        metadata: dict | None = None,
        validate: bool = True,
    ) -> None:
        """Finalize a staged version by removing .tmp suffix and updating 'current' symlink.

        Steps:
         - Ensure staged path exists (versions/{version}.tmp)
         - Compute checksum and write manifest
         - Rename staged -> versions/{version}
         - Update agent/current symlink to point to versions/{version}
        """
        versions = self.versions_root(agent)
        staged = versions / f"{version}.tmp"
        target = versions / version
        if not staged.exists():
            raise ModelStoreError(f"Staged path not found: {staged}")
        if target.exists():
            raise ModelStoreError(f"Target version already exists: {target}")

        # Optionally validate
        checksum = self.compute_checksum(staged)
        manifest = ModelManifest(version=version, checksum=checksum, metadata=metadata or {})
        # write manifest into staged
        self.write_manifest(staged, manifest)

        # atomic rename (move tmp -> version)
        os.rename(staged, target)

        # update symlink atomically
        agent_root = self.agent_root(agent)
        current = self.current_path(agent)
        rel = os.path.relpath(target, agent_root)
        tmp_link = agent_root / f".{self.current_name}.tmp"
        # create a temporary symlink then rename it to 'current'
        if tmp_link.exists():
            try:
                tmp_link.unlink()
            except Exception:
                pass
        os.symlink(rel, tmp_link)
        # atomic replace
        try:
            os.replace(tmp_link, current)
        except Exception as e:
            # best-effort cleanup
            try:
                tmp_link.unlink()
            except Exception:
                pass
            raise ModelStoreError(f"Failed to update symlink: {e}")

    def get_current(self, agent: str) -> Path | None:
        """Return the resolved current path or None if not found."""
        current = self.current_path(agent)
        if not current.exists():
            return None
        try:
            # resolve the symlink relative to agent_root
            agent_root = self.agent_root(agent)
            target = (agent_root / os.readlink(current)).resolve()
            return target
        except Exception:
            # fallback: if current is a directory return it
            if current.is_dir():
                return current.resolve()
            return None

    def verify_manifest(self, agent: str, version: str) -> bool:
        vp = self.version_path(agent, version)
        mf = vp / self.manifest_name
        if not mf.exists():
            return False
        with open(mf, encoding="utf-8") as fh:
            data = json.load(fh)
        expected = data.get("checksum", "")
        actual = self.compute_checksum(vp)
        return expected == actual
