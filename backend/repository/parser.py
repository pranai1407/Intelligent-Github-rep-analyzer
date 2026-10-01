
import json
import os
import shutil
import tempfile
from pathlib import Path

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


class RepositoryParser:
    HISTORY_COMMIT_LIMIT = 5000
    HOTSPOT_LIMIT = 10

    LANGUAGE_MAP = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "JavaScript", ".tsx": "TypeScript", ".java": "Java",
        ".cpp": "C++", ".cc": "C++", ".c": "C", ".h": "C/C++",
        ".hpp": "C++", ".cs": "C#", ".html": "HTML", ".css": "CSS",
        ".php": "PHP", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
        ".swift": "Swift", ".kt": "Kotlin", ".sql": "SQL",
        ".sh": "Shell", ".dart": "Dart", ".vue": "Vue", ".r": "R",
    }

    CONFIG_NAMES = {
        "requirements.txt", "pyproject.toml", "package.json",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "dockerfile", "docker-compose.yml", "compose.yml",
        ".gitignore", "pom.xml", "build.gradle", "cargo.toml",
        "go.mod", "makefile", "tox.ini", "pytest.ini",
        "tsconfig.json", "webpack.config.js",
    }

    DOC_EXTENSIONS = {".md", ".rst", ".txt"}

    def __init__(self):
        self.repositories_dir = Path("repositories").resolve()
        self.repositories_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _report_progress(progress_callback, stage, message, percent):
        """Send progress updates when a callback was provided."""
        if progress_callback is None:
            return

        try:
            progress_callback(
                stage=stage,
                message=message,
                percent=max(0, min(100, int(percent))),
            )
        except Exception:
            # Progress reporting must never break repository analysis.
            pass

    def clone_repository(self, repo_url, progress_callback=None):
        """Clone a repository into a unique directory with full history."""
        if not isinstance(repo_url, str) or not repo_url.strip():
            raise ValueError("A valid repository URL is required.")

        repo_name = repo_url.strip().rstrip("/").split("/")[-1]
        if repo_name.lower().endswith(".git"):
            repo_name = repo_name[:-4]

        safe_name = "".join(
            char if char.isalnum() or char in ("-", "_") else "_"
            for char in repo_name
        )[:50] or "repository"

        clone_path = Path(tempfile.mkdtemp(
            prefix=f"{safe_name}_",
            dir=str(self.repositories_dir),
        ))

        last_clone_percent = -1

        def clone_progress(operation, current, maximum, message):
            nonlocal last_clone_percent

            # Git may not provide a maximum, so use a stage-level update.
            if maximum and maximum > 0:
                percent = min(25, int((current / maximum) * 25))
            else:
                percent = 10

            if percent != last_clone_percent:
                last_clone_percent = percent
                detail = (message or "Receiving repository data").strip()
                self._report_progress(
                    progress_callback,
                    "cloning",
                    f"Cloning repository: {detail}",
                    percent,
                )

        try:
            self._report_progress(
                progress_callback,
                "cloning",
                "Connecting to Git and cloning the repository...",
                5,
            )
            Repo.clone_from(
                repo_url.strip(),
                str(clone_path),
                progress=clone_progress,
            )
            self._report_progress(
                progress_callback,
                "cloning",
                "Repository cloned successfully.",
                25,
            )
            return str(clone_path)
        except Exception:
            shutil.rmtree(clone_path, ignore_errors=True)
            raise

    @staticmethod
    def _get_repo(clone_path):
        try:
            return Repo(clone_path)
        except (InvalidGitRepositoryError, OSError) as exc:
            raise ValueError(
                f"Could not open Git repository at {clone_path}: {exc}"
            ) from exc

    @staticmethod
    def _walk_files(clone_path):
        """Yield files while excluding Git internals."""
        for root, dirs, files in os.walk(clone_path):
            dirs[:] = [d for d in dirs if d != ".git"]
            for filename in files:
                yield Path(root) / filename

    @staticmethod
    def _read_text(path, limit=None):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as file:
                return file.read() if limit is None else file.read(limit)
        except OSError:
            return ""

    def _scan_files(self, clone_path, progress_callback=None):
        """Collect file-derived metrics in a single directory traversal."""
        root = Path(clone_path)
        languages = {}
        documentation = []
        configurations = []
        total_files = 0
        total_directories = 0

        self._report_progress(
            progress_callback,
            "scanning",
            "Scanning repository files and identifying languages...",
            30,
        )

        for current_root, dirs, files in os.walk(root):
            dirs[:] = [directory for directory in dirs if directory != ".git"]
            total_directories += len(dirs)

            for filename in files:
                path = Path(current_root) / filename
                total_files += 1
                suffix = path.suffix.lower()
                language = self.LANGUAGE_MAP.get(suffix)

                if language:
                    languages[language] = languages.get(language, 0) + 1

                relative_path = str(path.relative_to(root))

                if suffix in self.DOC_EXTENSIONS:
                    documentation.append({
                        "name": path.name,
                        "path": relative_path,
                    })

                if path.name.lower() in self.CONFIG_NAMES:
                    configurations.append({
                        "name": path.name,
                        "path": relative_path,
                    })

        documentation.sort(key=lambda item: item["path"].lower())
        configurations.sort(key=lambda item: item["path"].lower())

        self._report_progress(
            progress_callback,
            "scanning",
            f"File scan complete: {total_files} files and "
            f"{total_directories} directories found.",
            50,
        )

        return {
            "languages": languages,
            "documentation": documentation,
            "configurations": configurations,
            "statistics": {
                "total_files": total_files,
                "total_directories": total_directories,
            },
        }

    def _get_history_metrics(self, clone_path, progress_callback=None):
        """
        Use efficient Git plumbing commands.

        Contributor and hotspot analysis is limited to the most recent
        HISTORY_COMMIT_LIMIT commits to avoid unbounded history processing.
        The total commit count remains exact when Git can read the history.
        """
        repo = self._get_repo(clone_path)
        total_commits = 0
        contributors = set()
        file_counts = {}
        history_limited = False

        self._report_progress(
            progress_callback,
            "history",
            "Analyzing Git commits, contributors, and changed files...",
            55,
        )

        try:
            total_commits = int(repo.git.rev_list("--count", "HEAD"))
        except (GitCommandError, ValueError):
            total_commits = 0

        try:
            history_limited = total_commits > self.HISTORY_COMMIT_LIMIT
            output = repo.git.log(
                f"-n{self.HISTORY_COMMIT_LIMIT}",
                "--format=%an%x1f%ae",
                "--name-only",
                "--no-renames",
            )

            current_author = None
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue

                if "\x1f" in line:
                    name, email = line.split("\x1f", 1)
                    current_author = (email or name).strip().lower()
                    if current_author:
                        contributors.add(current_author)
                    continue

                normalized = line.replace("\\", "/")
                if normalized.startswith(".git/"):
                    continue

                file_counts[normalized] = file_counts.get(normalized, 0) + 1

        except GitCommandError:
            pass

        hotspots = sorted(
            file_counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )[:self.HOTSPOT_LIMIT]

        self._report_progress(
            progress_callback,
            "history",
            f"Git history analyzed: {total_commits} commits found.",
            70,
        )

        return {
            "total_commits": total_commits,
            "total_contributors": len(contributors),
            "hotspot_files": hotspots,
            "history_analysis_limited": history_limited,
        }

    def _get_repository_info(self, clone_path):
        repo = self._get_repo(clone_path)

        try:
            default_branch = repo.active_branch.name
        except (TypeError, GitCommandError):
            default_branch = "Detached HEAD"

        readme_found = any(
            (Path(clone_path) / name).is_file()
            for name in ("README.md", "readme.md", "README.txt", "Readme.md")
        )

        return {
            "repository_name": Path(clone_path).name.split("_")[0],
            "default_branch": default_branch,
            "total_branches": len(repo.branches),
            "readme_found": readme_found,
        }

    def _get_readme_content(self, clone_path):
        root = Path(clone_path)
        for name in ("README.md", "readme.md", "README.txt", "Readme.md"):
            path = root / name
            if path.is_file():
                content = self._read_text(path, limit=200_000)
                if content:
                    return content
        return "README file not found."

    def _get_dependencies(self, clone_path):
        root = Path(clone_path)
        dependencies = []
        requirements = root / "requirements.txt"

        if requirements.is_file():
            for line in self._read_text(
                requirements, limit=500_000
            ).splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    dependencies.append(line)

        package_json = root / "package.json"
        if package_json.is_file():
            try:
                data = json.loads(
                    self._read_text(package_json, limit=500_000)
                )
                if isinstance(data, dict):
                    for section in ("dependencies", "devDependencies"):
                        section_data = data.get(section, {})
                        if isinstance(section_data, dict):
                            dependencies.extend(
                                f"{name}: {version}"
                                for name, version in section_data.items()
                            )
            except (json.JSONDecodeError, OSError):
                pass

        return sorted(set(dependencies), key=str.lower)

    def _get_structure(self, clone_path):
        root = Path(clone_path)
        folders, files = [], []

        try:
            for item in root.iterdir():
                if item.name == ".git":
                    continue
                if item.is_dir():
                    folders.append(item.name)
                elif item.is_file():
                    files.append(item.name)
        except OSError:
            pass

        return {
            "folders": sorted(folders, key=str.lower),
            "files": sorted(files, key=str.lower),
        }

    def get_repository_snapshot(
        self,
        clone_path,
        progress_callback=None,
    ):
        """Build all repository metrics with one file scan."""
        self._report_progress(
            progress_callback,
            "metadata",
            "Reading repository metadata...",
            27,
        )
        info = self._get_repository_info(clone_path)

        file_metrics = self._scan_files(
            clone_path,
            progress_callback=progress_callback,
        )
        history_metrics = self._get_history_metrics(
            clone_path,
            progress_callback=progress_callback,
        )

        self._report_progress(
            progress_callback,
            "finalizing",
            "Collecting dependencies, README, and project structure...",
            80,
        )

        info.update(history_metrics)
        info.update(file_metrics)
        info["structure"] = self._get_structure(clone_path)
        info["dependencies"] = self._get_dependencies(clone_path)
        info["readme"] = self._get_readme_content(clone_path)
        info["analysis"] = {
            "repository_name": info["repository_name"],
            "default_branch": info["default_branch"],
            "total_branches": info["total_branches"],
            "total_commits": info["total_commits"],
            "total_contributors": info["total_contributors"],
            "languages": info["languages"],
            "dependencies": info["dependencies"],
            "documentation": info["documentation"],
            "configuration_files": info["configurations"],
            "structure": info["structure"],
            "statistics": info["statistics"],
            "readme": info["readme"],
            "hotspot_files": info["hotspot_files"],
            "history_analysis_limited": info["history_analysis_limited"],
        }

        self._report_progress(
            progress_callback,
            "complete",
            "Repository snapshot is ready.",
            85,
        )
        return info

    # Compatibility methods for existing callers.
    def get_repository_info(self, clone_path):
        return self._get_repository_info(clone_path)

    def get_commit_count(self, clone_path):
        return self._get_history_metrics(clone_path)["total_commits"]

    def get_contributors_count(self, clone_path):
        return self._get_history_metrics(clone_path)["total_contributors"]

    def get_hotspot_files(self, clone_path):
        return self._get_history_metrics(clone_path)["hotspot_files"]

    def get_readme_content(self, clone_path):
        return self._get_readme_content(clone_path)

    def get_languages(self, clone_path):
        return self._scan_files(clone_path)["languages"]

    def get_documentation_files(self, clone_path):
        return self._scan_files(clone_path)["documentation"]

    def get_configuration_files(self, clone_path):
        return self._scan_files(clone_path)["configurations"]

    def get_repository_structure(self, clone_path):
        return self._get_structure(clone_path)

    def get_dependencies(self, clone_path):
        return self._get_dependencies(clone_path)

    def get_file_statistics(self, clone_path):
        return self._scan_files(clone_path)["statistics"]