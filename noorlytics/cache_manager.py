"""Cache Manager for Noorlytics Findings

Provides persistent caching of analysis findings to enable:
- Instant results for repeated analysis
- Incremental analysis (only re-scan changed files)
- Cache invalidation based on file hash
- Performance tracking and metrics
"""

from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, UTC
import sqlite3
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry for a file's analysis results."""
    file_path: str
    file_hash: str
    file_size: int
    analysis_type: str  # "analyze", "suggest", "audit-security", "gdpr", etc.
    findings: Dict[str, Any]
    timestamp: str
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class FileHashCache:
    """Simple file hash caching to detect changes."""
    
    def __init__(self, cache_dir: Path = Path(".noor/cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hashes_file = cache_dir / "file_hashes.json"
        self._hashes: Dict[str, str] = self._load_hashes()
    
    def _load_hashes(self) -> Dict[str, str]:
        """Load cached file hashes from disk."""
        if self.hashes_file.exists():
            try:
                return json.loads(self.hashes_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load file hashes: {e}")
        return {}
    
    def _save_hashes(self) -> None:
        """Save file hashes to disk."""
        try:
            self.hashes_file.write_text(json.dumps(self._hashes, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save file hashes: {e}")
    
    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to hash {file_path}: {e}")
            return ""
    
    def has_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last cache."""
        path_str = str(file_path.resolve())
        current_hash = self._compute_file_hash(file_path)
        
        if not current_hash:
            return True  # File unreadable, treat as changed
        
        cached_hash = self._hashes.get(path_str)
        changed = cached_hash != current_hash
        
        if changed or not cached_hash:
            self._hashes[path_str] = current_hash
            self._save_hashes()
        
        return changed
    
    def invalidate(self, file_path: Path) -> None:
        """Remove file from hash cache."""
        path_str = str(file_path.resolve())
        if path_str in self._hashes:
            del self._hashes[path_str]
            self._save_hashes()
    
    def clear(self) -> None:
        """Clear all cached hashes."""
        self._hashes.clear()
        self._save_hashes()


class FindingsCache:
    """SQLite-backed cache for analysis findings."""
    
    def __init__(self, cache_dir: Path = Path(".noor/cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_dir / "findings.db"
        self._init_db()
        self.file_hash_cache = FileHashCache(cache_dir)
    
    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS findings_cache (
                    id INTEGER PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER,
                    analysis_type TEXT NOT NULL,
                    findings_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    execution_time_ms REAL,
                    UNIQUE(file_path, analysis_type)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path 
                ON findings_cache(file_path)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_analysis_type 
                ON findings_cache(analysis_type)
            """)
            conn.commit()
        finally:
            conn.close()
    
    def get(
        self,
        file_path: Path,
        analysis_type: str,
        allow_stale: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached findings for a file.
        
        Args:
            file_path: Path to the file
            analysis_type: Type of analysis (e.g., "analyze", "suggest")
            allow_stale: If False, check if file has changed
        
        Returns:
            Cached findings or None if not found or stale
        """
        if not allow_stale and self.file_hash_cache.has_changed(file_path):
            return None  # File changed, cache is stale
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT findings_json FROM findings_cache
                WHERE file_path = ? AND analysis_type = ?
                """,
                (str(file_path.resolve()), analysis_type)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        finally:
            conn.close()
        
        return None
    
    def set(
        self,
        file_path: Path,
        analysis_type: str,
        findings: Dict[str, Any],
        execution_time_ms: float
    ) -> None:
        """
        Store findings in cache.
        
        Args:
            file_path: Path to the file
            analysis_type: Type of analysis
            findings: Analysis findings dictionary
            execution_time_ms: Time taken to generate findings
        """
        try:
            path_resolved = str(file_path.resolve())
            file_hash = self.file_hash_cache._compute_file_hash(file_path)
            file_size = file_path.stat().st_size if file_path.exists() else 0
            timestamp = datetime.now(UTC).isoformat()
            
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO findings_cache
                    (file_path, file_hash, file_size, analysis_type, findings_json, timestamp, execution_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path_resolved,
                        file_hash,
                        file_size,
                        analysis_type,
                        json.dumps(findings),
                        timestamp,
                        execution_time_ms
                    )
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")
    
    def invalidate(self, file_path: Path, analysis_type: Optional[str] = None) -> None:
        """
        Invalidate cache for a file.
        
        Args:
            file_path: Path to invalidate
            analysis_type: If provided, only invalidate this type; otherwise invalidate all
        """
        try:
            path_resolved = str(file_path.resolve())
            conn = sqlite3.connect(self.db_path)
            try:
                if analysis_type:
                    conn.execute(
                        "DELETE FROM findings_cache WHERE file_path = ? AND analysis_type = ?",
                        (path_resolved, analysis_type)
                    )
                else:
                    conn.execute(
                        "DELETE FROM findings_cache WHERE file_path = ?",
                        (path_resolved,)
                    )
                conn.commit()
            finally:
                conn.close()
            
            self.file_hash_cache.invalidate(file_path)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM findings_cache")
            total_entries = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT analysis_type, COUNT(*) FROM findings_cache GROUP BY analysis_type"
            )
            by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor = conn.execute(
                "SELECT SUM(execution_time_ms) FROM findings_cache"
            )
            total_time_ms = cursor.fetchone()[0] or 0
            
            return {
                "total_entries": total_entries,
                "by_type": by_type,
                "total_execution_time_ms": total_time_ms,
                "avg_execution_time_ms": total_time_ms / total_entries if total_entries > 0 else 0,
            }
        finally:
            conn.close()
    
    def clear(self) -> None:
        """Clear all cached findings."""
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("DELETE FROM findings_cache")
                conn.commit()
            finally:
                conn.close()
            
            self.file_hash_cache.clear()
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
    
    def get_cache_dir_size(self) -> int:
        """Get total size of cache directory in bytes."""
        total = 0
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total


# Global cache instance
_global_cache: Optional[FindingsCache] = None


def get_cache(cache_dir: Path = Path(".noor/cache")) -> FindingsCache:
    """Get or create global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = FindingsCache(cache_dir)
    return _global_cache


def reset_cache() -> None:
    """Reset global cache instance (for testing)."""
    global _global_cache
    _global_cache = None
