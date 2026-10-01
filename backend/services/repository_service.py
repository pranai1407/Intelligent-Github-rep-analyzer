
import logging
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from backend.report.pdf_generator import PDFGenerator
from backend.repository.parser import RepositoryParser
from backend.ai.prompt_builder import PromptBuilder
from backend.ai.gemini_client import GeminiClient


logger = logging.getLogger(__name__)


class RepositoryService:
    CACHE_LIMIT = 5
    CLEANUP_ATTEMPTS = 3
    CLEANUP_RETRY_DELAY = 0.5

    def __init__(self):
        self.parser = RepositoryParser()
        self.prompt_builder = PromptBuilder()
        self.gemini = GeminiClient()
        self.pdf_generator = PDFGenerator()
        self.analysis_cache = {}

    @staticmethod
    def _report_progress(progress_callback, stage, message, percent):
        """Safely report a progress update when a callback is supplied."""
        if progress_callback is None:
            return

        try:
            progress_callback(
                stage=stage,
                message=message,
                percent=max(0, min(100, int(percent))),
            )
        except Exception:
            # Progress reporting must not interrupt repository analysis.
            pass

    def _cache_key(self, repo_url: str) -> str:
        """Create a consistent cache key for a GitHub repository URL."""
        parsed = urlparse(repo_url.strip())
        path = parsed.path.rstrip("/")

        if path.lower().endswith(".git"):
            path = path[:-4]

        return f"https://github.com{path}".lower()

    def validate_repository_url(self, repo_url: str):
        """Validate that the URL points to a GitHub repository."""
        if not isinstance(repo_url, str):
            return False

        try:
            parsed_url = urlparse(repo_url.strip())

            if parsed_url.scheme not in ("http", "https"):
                return False

            if parsed_url.netloc.lower() not in (
                "github.com",
                "www.github.com",
            ):
                return False

            path_parts = [
                part
                for part in parsed_url.path.strip("/").split("/")
                if part
            ]

            return (
                len(path_parts) == 2
                and all(part not in (".", "..") for part in path_parts)
            )

        except (TypeError, ValueError):
            return False

    @staticmethod
    def _default_summary(message="AI summary unavailable."):
        return {
            "repository_purpose": message,
            "technologies_used": [],
            "project_organization": "Unavailable.",
            "intended_users": "Unavailable.",
            "beginner_summary": "AI service could not provide a summary.",
        }

    @staticmethod
    def _default_recommendations(message="Unavailable"):
        return {
            "strengths": [],
            "areas_for_improvement": [],
            "best_practices": [],
            "overall_quality": message,
        }

    @staticmethod
    def _as_text(value, fallback):
        """Convert a value into displayable text."""
        if isinstance(value, str) and value.strip():
            return value.strip()

        if value is None:
            return fallback

        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value, ensure_ascii=False, indent=2)

        return str(value)

    @staticmethod
    def _as_string_list(value):
        """Normalize a value into a list of strings."""
        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if item is not None and str(item).strip()
            ]

        if isinstance(value, str) and value.strip():
            return [value.strip()]

        return []

    def _normalize_summary(self, response):
        """Ensure the AI summary always has the expected keys."""
        if not isinstance(response, dict):
            message = (
                response.strip()
                if isinstance(response, str) and response.strip()
                else "AI returned an unexpected response."
            )
            return self._default_summary(message)

        return {
            "repository_purpose": self._as_text(
                response.get("repository_purpose"),
                "Purpose not available.",
            ),
            "technologies_used": self._as_string_list(
                response.get("technologies_used")
            ),
            "project_organization": self._as_text(
                response.get("project_organization"),
                "Project organization not available.",
            ),
            "intended_users": self._as_text(
                response.get("intended_users"),
                "Intended users not available.",
            ),
            "beginner_summary": self._as_text(
                response.get("beginner_summary"),
                "Beginner summary not available.",
            ),
        }

    def _normalize_recommendations(self, response):
        """Ensure AI recommendations always have the expected keys."""
        if not isinstance(response, dict):
            return self._default_recommendations(
                "AI recommendations unavailable."
            )

        return {
            "strengths": self._as_string_list(
                response.get("strengths")
            ),
            "areas_for_improvement": self._as_string_list(
                response.get("areas_for_improvement")
            ),
            "best_practices": self._as_string_list(
                response.get("best_practices")
            ),
            "overall_quality": self._as_text(
                response.get("overall_quality"),
                "Assessment unavailable.",
            ),
        }

    def _build_analysis(self, clone_path, progress_callback=None):
        """Build analysis using the parser's consolidated snapshot."""
        return self.parser.get_repository_snapshot(
            clone_path,
            progress_callback=progress_callback,
        )

    def _generate_ai_summary(self, analysis, progress_callback=None):
        """Generate and normalize the AI summary."""
        self._report_progress(
            progress_callback,
            "ai_summary",
            "Generating the AI repository summary...",
            87,
        )

        try:
            prompt = self.prompt_builder.build_summary_prompt(analysis)
            response = self.gemini.generate_response(prompt)
            return self._normalize_summary(response)

        except Exception as exc:
            logger.warning("AI summary generation failed: %s", exc)
            return self._default_summary(
                f"AI Summary unavailable: {exc}"
            )

    def _generate_ai_recommendations(
        self,
        analysis,
        progress_callback=None,
    ):
        """Generate and normalize AI recommendations."""
        self._report_progress(
            progress_callback,
            "ai_recommendations",
            "Generating AI recommendations and improvement suggestions...",
            93,
        )

        try:
            prompt = self.prompt_builder.build_recommendation_prompt(
                analysis
            )
            response = self.gemini.generate_response(prompt)
            return self._normalize_recommendations(response)

        except Exception as exc:
            logger.warning(
                "AI recommendation generation failed: %s",
                exc,
            )
            return self._default_recommendations()

    def _cleanup_clone(self, clone_path):
        """
        Safely remove a temporary clone inside repositories/.

        Retries transient filesystem failures and logs persistent failures.
        Cleanup errors do not replace the original analysis result/error.
        """
        if not clone_path:
            return True

        try:
            repositories_root = Path(
                self.parser.repositories_dir
            ).resolve()

            candidate = Path(clone_path).resolve()

            # Never remove the repositories root itself.
            if candidate == repositories_root:
                logger.error(
                    "Clone cleanup refused: candidate is the repositories root."
                )
                return False

            # Only remove a child directory of repositories/.
            if repositories_root not in candidate.parents:
                logger.error(
                    "Clone cleanup refused: path is outside repositories/: %s",
                    candidate,
                )
                return False

        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Could not validate clone cleanup path %r: %s",
                clone_path,
                exc,
            )
            return False

        for attempt in range(1, self.CLEANUP_ATTEMPTS + 1):
            try:
                if not candidate.exists():
                    logger.info(
                        "Temporary clone already removed: %s",
                        candidate,
                    )
                    return True

                # Do not suppress errors; retries and logging need them.
                shutil.rmtree(candidate)

                logger.info(
                    "Temporary clone successfully removed: %s",
                    candidate,
                )
                return True

            except FileNotFoundError:
                # Another cleanup attempt/process may have removed it.
                return True

            except OSError as exc:
                if attempt < self.CLEANUP_ATTEMPTS:
                    logger.warning(
                        "Clone cleanup attempt %d/%d failed for %s: %s. "
                        "Retrying...",
                        attempt,
                        self.CLEANUP_ATTEMPTS,
                        candidate,
                        exc,
                    )
                    time.sleep(self.CLEANUP_RETRY_DELAY)
                else:
                    logger.error(
                        "Clone cleanup failed after %d attempts for %s: %s",
                        self.CLEANUP_ATTEMPTS,
                        candidate,
                        exc,
                    )
                    return False

        return False

    def _remember_analysis(self, cache_key, repository_info):
        """Store analysis and evict the oldest entry when the cache is full."""
        self.analysis_cache[cache_key] = repository_info

        while len(self.analysis_cache) > self.CACHE_LIMIT:
            oldest_key = next(iter(self.analysis_cache))
            del self.analysis_cache[oldest_key]

    def _analyze_and_cache(
        self,
        repo_url: str,
        progress_callback=None,
    ):
        """Clone, analyze, cache results, and always clean up the clone."""
        cache_key = self._cache_key(repo_url)
        clone_path = None

        try:
            self._report_progress(
                progress_callback,
                "starting",
                "Preparing repository analysis...",
                2,
            )

            clone_path = self.parser.clone_repository(
                repo_url,
                progress_callback=progress_callback,
            )

            if clone_path is None:
                return None

            repository_info = self._build_analysis(
                clone_path,
                progress_callback=progress_callback,
            )
            analysis = repository_info["analysis"]

            repository_info["ai_summary"] = (
                self._generate_ai_summary(
                    analysis,
                    progress_callback=progress_callback,
                )
            )
            repository_info["ai_recommendations"] = (
                self._generate_ai_recommendations(
                    analysis,
                    progress_callback=progress_callback,
                )
            )

            self._report_progress(
                progress_callback,
                "caching",
                "Saving the analysis result for PDF and chatbot reuse...",
                98,
            )
            self._remember_analysis(cache_key, repository_info)

            self._report_progress(
                progress_callback,
                "complete",
                "Repository analysis completed successfully.",
                100,
            )
            return repository_info

        finally:
            # Runs after success or failure, including AI-related failures.
            self._cleanup_clone(clone_path)

    def analyze_repository(
        self,
        repo_url: str,
        progress_callback=None,
    ):
        """Analyze a repository and save its result in the cache."""
        if not self.validate_repository_url(repo_url):
            return {
                "status": "error",
                "message": "Please enter a valid GitHub repository URL.",
            }

        try:
            repository_info = self._analyze_and_cache(
                repo_url.strip(),
                progress_callback=progress_callback,
            )

            if repository_info is None:
                return {
                    "status": "error",
                    "message": (
                        "Unable to clone the repository. "
                        "Please check that it exists and is public."
                    ),
                }

            return repository_info

        except Exception as exc:
            logger.exception("Repository analysis failed")
            return {
                "status": "error",
                "message": f"Repository analysis failed: {exc}",
            }

    def ask_question(self, repo_url: str, question: str):
        """Answer questions using cached repository analysis when possible."""
        if not self.validate_repository_url(repo_url):
            return {
                "status": "error",
                "message": "Invalid GitHub repository URL.",
            }

        if not isinstance(question, str) or not question.strip():
            return {
                "status": "error",
                "message": "Please enter a question.",
            }

        try:
            cache_key = self._cache_key(repo_url)
            repository_info = self.analysis_cache.get(cache_key)

            if repository_info is None:
                repository_info = self._analyze_and_cache(repo_url)

            if repository_info is None:
                return {
                    "status": "error",
                    "message": "Unable to clone or analyze the repository.",
                }

            analysis = repository_info["analysis"]
            clean_question = question.strip()

            prompt = self.prompt_builder.build_qa_prompt(
                analysis,
                clean_question,
            )
            answer = self.gemini.generate_response(prompt)

            if isinstance(answer, dict):
                answer = answer.get("answer", str(answer))

            if not isinstance(answer, str):
                answer = str(answer)

            return {
                "repository": analysis.get(
                    "repository_name",
                    "Unknown repository",
                ),
                "question": clean_question,
                "answer": answer,
            }

        except Exception as exc:
            logger.exception("Unable to answer repository question")
            return {
                "status": "error",
                "message": f"Unable to answer the question: {exc}",
            }

    def generate_pdf_report(self, repo_url: str):
        """Generate a PDF report, reusing cached analysis if available."""
        if not self.validate_repository_url(repo_url):
            raise ValueError("Invalid GitHub repository URL.")

        cache_key = self._cache_key(repo_url)
        repository_info = self.analysis_cache.get(cache_key)

        if repository_info is None:
            repository_info = self._analyze_and_cache(repo_url)

        if repository_info is None:
            raise RuntimeError(
                "Unable to clone or analyze the repository for the report."
            )

        filename = "Repository_Analysis_Report.pdf"

        self.pdf_generator.generate_report(
            repository_info,
            filename,
        )

        return filename