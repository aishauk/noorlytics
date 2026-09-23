# noorlytics/git_integration.py
"""Optional git integration for refactoring changes.

Provides:
- Check if directory is a git repository
- Stage files
- Create commits
"""

from pathlib import Path
import subprocess
from typing import Optional


class GitIntegration:
    """Stage and commit refactoring changes to git."""
    
    @staticmethod
    def is_git_repo(path: Path) -> bool:
        """Check if path is inside a git repository.
        
        Args:
            path: Path to check (file or directory)
            
        Returns:
            True if inside a git repo, False otherwise
        """
        try:
            work_dir = path.parent if path.is_file() else path
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=work_dir,
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def stage_file(file_path: Path, work_dir: Optional[Path] = None) -> bool:
        """Stage file changes in git.
        
        Args:
            file_path: Path to file to stage
            work_dir: Working directory (default: parent of file)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            work_dir = work_dir or file_path.parent
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=work_dir,
                capture_output=True,
                check=True,
                timeout=10
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def commit(message: str, work_dir: Optional[Path] = None) -> bool:
        """Create a commit with refactoring changes.
        
        Args:
            message: Commit message
            work_dir: Working directory (default: current directory)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = ["git", "commit", "-m", message]
            subprocess.run(
                cmd,
                cwd=work_dir or Path.cwd(),
                capture_output=True,
                check=True,
                timeout=10
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def get_current_branch(work_dir: Optional[Path] = None) -> Optional[str]:
        """Get current git branch name.
        
        Args:
            work_dir: Working directory (default: current directory)
            
        Returns:
            Branch name, or None if not in a git repo
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=work_dir or Path.cwd(),
                capture_output=True,
                check=True,
                timeout=5,
                text=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None
    
    @staticmethod
    def get_status(work_dir: Optional[Path] = None) -> Optional[str]:
        """Get git status output.
        
        Args:
            work_dir: Working directory (default: current directory)
            
        Returns:
            Status output, or None if not in a git repo
        """
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=work_dir or Path.cwd(),
                capture_output=True,
                check=True,
                timeout=5,
                text=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None
