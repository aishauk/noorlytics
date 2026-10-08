"""Performance Benchmarking Tool for Noorlytics

Measures and tracks performance of analysis operations:
- File scanning speed (files/sec, MB/sec)
- LLM inference time
- Cache effectiveness
- Parallel processing efficiency
- Memory usage tracking
"""

from __future__ import annotations

import time
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
import subprocess
import psutil
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Metrics for a single analysis operation."""
    operation_name: str
    start_time: float
    end_time: float
    duration_ms: float
    file_count: int = 0
    total_lines: int = 0
    total_bytes: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    memory_peak_mb: float = 0.0
    memory_start_mb: float = 0.0
    memory_end_mb: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    
    @property
    def duration_sec(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000.0
    
    @property
    def throughput_files_per_sec(self) -> float:
        """How many files analyzed per second."""
        return self.file_count / self.duration_sec if self.duration_sec > 0 else 0
    
    @property
    def throughput_mb_per_sec(self) -> float:
        """How many MB analyzed per second."""
        mb = self.total_bytes / (1024 * 1024)
        return mb / self.duration_sec if self.duration_sec > 0 else 0
    
    @property
    def cache_hit_rate(self) -> float:
        """Percentage of cache hits."""
        total = self.cache_hit_count + self.cache_miss_count
        return (self.cache_hit_count / total * 100) if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d.update({
            "duration_sec": self.duration_sec,
            "throughput_files_per_sec": self.throughput_files_per_sec,
            "throughput_mb_per_sec": self.throughput_mb_per_sec,
            "cache_hit_rate": self.cache_hit_rate,
        })
        return d
    
    def __str__(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Operation: {self.operation_name}",
            f"Duration: {self.duration_sec:.2f}s ({self.duration_ms:.0f}ms)",
            f"Files: {self.file_count}, {self.total_lines:,} lines, {self.total_bytes / (1024*1024):.1f} MB",
            f"Throughput: {self.throughput_files_per_sec:.1f} files/sec, {self.throughput_mb_per_sec:.2f} MB/sec",
        ]
        
        if self.cache_hit_count + self.cache_miss_count > 0:
            lines.append(f"Cache: {self.cache_hit_count} hits, {self.cache_miss_count} misses ({self.cache_hit_rate:.1f}%)")
        
        if self.memory_peak_mb > 0:
            lines.append(
                f"Memory: {self.memory_start_mb:.1f}MB → {self.memory_end_mb:.1f}MB "
                f"(peak: {self.memory_peak_mb:.1f}MB, +{self.memory_peak_mb - self.memory_start_mb:.1f}MB)"
            )
        
        return "\n".join(lines)


class PerformanceMonitor:
    """Tracks performance metrics during analysis operations."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.process = psutil.Process()
        self.memory_start_mb = self.process.memory_info().rss / (1024 * 1024)
        self.memory_peak_mb = self.memory_start_mb
        self.memory_end_mb = self.memory_start_mb
        
        # Metric accumulators
        self.file_count = 0
        self.total_lines = 0
        self.total_bytes = 0
        self.cache_hit_count = 0
        self.cache_miss_count = 0
    
    def update_memory(self) -> None:
        """Update current memory usage."""
        current_mb = self.process.memory_info().rss / (1024 * 1024)
        self.memory_peak_mb = max(self.memory_peak_mb, current_mb)
        self.memory_end_mb = current_mb
    
    def add_file(self, file_path: Path, cache_hit: bool = False) -> None:
        """Record analysis of a file."""
        self.file_count += 1
        
        if file_path.exists():
            self.total_bytes += file_path.stat().st_size
            try:
                self.total_lines += len(file_path.read_text(errors='ignore').splitlines())
            except Exception:
                pass
        
        if cache_hit:
            self.cache_hit_count += 1
        else:
            self.cache_miss_count += 1
    
    def finish(self) -> PerformanceMetrics:
        """Generate final metrics."""
        self.end_time = time.time()
        self.update_memory()
        
        return PerformanceMetrics(
            operation_name=self.operation_name,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=(self.end_time - self.start_time) * 1000,
            file_count=self.file_count,
            total_lines=self.total_lines,
            total_bytes=self.total_bytes,
            cache_hit_count=self.cache_hit_count,
            cache_miss_count=self.cache_miss_count,
            memory_peak_mb=self.memory_peak_mb,
            memory_start_mb=self.memory_start_mb,
            memory_end_mb=self.memory_end_mb,
        )


