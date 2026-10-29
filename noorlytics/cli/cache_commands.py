"""Cache Management CLI Subcommand

Provides cache-related commands:
- noor cache stats    - Show cache statistics
- noor cache clear    - Clear all cached findings
- noor cache info     - Show cache directory info
"""

from __future__ import annotations

import click
from pathlib import Path

from noorlytics.cache_manager import get_cache


@click.group("cache")
def cache():
    """Manage Noorlytics findings cache.
    
    The cache stores analysis results to provide instant results for
    unchanged files, dramatically improving performance on repeated runs.
    
    Cache is located at: .noor/cache/
    Database: .noor/cache/findings.db (SQLite)
    Hashes: .noor/cache/file_hashes.json
    
    Examples:
      noor cache stats           # Show cache statistics
      noor cache clear           # Clear entire cache
      noor cache info            # Show cache details
    """
    pass


@cache.command("stats")
def cache_stats():
    """Display cache statistics and usage information.
    
    Shows:
    - Total number of cached findings
    - Breakdown by analysis type (analyze, audit-security, gdpr, etc.)
    - Average execution time saved by cache hits
    - Cache storage size
    """
    cache_mgr = get_cache()
    stats = cache_mgr.get_stats()
    
    click.echo(click.style("📊 Cache Statistics", fg="cyan", bold=True))
    click.echo(f"\n  Total cached findings: {stats['total_entries']}")
    
    if stats.get('by_type'):
        click.echo(f"\n  Breakdown by analysis type:")
        for analysis_type, count in sorted(stats['by_type'].items()):
            click.echo(f"    - {analysis_type}: {count} finding(s)")
    
    if stats.get('total_execution_time_ms'):
        total_saved_sec = stats['total_execution_time_ms'] / 1000
        avg_time_ms = stats.get('avg_execution_time_ms', 0)
        click.echo(f"\n  Performance:")
        click.echo(f"    - Total time invested: {total_saved_sec:.1f}s")
        click.echo(f"    - Average per finding: {avg_time_ms:.1f}ms")
    
    # Cache directory size
    try:
        cache_size = cache_mgr.get_cache_dir_size()
        cache_size_mb = cache_size / (1024 * 1024)
        click.echo(f"\n  Storage:")
        click.echo(f"    - Cache directory size: {cache_size_mb:.2f} MB")
    except Exception as e:
        click.echo(f"\n  Storage: Unable to calculate size ({e})")
    
    click.echo(f"\n  Location: {cache_mgr.cache_dir.resolve()}")


@cache.command("clear")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def cache_clear(confirm: bool):
    """Clear all cached findings.
    
    WARNING: This will delete all cached analysis results. The cache will be
    rebuilt on the next analysis run.
    
    Use --confirm to skip the confirmation prompt.
    
    Examples:
      noor cache clear           # Interactive (asks for confirmation)
      noor cache clear --confirm # Non-interactive (clears immediately)
    """
    if not confirm:
        click.echo(click.style("⚠️  This will clear ALL cached findings!", fg="yellow"))
        if not click.confirm("Continue?"):
            click.echo("Cancelled.")
            return
    
    cache_mgr = get_cache()
    cache_mgr.clear()
    
    click.echo(click.style("✅ Cache cleared successfully", fg="green"))


@cache.command("info")
def cache_info():
    """Display detailed cache information.
    
    Shows:
    - Cache location and size
    - Database schema info
    - Hash index size
    - Recommendations for cache management
    """
    cache_mgr = get_cache()
    cache_dir = cache_mgr.cache_dir
    
    click.echo(click.style("ℹ️  Cache Information", fg="cyan", bold=True))
    
    # Location and files
    click.echo(f"\n  Location: {cache_dir.resolve()}")
    
    db_path = cache_mgr.db_path
    if db_path.exists():
        db_size_kb = db_path.stat().st_size / 1024
        click.echo(f"\n  Database:")
        click.echo(f"    - Path: {db_path.resolve()}")
        click.echo(f"    - Size: {db_size_kb:.1f} KB")
    
    hashes_path = cache_dir / "file_hashes.json"
    if hashes_path.exists():
        hashes_size_kb = hashes_path.stat().st_size / 1024
        click.echo(f"\n  File Hashes:")
        click.echo(f"    - Path: {hashes_path.resolve()}")
        click.echo(f"    - Size: {hashes_size_kb:.1f} KB")
    
    state_path = cache_dir / "incremental_state.json"
    if state_path.exists():
        state_size_kb = state_path.stat().st_size / 1024
        click.echo(f"\n  Incremental Analysis State:")
        click.echo(f"    - Path: {state_path.resolve()}")
        click.echo(f"    - Size: {state_size_kb:.1f} KB")
    
    # Recommendations
    stats = cache_mgr.get_stats()
    total_entries = stats.get('total_entries', 0)
    
    click.echo(f"\n  Status: {total_entries} findings cached")
    
    if total_entries == 0:
        click.echo("  💡 Tip: Run analysis to build the cache")
    elif total_entries > 10000:
        click.echo("  💡 Tip: Cache is large; consider 'noor cache clear' if old findings")
    else:
        click.echo("  ✅ Cache is in good state")


@cache.command("reset-hashes")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def cache_reset_hashes(confirm: bool):
    """Reset file hash tracking (forces re-analysis of all files).
    
    This clears the file hash index but keeps cached findings. All files will
    be re-analyzed on next run to update their hashes, but cached results will
    still be used.
    
    Use this if:
    - File modification times are unreliable
    - You want to force hash validation
    - File system timestamps have changed
    
    Examples:
      noor cache reset-hashes           # Interactive
      noor cache reset-hashes --confirm # Non-interactive
    """
    if not confirm:
        click.echo(click.style("⚠️  This will reset file hash tracking!", fg="yellow"))
        if not click.confirm("Continue?"):
            click.echo("Cancelled.")
            return
    
    cache_mgr = get_cache()
    cache_mgr.file_hash_cache.clear()
    
    click.echo(click.style("✅ File hash tracking reset", fg="green"))
