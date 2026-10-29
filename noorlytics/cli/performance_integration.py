"""Phase 5: CLI Integration for Performance & Scalability Features

Integrates the Phase 4 performance modules (caching, benchmarking, parallel processing,
incremental analysis) into the CLI commands.

This module provides decorators and helpers to add performance features to existing
commands with minimal code changes.
"""

from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Optional, Callable, Any, List
from functools import wraps

import click

from noorlytics.cache_manager import get_cache, FindingsCache
from noorlytics.performance_benchmark import PerformanceMonitor, PerformanceBenchmark
from noorlytics.parallel_processor import (
    ParallelAnalyzer,
    IncrementalAnalysisTracker,
    ProgressTracker,
)

logger = logging.getLogger(__name__)


class PerformanceContext:
    """Context manager for performance tracking during CLI commands."""
    
    def __init__(
        self,
        command_name: str,
        enable_cache: bool = True,
        enable_benchmark: bool = False,
        reports_dir: Path = Path("reports"),
    ):
        self.command_name = command_name
        self.enable_cache = enable_cache
        self.enable_benchmark = enable_benchmark
        self.reports_dir = reports_dir
        
        self.cache: Optional[FindingsCache] = None
        self.monitor: Optional[PerformanceMonitor] = None
        self.benchmark: Optional[PerformanceBenchmark] = None
    
    def __enter__(self):
        """Initialize performance tracking."""
        if self.enable_cache:
            self.cache = get_cache()
        
        if self.enable_benchmark:
            self.monitor = PerformanceMonitor(self.command_name)
            self.benchmark = PerformanceBenchmark(self.reports_dir)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalize performance tracking and save results."""
        if self.enable_benchmark and self.monitor:
            metrics = self.monitor.finish()
            
            if self.benchmark:
                self.benchmark.record(metrics)
            
            # Print metrics summary
            click.echo(click.style("\n📊 Performance Metrics:", fg="cyan", bold=True))
            for line in str(metrics).split("\n"):
                click.echo(f"  {line}")
            
            click.echo(click.style(f"📈 Saved to: {self.benchmark.results_file}", fg="green"))
    
    def get_cached_findings(
        self,
        file_path: Path,
        analysis_type: str,
        allow_stale: bool = False,
    ) -> Optional[dict]:
        """Retrieve cached findings if available."""
        if not self.cache:
            return None
        
        return self.cache.get(file_path, analysis_type, allow_stale=allow_stale)
    
    def cache_findings(
        self,
        file_path: Path,
        analysis_type: str,
        findings: dict,
        execution_time_ms: float,
    ) -> None:
        """Store findings in cache."""
        if not self.cache:
            return
        
        self.cache.set(file_path, analysis_type, findings, execution_time_ms)
    
    def get_cache_stats(self) -> Optional[dict]:
        """Get cache statistics."""
        if not self.cache:
            return None
        
        return self.cache.get_stats()
    
    def record_file_analysis(self, file_path: Path, cache_hit: bool = False) -> None:
        """Record file analysis for metrics."""
        if self.monitor:
            self.monitor.add_file(file_path, cache_hit=cache_hit)


def with_performance_context(
    command_name: str,
    enable_cache: bool = True,
    enable_benchmark: bool = False,
):
    """Decorator to add performance context to CLI commands.
    
    Usage:
        @with_performance_context("analyze", enable_cache=True)
        def analyze_cmd(state, path):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state, *args, **kwargs):
            # Extract performance flags from kwargs
            enable_cache_flag = kwargs.pop("cache", True)
            enable_benchmark_flag = kwargs.pop("benchmark", False)
            
            with PerformanceContext(
                command_name=command_name,
                enable_cache=enable_cache and enable_cache_flag,
                enable_benchmark=enable_benchmark or enable_benchmark_flag,
                reports_dir=state.reports_dir,
            ) as perf_ctx:
                # Pass context to function
                return func(state, *args, perf_ctx=perf_ctx, **kwargs)
        
        return wrapper
    
    return decorator


class CLICommandBuilder:
    """Builder for CLI commands with performance features."""
    
    def __init__(self, state):
        self.state = state
        self.parallel_workers = 4
        self.enable_incremental = False
        self.enable_cache = True
        self.enable_benchmark = False
    
    def set_parallel_workers(self, workers: int) -> CLICommandBuilder:
        """Set number of parallel workers."""
        self.parallel_workers = max(1, workers)
        return self
    
    def enable_incremental_analysis(self, enable: bool = True) -> CLICommandBuilder:
        """Enable incremental analysis."""
        self.enable_incremental = enable
        return self
    
    def enable_caching(self, enable: bool = True) -> CLICommandBuilder:
        """Enable findings cache."""
        self.enable_cache = enable
        return self
    
    def enable_performance_benchmark(self, enable: bool = True) -> CLICommandBuilder:
        """Enable performance benchmarking."""
        self.enable_benchmark = enable
        return self
    
    def get_files_for_analysis(
        self,
        files: List[Path],
        analysis_type: str,
    ) -> tuple[List[Path], List[Path]]:
        """
        Get files to analyze, accounting for caching and incremental analysis.
        
        Returns: (files_to_analyze, cached_files)
        """
        if not self.enable_incremental:
            return files, []
        
        tracker = IncrementalAnalysisTracker()
        changed, unchanged = tracker.get_files_to_analyze(files, analysis_type)
        
        click.echo(click.style(
            f"📊 Incremental Analysis: {len(changed)} changed, {len(unchanged)} unchanged",
            fg="cyan"
        ))
        
        return changed, unchanged
    
    def get_parallel_analyzer(self) -> ParallelAnalyzer:
        """Create parallel analyzer with configured workers."""
        return ParallelAnalyzer(max_workers=self.parallel_workers, verbose=True)


# Global registry of CLI commands with performance features
_PERFORMANCE_ENABLED_COMMANDS = set()


def register_performance_command(command_name: str) -> None:
    """Register a command as having performance features."""
    _PERFORMANCE_ENABLED_COMMANDS.add(command_name)


def get_performance_enabled_commands() -> set:
    """Get set of commands with performance features."""
    return _PERFORMANCE_ENABLED_COMMANDS.copy()


# Helper functions for common CLI patterns

def format_file_analysis_result(
    file_path: Path,
    success: bool,
    cache_hit: bool = False,
    error: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> str:
    """Format a file analysis result for display."""
    rel_path = file_path.relative_to(base_path) if base_path else file_path
    
    if success:
        status = "✅"
        if cache_hit:
            status = "⚡"  # Lightning bolt for cache hit
        return f"{status} {rel_path}"
    else:
        return f"❌ {rel_path}: {error}"


def display_cache_statistics(stats: Optional[dict]) -> None:
    """Display cache statistics in the terminal."""
    if not stats:
        return
    
    click.echo(click.style("\n💾 Cache Statistics:", fg="cyan", bold=True))
    click.echo(f"  Total entries: {stats['total_entries']}")
    
    if stats.get('by_type'):
        for analysis_type, count in stats['by_type'].items():
            click.echo(f"    - {analysis_type}: {count}")
    
    if stats.get('avg_execution_time_ms'):
        click.echo(f"  Avg execution time: {stats['avg_execution_time_ms']:.1f}ms")


def validate_parallel_workers(value: int) -> int:
    """Validate and normalize parallel worker count."""
    if value == 0:
        import os
        return os.cpu_count() or 4  # Auto-detect or default to 4
    
    return max(1, min(value, 64))  # Between 1 and 64