class PerformanceBenchmark:
    """Store and analyze performance benchmark results."""
    
    def __init__(self, output_dir: Path = Path("reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = output_dir / "performance_benchmarks.json"
        self.results: List[PerformanceMetrics] = self._load_results()
    
    def _load_results(self) -> List[PerformanceMetrics]:
        """Load historical benchmark results."""
        if self.results_file.exists():
            try:
                data = json.loads(self.results_file.read_text())
                return [
                    PerformanceMetrics(
                        operation_name=r["operation_name"],
                        start_time=r["start_time"],
                        end_time=r["end_time"],
                        duration_ms=r["duration_ms"],
                        file_count=r.get("file_count", 0),
                        total_lines=r.get("total_lines", 0),
                        total_bytes=r.get("total_bytes", 0),
                        cache_hit_count=r.get("cache_hit_count", 0),
                        cache_miss_count=r.get("cache_miss_count", 0),
                        memory_peak_mb=r.get("memory_peak_mb", 0),
                        memory_start_mb=r.get("memory_start_mb", 0),
                        memory_end_mb=r.get("memory_end_mb", 0),
                        timestamp=r.get("timestamp", ""),
                    )
                    for r in data
                ]
            except Exception as e:
                logger.warning(f"Failed to load benchmark results: {e}")
        return []
    
    def record(self, metrics: PerformanceMetrics) -> None:
        """Record a benchmark result."""
        self.results.append(metrics)
        self._save_results()
    
    def _save_results(self) -> None:
        """Save results to file."""
        try:
            data = [m.to_dict() for m in self.results]
            self.results_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save benchmark results: {e}")
    
    def get_average_performance(self, operation_name: str, last_n: int = 10) -> Optional[Dict[str, Any]]:
        """Get average performance metrics for an operation."""
        matching = [m for m in self.results if m.operation_name == operation_name]
        
        if not matching:
            return None
        
        # Use last N results
        recent = matching[-last_n:] if last_n else matching
        
        if not recent:
            return None
        
        avg_duration_ms = sum(m.duration_ms for m in recent) / len(recent)
        avg_throughput_mb = sum(m.throughput_mb_per_sec for m in recent) / len(recent)
        avg_cache_hit = sum(m.cache_hit_rate for m in recent) / len(recent)
        
        return {
            "operation": operation_name,
            "samples": len(recent),
            "avg_duration_ms": avg_duration_ms,
            "avg_throughput_mb_per_sec": avg_throughput_mb,
            "avg_cache_hit_rate": avg_cache_hit,
        }
    
    def compare_runs(self, op_name: str, run1_idx: int, run2_idx: int) -> Dict[str, Any]:
        """Compare two benchmark runs."""
        matching = [m for m in self.results if m.operation_name == op_name]
        
        if run1_idx >= len(matching) or run2_idx >= len(matching):
            return {"error": "Invalid run indices"}
        
        r1 = matching[run1_idx]
        r2 = matching[run2_idx]
        
        speedup = r1.duration_ms / r2.duration_ms if r2.duration_ms > 0 else 0
        
        return {
            "operation": op_name,
            "run1": {
                "timestamp": r1.timestamp,
                "duration_ms": r1.duration_ms,
                "throughput_mb_per_sec": r1.throughput_mb_per_sec,
            },
            "run2": {
                "timestamp": r2.timestamp,
                "duration_ms": r2.duration_ms,
                "throughput_mb_per_sec": r2.throughput_mb_per_sec,
            },
            "speedup": speedup,
            "faster_run": 1 if r1.duration_ms < r2.duration_ms else 2,
        }
    
    def generate_report(self) -> str:
        """Generate a human-readable performance report."""
        lines = [
            "# Performance Benchmarks",
            "",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "",
            "## Summary",
            "",
        ]
        
        # Group by operation
        by_operation: Dict[str, List[PerformanceMetrics]] = {}
        for m in self.results:
            if m.operation_name not in by_operation:
                by_operation[m.operation_name] = []
            by_operation[m.operation_name].append(m)
        
        for op_name in sorted(by_operation.keys()):
            metrics_list = by_operation[op_name]
            lines.append(f"### {op_name} ({len(metrics_list)} runs)")
            lines.append("")
            
            if metrics_list:
                latest = metrics_list[-1]
                lines.append(f"**Latest run:**")
                lines.append(f"- Duration: {latest.duration_sec:.2f}s")
                lines.append(f"- Files: {latest.file_count}, {latest.total_lines:,} lines")
                lines.append(f"- Throughput: {latest.throughput_files_per_sec:.1f} files/sec, {latest.throughput_mb_per_sec:.2f} MB/sec")
                
                if latest.cache_hit_count + latest.cache_miss_count > 0:
                    lines.append(f"- Cache hit rate: {latest.cache_hit_rate:.1f}%")
                
                lines.append("")
                
                # Trends
                avg = self.get_average_performance(op_name)
                if avg:
                    lines.append(f"**Average (last 10 runs):**")
                    lines.append(f"- Duration: {avg['avg_duration_ms']/1000:.2f}s")
                    lines.append(f"- Throughput: {avg['avg_throughput_mb_per_sec']:.2f} MB/sec")
                    lines.append(f"- Cache hit rate: {avg['avg_cache_hit_rate']:.1f}%")
                    lines.append("")
        
        return "\n".join(lines)


def benchmark_operation(
    operation_name: str,
    func: Callable,
    *args,
    **kwargs
) -> tuple[Any, PerformanceMetrics]:
    """
    Benchmark a function and return result + metrics.
    
    Example:
        result, metrics = benchmark_operation("analyze", analyze_file, path)
    """
    monitor = PerformanceMonitor(operation_name)
    result = func(*args, **kwargs)
    metrics = monitor.finish()
    return result, metrics
