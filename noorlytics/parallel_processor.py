"""Parallel Processing Module for Noorlytics

Enables concurrent analysis of multiple files:
- Thread pool-based parallel scanning
- Batch LLM requests for efficiency
- Progress tracking with rich formatting
- Graceful error handling and recovery
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Any, List, Optional, Dict, Iterable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of analyzing a single file."""
    file_path: Path
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    cache_hit: bool = False


class ParallelAnalyzer:
    """Runs file analysis in parallel using thread pool."""
    
    def __init__(self, max_workers: int = 4, verbose: bool = False):
        """
        Initialize parallel analyzer.
        
        Args:
            max_workers: Number of worker threads (default: 4)
                        Use CPU count for CPU-bound, use higher for I/O-bound
            verbose: Enable detailed logging
        """
        self.max_workers = max_workers
        self.verbose = verbose
        self.logger = logger.getChild("ParallelAnalyzer")
    
    def analyze_files(
        self,
        files: Iterable[Path],
        analyze_func: Callable[[Path], Any],
        show_progress: bool = True
    ) -> List[AnalysisResult]:
        """
        Analyze multiple files in parallel.
        
        Args:
            files: Iterable of file paths
            analyze_func: Function to call for each file (takes Path, returns Any)
            show_progress: Show progress bar
        
        Returns:
            List of AnalysisResult objects
        """
        files_list = list(files)
        results: List[AnalysisResult] = []
        
        if self.verbose:
            self.logger.info(f"Starting parallel analysis of {len(files_list)} files with {self.max_workers} workers")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self._analyze_single, f, analyze_func): f
                for f in files_list
            }
            
            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Analysis failed for {file_path}: {e}")
                    results.append(AnalysisResult(
                        file_path=file_path,
                        success=False,
                        error=str(e)
                    ))
                
                completed += 1
                if show_progress:
                    print(f"  [{completed}/{len(files_list)}] Analyzed {file_path.name}")
        
        return results
    
    @staticmethod
    def _analyze_single(file_path: Path, analyze_func: Callable[[Path], Any]) -> AnalysisResult:
        """Analyze a single file with timing."""
        start = time.time()
        try:
            result = analyze_func(file_path)
            duration_ms = (time.time() - start) * 1000
            return AnalysisResult(
                file_path=file_path,
                success=True,
                result=result,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return AnalysisResult(
                file_path=file_path,
                success=False,
                error=str(e),
                duration_ms=duration_ms
            )


class BatchLLMProcessor:
    """Batch multiple analysis requests to LLM for efficiency."""
    
    def __init__(self, batch_size: int = 10, verbose: bool = False):
        """
        Initialize batch processor.
        
        Args:
            batch_size: Number of items to batch together (default: 10)
            verbose: Enable detailed logging
        """
        self.batch_size = batch_size
        self.verbose = verbose
        self.logger = logger.getChild("BatchLLMProcessor")
    
    def batch_analyze(
        self,
        items: List[Any],
        batch_func: Callable[[List[Any]], List[Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Any]:
        """
        Process items in batches.
        
        Args:
            items: List of items to process
            batch_func: Function that takes list of items, returns list of results
            progress_callback: Optional callback(processed_count, total_count)
        
        Returns:
            List of results in same order as input items
        """
        results = []
        total = len(items)
        
        for i in range(0, total, self.batch_size):
            batch = items[i:i+self.batch_size]
            
            if self.verbose:
                self.logger.info(f"Processing batch {i//self.batch_size + 1} ({len(batch)} items)")
            
            try:
                batch_results = batch_func(batch)
                results.extend(batch_results)
            except Exception as e:
                self.logger.error(f"Batch processing failed: {e}")
                # On error, add None placeholders to maintain order
                results.extend([None] * len(batch))
            
            if progress_callback:
                progress_callback(min(i + self.batch_size, total), total)
        
        return results
    
    def estimate_batch_count(self, total_items: int) -> int:
        """Estimate number of batches needed."""
        return (total_items + self.batch_size - 1) // self.batch_size


class IncrementalAnalysisTracker:
    """Tracks file changes for incremental analysis."""
    
    def __init__(self, state_file: Path = Path(".noor/incremental_state.json")):
        """
        Initialize tracker.
        
        Args:
            state_file: Path to store incremental analysis state
        """
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Dict[str, Any]] = self._load_state()
    
    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        """Load previous analysis state."""
        import json
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load incremental state: {e}")
        return {}
    
    def _save_state(self) -> None:
        """Save analysis state."""
        import json
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save incremental state: {e}")
    
    def get_files_to_analyze(
        self,
        files: Iterable[Path],
        analysis_type: str
    ) -> Tuple[List[Path], List[Path]]:
        """
        Determine which files need analysis.
        
        Args:
            files: Candidate files
            analysis_type: Type of analysis (e.g., "audit-security")
        
        Returns:
            (changed_files, unchanged_files)
        """
        import hashlib
        
        changed = []
        unchanged = []
        
        for file_path in files:
            path_str = str(file_path.resolve())
            
            # Compute current file hash
            try:
                with open(file_path, 'rb') as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                changed.append(file_path)
                continue
            
            # Check if file has changed
            if path_str not in self.state:
                self.state[path_str] = {}
            
            previous_hash = self.state[path_str].get(f"{analysis_type}_hash")
            
            if previous_hash == current_hash:
                unchanged.append(file_path)
            else:
                changed.append(file_path)
                self.state[path_str][f"{analysis_type}_hash"] = current_hash
        
        self._save_state()
        return changed, unchanged
    
    def clear(self) -> None:
        """Clear all tracked state."""
        self.state.clear()
        self._save_state()


class ProgressTracker:
    """Simple progress tracker with console output."""
    
    def __init__(self, total: int, label: str = "Progress"):
        self.total = total
        self.label = label
        self.current = 0
        self.start_time = time.time()
    
    def update(self, amount: int = 1) -> None:
        """Update progress."""
        self.current += amount
        self._print_progress()
    
    def _print_progress(self) -> None:
        """Print progress bar."""
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.current) / rate if rate > 0 else 0
        
        percent = (self.current / self.total * 100) if self.total > 0 else 0
        bar_length = 30
        filled = int(bar_length * self.current / self.total) if self.total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(
            f"\r{self.label}: [{bar}] {percent:.1f}% ({self.current}/{self.total}) "
            f"ETA: {remaining:.0f}s",
            end="",
            flush=True
        )
    
    def finish(self) -> None:
        """Mark as complete."""
        self.current = self.total
        self._print_progress()
        print()  # Newline
