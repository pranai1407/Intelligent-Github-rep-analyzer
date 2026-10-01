
import json
import time

import requests
import streamlit as st


BACKEND_URL = "http://127.0.0.1:8000"
PDF_FILENAME = "Repository_Analysis_Report.pdf"
PROGRESS_POLL_INTERVAL = 1.5
MAX_ANALYSIS_WAIT_SECONDS = 1800


# ----------------------------------------
# Page Configuration
# ----------------------------------------

st.set_page_config(
    page_title="GitHub Repository Analyzer",
    page_icon="📊",
    layout="wide",
)


# ----------------------------------------
# Session State
# ----------------------------------------

DEFAULT_SESSION_STATE = {
    "analysis": None,
    "repo_url": "",
    "pdf_bytes": None,
    "last_question": "",
    "last_answer": "",
    "last_job_id": "",
}

for key, value in DEFAULT_SESSION_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ----------------------------------------
# Health Score Helpers
# ----------------------------------------

def safe_count(value):
    """Convert a value to a non-negative integer safely."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def flatten_text(value):
    """Convert nested repository metadata into searchable text."""
    if isinstance(value, dict):
        return " ".join(
            flatten_text(item)
            for item in value.values()
        )

    if isinstance(value, (list, tuple, set)):
        return " ".join(
            flatten_text(item)
            for item in value
        )

    return str(value or "")


def calculate_health_score(data):
    """
    Calculate an explainable repository health estimate.

    This is a heuristic based on visible repository signals.
    It is not a code-quality audit or security assessment.
    """

    documentation_files = data.get("documentation_files") or []
    configuration_files = data.get("configuration_files") or []
    structure = data.get("structure") or {}
    statistics = data.get("statistics") or {}

    if not isinstance(documentation_files, list):
        documentation_files = []

    if not isinstance(configuration_files, list):
        configuration_files = []

    if not isinstance(structure, (dict, list, tuple)):
        structure = {}

    if not isinstance(statistics, dict):
        statistics = {}

    structure_text = flatten_text(structure).lower()
    config_text = flatten_text(configuration_files).lower()
    docs_text = flatten_text(documentation_files).lower()

    readme = data.get("readme")
    readme_found = bool(
        data.get("readme_found")
        or (isinstance(readme, str) and readme.strip())
        or (isinstance(readme, dict) and readme)
    )

    # 1. Documentation: 25 points
    documentation_score = 0

    if readme_found:
        documentation_score += 15

    if documentation_files:
        documentation_score += 10

    documentation_score = min(documentation_score, 25)

    # 2. Testing signals: 25 points
    testing_score = 0

    testing_terms = (
        "test",
        "tests",
        "testing",
        "pytest",
        "unittest",
        "tox",
        "jest",
        "vitest",
        "mocha",
        "spec",
    )

    testing_text = f"{structure_text} {config_text} {docs_text}"

    if any(term in testing_text for term in testing_terms):
        testing_score += 15

    if any(
        term in config_text
        for term in ("pytest", "tox", "jest", "vitest", "unittest")
    ):
        testing_score += 10

    testing_score = min(testing_score, 25)

    # 3. Configuration: 20 points
    config_count = len(configuration_files)
    configuration_score = min(config_count * 5, 20)

    # 4. Organization: 15 points
    organization_score = 0

    if isinstance(structure, dict):
        folders = (
            structure.get("folders")
            or structure.get("directories")
            or structure.get("top_level_folders")
            or []
        )
        files = (
            structure.get("files")
            or structure.get("top_level_files")
            or []
        )
    else:
        folders = []
        files = []

    if isinstance(folders, (list, tuple)) and folders:
        organization_score += 10

    if isinstance(files, (list, tuple)) and files:
        organization_score += 5

    if organization_score == 0 and structure_text.strip():
        organization_score = 5

    organization_score = min(organization_score, 15)

    # 5. Activity signals: 15 points
    activity_score = 0

    commits = safe_count(data.get("total_commits"))
    contributors = safe_count(data.get("total_contributors"))

    if commits >= 1:
        activity_score += 8

    if commits >= 10:
        activity_score += 3

    if contributors >= 1:
        activity_score += 4

    activity_score = min(activity_score, 15)

    breakdown = {
        "Documentation": documentation_score,
        "Testing signals": testing_score,
        "Configuration": configuration_score,
        "Organization": organization_score,
        "Activity signals": activity_score,
    }

    total_score = min(sum(breakdown.values()), 100)

    return total_score, breakdown


def display_health_score(data):
    """Display the repository health estimate and category bar chart."""

    score, breakdown = calculate_health_score(data)

    st.divider()
    st.header("🩺 Repository Health")

    st.caption(
        "An indicative score based on repository-visible signals. "
        "It does not replace code review, automated tests, or a security audit."
    )

    score_col, detail_col = st.columns([1, 2])

    with score_col:
        st.metric(
            label="Repository Health Score",
            value=f"{score}/100",
        )
        st.progress(score / 100)

        if score >= 80:
            st.success("Many of the measured signals are present.")
        elif score >= 50:
            st.info(
                "Some measured signals are present; review the breakdown."
            )
        else:
            st.warning(
                "Several measured signals were not detected. "
                "Check the breakdown and repository metadata."
            )

    with detail_col:
        st.subheader("Health Category Breakdown")
        st.bar_chart(
            breakdown,
            horizontal=True,
            y_label="Points",
            x_label="Category",
            height=280,
        )

    with st.expander("How is this score calculated?"):
        st.markdown(
            """
            | Category | Maximum points | Signal measured |
            |---|---:|---|
            | Documentation | 25 | README and documentation files |
            | Testing signals | 25 | Test-related names and testing configuration |
            | Configuration | 20 | Detected project configuration files |
            | Organization | 15 | Available folder and file structure |
            | Activity signals | 15 | Commit and contributor counts |

            **Important:** This is a simple heuristic. Detecting test files
            does not prove that tests pass, and commit counts do not establish
            code quality. A low score can also reflect incomplete metadata
            or an unusual repository layout.
            """
        )


# ----------------------------------------
# Backend Helpers
# ----------------------------------------

def show_backend_error(response, default_message):
    """Display a useful error from a FastAPI response."""
    try:
        error_data = response.json()

        if isinstance(error_data, dict):
            message = (
                error_data.get("detail")
                or error_data.get("message")
                or default_message
            )
        else:
            message = default_message

        if isinstance(message, (dict, list)):
            message = json.dumps(
                message,
                ensure_ascii=False,
                indent=2,
            )

        st.error(
            f"{message} (HTTP {response.status_code})"
        )

    except (ValueError, AttributeError):
        response_text = getattr(response, "text", "")

        if response_text:
            st.error(
                f"{default_message} "
                f"Backend response: {response_text[:1000]}"
            )
        else:
            st.error(
                f"{default_message} (HTTP {response.status_code})"
            )


def post_to_backend(endpoint, params, timeout):
    """Send a POST request and display connection errors clearly."""
    try:
        return requests.post(
            f"{BACKEND_URL}/{endpoint}",
            params=params,
            timeout=timeout,
        )

    except requests.exceptions.ConnectionError:
        st.error(
            "❌ Cannot connect to the backend. "
            "Make sure FastAPI is running at "
            f"{BACKEND_URL}."
        )

    except requests.exceptions.Timeout:
        st.error(
            "⏱ The backend request timed out. "
            "The repository or AI response may be taking too long. "
            "Please try again."
        )

    except requests.exceptions.RequestException as exc:
        st.error(f"❌ Backend request failed: {exc}")

    return None


def display_string_list(items, empty_message):
    """Render a list of values safely."""
    if not items:
        st.info(empty_message)
        return

    if isinstance(items, str):
        items = [items]

    if not isinstance(items, (list, tuple, set)):
        items = [items]

    for item in items:
        st.write(f"• {item}")


def start_analysis_job(repo_url):
    """Start an asynchronous repository analysis job."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/analyze-progress",
            params={"repo_url": repo_url},
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        st.error(
            "❌ Cannot connect to FastAPI. "
            f"Check that the backend is running at {BACKEND_URL}."
        )
        return None
    except requests.exceptions.Timeout:
        st.error(
            "⏱ The backend did not respond while starting the job."
        )
        return None
    except requests.exceptions.RequestException as exc:
        st.error(f"❌ Unable to start analysis: {exc}")
        return None

    if response.status_code != 200:
        show_backend_error(
            response,
            "Unable to start repository analysis.",
        )
        return None

    try:
        result = response.json()
    except ValueError:
        st.error("The backend returned invalid JSON when starting analysis.")
        return None

    job_id = result.get("job_id")

    if not isinstance(job_id, str) or not job_id.strip():
        st.error(
            "The backend did not return a valid job ID. "
            "Check the POST /analyze-progress response."
        )
        return None

    return job_id


def get_analysis_progress(job_id):
    """Fetch the current status of a background analysis job."""
    try:
        response = requests.get(
            f"{BACKEND_URL}/analysis-progress/{job_id}",
            timeout=30,
        )
    except requests.exceptions.RequestException:
        return None, "temporary"

    if response.status_code != 200:
        return response, "error"

    try:
        return response.json(), "success"
    except ValueError:
        return None, "invalid_json"


def run_analysis_with_progress(repo_url):
    """Start a job, poll progress, and return its completed analysis result."""

    st.session_state.analysis = None
    st.session_state.pdf_bytes = None
    st.session_state.last_question = ""
    st.session_state.last_answer = ""

    progress_bar = st.progress(0)
    status_container = st.status(
        "Starting repository analysis...",
        expanded=True,
    )
    progress_details = st.empty()

    job_id = start_analysis_job(repo_url)

    if not job_id:
        status_container.update(
            label="Unable to start repository analysis",
            state="error",
        )
        return None

    st.session_state.last_job_id = job_id

    status_container.update(
        label="Repository analysis is running",
        state="running",
    )

    progress_details.markdown(
        f"**Job ID:** `{job_id}`  \n"
        "**Stage:** queued  \n"
        "**Progress:** 0%"
    )

    start_time = time.monotonic()
    last_temporary_error = 0.0

    while time.monotonic() - start_time < MAX_ANALYSIS_WAIT_SECONDS:
        job_data, outcome = get_analysis_progress(job_id)

        if outcome == "temporary":
            now = time.monotonic()

            if now - last_temporary_error >= 10:
                progress_details.warning(
                    "Temporary connection issue while checking progress. "
                    "Retrying..."
                )
                last_temporary_error = now

            time.sleep(PROGRESS_POLL_INTERVAL)
            continue

        if outcome == "error":
            show_backend_error(
                job_data,
                "Unable to retrieve analysis progress.",
            )
            status_container.update(
                label="Progress request failed",
                state="error",
            )
            return None

        if outcome == "invalid_json":
            st.error(
                "The backend returned invalid JSON for the progress request."
            )
            status_container.update(
                label="Invalid progress response",
                state="error",
            )
            return None

        status = str(
            job_data.get("status", "running")
        ).lower()

        stage = job_data.get("stage", "processing")
        message = job_data.get(
            "message",
            "Analyzing repository...",
        )

        try:
            percent = int(job_data.get("percent", 0))
        except (TypeError, ValueError):
            percent = 0

        percent = max(0, min(100, percent))
        progress_bar.progress(percent)

        progress_details.markdown(
            f"**Job ID:** `{job_id}`  \n"
            f"**Stage:** {stage}  \n"
            f"**Progress:** {percent}%  \n"
            f"{message}"
        )

        if status == "completed":
            analysis_result = job_data.get("result")

            if not isinstance(analysis_result, dict):
                st.error(
                    "The job completed, but the backend did not return "
                    "a valid analysis result. Confirm that the latest "
                    "backend main.py is running."
                )
                status_container.update(
                    label="Analysis result unavailable",
                    state="error",
                )
                return None

            progress_bar.progress(100)
            status_container.update(
                label="Repository analysis completed!",
                state="complete",
            )

            return analysis_result

        if status in ("failed", "error", "cancelled"):
            error_message = (
                job_data.get("error")
                or message
                or "Repository analysis failed."
            )
            st.error(str(error_message))
            status_container.update(
                label="Repository analysis failed",
                state="error",
            )
            return None

        time.sleep(PROGRESS_POLL_INTERVAL)

    st.error(
        "Analysis exceeded the 30-minute frontend waiting limit. "
        "The backend job may still be running. "
        "You can check its status using the job ID shown above."
    )
    status_container.update(
        label="Frontend waiting limit reached",
        state="error",
    )
    return None


# ----------------------------------------
# Analysis Dashboard
# ----------------------------------------

def display_analysis(data):
    """Render the complete repository analysis dashboard."""

    # =====================================
    # Repository Overview
    # =====================================

    st.header("📁 Repository Overview")

    st.write(
        f"**Repository:** "
        f"{data.get('repository_name', 'Unavailable')}"
    )
    st.write(
        f"**Default Branch:** "
        f"{data.get('default_branch', 'Unavailable')}"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Branches",
            data.get("total_branches", 0),
        )

    with col2:
        st.metric(
            "Commits",
            data.get("total_commits", 0),
        )

    with col3:
        st.metric(
            "Contributors",
            data.get("total_contributors", 0),
        )

    # =====================================
    # Repository Health
    # =====================================

    display_health_score(data)

    # =====================================
    # Programming Languages
    # =====================================

    st.divider()
    st.header("🐍 Programming Languages")

    languages = data.get("languages") or {}

    if isinstance(languages, dict) and languages:
        valid_languages = {
            str(language): count
            for language, count in languages.items()
            if isinstance(count, (int, float)) and count > 0
        }

        total_files = sum(valid_languages.values())

        if total_files > 0:
            st.subheader("Language Distribution")

            chart_data = {
                "Language": list(valid_languages.keys()),
                "Files": list(valid_languages.values()),
            }

            st.vega_lite_chart(
                chart_data,
                {
                    "mark": {
                        "type": "arc",
                        "innerRadius": 45,
                    },
                    "encoding": {
                        "theta": {
                            "field": "Files",
                            "type": "quantitative",
                        },
                        "color": {
                            "field": "Language",
                            "type": "nominal",
                            "legend": {
                                "title": "Languages",
                            },
                        },
                        "tooltip": [
                            {
                                "field": "Language",
                                "type": "nominal",
                            },
                            {
                                "field": "Files",
                                "type": "quantitative",
                            },
                        ],
                    },
                    "view": {
                        "stroke": None,
                    },
                },
                use_container_width=True,
            )

            st.subheader("Language Details")

            for language, count in valid_languages.items():
                percentage = (count / total_files) * 100

                st.write(
                    f"**{language}** — {count} files "
                    f"({percentage:.1f}%)"
                )
                st.progress(
                    min(max(percentage / 100, 0.0), 1.0)
                )
        else:
            st.info("No programming languages detected.")
    else:
        st.info("No programming languages detected.")

    # =====================================
    # Dependencies
    # =====================================

    st.divider()
    st.header("📦 Dependencies")

    dependencies = data.get("dependencies") or []

    if dependencies:
        display_string_list(
            dependencies,
            "No dependencies found.",
        )
    else:
        st.info("No dependencies found.")

    # =====================================
    # Hotspot Files
    # =====================================

    st.divider()
    st.header("🔥 Hotspot Files")

    hotspot_files = data.get("hotspot_files") or []

    if hotspot_files:
        for item in hotspot_files:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                file_name, changes = item[0], item[1]
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.write(str(file_name))

                with col2:
                    st.write(f"**{changes} commits**")

            elif isinstance(item, dict):
                st.write(
                    f"**{item.get('file', item.get('name', 'File'))}**"
                )
                st.write(
                    f"{item.get('changes', item.get('commits', 0))} commits"
                )
            else:
                st.write(str(item))
    else:
        st.info("No hotspot files found.")

    # =====================================
    # Repository Statistics
    # =====================================

    st.divider()
    st.header("📊 Repository Statistics")

    statistics = data.get("statistics") or {}

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "📄 Total Files",
            statistics.get("total_files", 0),
        )

    with col2:
        st.metric(
            "📁 Total Directories",
            statistics.get("total_directories", 0),
        )

    # =====================================
    # AI Summary
    # =====================================

    st.divider()
    st.header("🤖 AI Summary")

    summary = data.get("ai_summary") or {}

    st.subheader("📌 Repository Purpose")
    st.write(
        summary.get(
            "repository_purpose",
            "Purpose not available.",
        )
    )

    st.subheader("🛠 Technologies Used")
    display_string_list(
        summary.get("technologies_used") or [],
        "No technologies were identified.",
    )

    st.subheader("🏗 Project Organization")
    st.write(
        summary.get(
            "project_organization",
            "Project organization not available.",
        )
    )

    st.subheader("👥 Intended Users")
    st.write(
        summary.get(
            "intended_users",
            "Intended users not available.",
        )
    )

    st.subheader("📖 Beginner Summary")
    st.write(
        summary.get(
            "beginner_summary",
            "Beginner summary not available.",
        )
    )

    # =====================================
    # PDF Report
    # =====================================

    st.divider()
    st.header("📄 Export Analysis Report")

    if st.button(
        "Generate PDF Report",
        key="generate_pdf_report",
        type="primary",
    ):
        if not st.session_state.repo_url:
            st.warning(
                "Please analyze a repository before generating a report."
            )
        else:
            with st.spinner("Generating PDF report..."):
                response = post_to_backend(
                    "generate-report",
                    {
                        "repo_url": st.session_state.repo_url,
                    },
                    timeout=300,
                )

                if response is not None:
                    if response.status_code == 200:
                        content_type = response.headers.get(
                            "content-type",
                            "",
                        ).lower()

                        if (
                            "application/pdf" not in content_type
                            or not response.content.startswith(b"%PDF")
                        ):
                            st.session_state.pdf_bytes = None
                            st.error(
                                "The backend responded successfully, "
                                "but the response does not appear to be "
                                "a valid PDF. Check the FastAPI logs."
                            )
                        else:
                            st.session_state.pdf_bytes = response.content
                            st.success(
                                "✅ PDF report generated successfully!"
                            )
                    else:
                        st.session_state.pdf_bytes = None
                        show_backend_error(
                            response,
                            "Unable to generate the PDF report.",
                        )

    if st.session_state.pdf_bytes:
        st.download_button(
            label="⬇ Download Repository Report",
            data=st.session_state.pdf_bytes,
            file_name=PDF_FILENAME,
            mime="application/pdf",
            key="download_repository_pdf",
        )

    # =====================================
    # AI Recommendations
    # =====================================

    st.divider()
    st.header("💡 AI Recommendations")

    recommendations = data.get("ai_recommendations") or {}

    st.subheader("✅ Repository Strengths")
    display_string_list(
        recommendations.get("strengths") or [],
        "No strengths were provided.",
    )

    st.subheader("⚠ Areas for Improvement")
    display_string_list(
        recommendations.get("areas_for_improvement") or [],
        "No improvement areas were provided.",
    )

    st.subheader("⭐ Best Practices")
    display_string_list(
        recommendations.get("best_practices") or [],
        "No best-practice suggestions were provided.",
    )

    st.subheader("🏆 Overall Repository Quality")
    st.write(
        recommendations.get(
            "overall_quality",
            "Assessment unavailable.",
        )
    )

    # =====================================
    # Ask AI
    # =====================================

    st.divider()
    st.header("💬 Ask AI About This Repository")

    question = st.text_input(
        "Ask anything about this repository",
        key="repository_question",
        placeholder=(
            "Example: Explain the project architecture "
            "or identify the main dependencies."
        ),
    )

    if st.button(
        "Ask AI",
        key="ask_repository_ai",
        type="primary",
    ):
        if not question.strip():
            st.warning("Please enter a question.")
        elif not st.session_state.repo_url:
            st.warning("Please analyze a repository first.")
        else:
            with st.spinner("AI is analyzing your question..."):
                response = post_to_backend(
                    "ask",
                    {
                        "repo_url": st.session_state.repo_url,
                        "question": question.strip(),
                    },
                    timeout=180,
                )

                if response is not None:
                    if response.status_code == 200:
                        try:
                            result = response.json()
                        except ValueError:
                            st.error(
                                "The backend returned an invalid response."
                            )
                        else:
                            if result.get("status") == "error":
                                st.error(
                                    result.get(
                                        "message",
                                        "Unable to answer the question.",
                                    )
                                )
                            else:
                                answer = result.get(
                                    "answer",
                                    "The AI returned no answer.",
                                )
                                st.session_state.last_question = (
                                    question.strip()
                                )
                                st.session_state.last_answer = str(answer)
                    else:
                        show_backend_error(
                            response,
                            "The AI request failed.",
                        )

    if st.session_state.last_answer:
        st.subheader("🧠 AI Answer")
        st.caption(
            f"Question: {st.session_state.last_question}"
        )
        st.markdown(st.session_state.last_answer)


# ----------------------------------------
# Main Page
# ----------------------------------------

st.title("📊 GitHub Repository Analyzer")
st.write(
    "Analyze a public GitHub repository, explore its structure, "
    "review AI insights, ask questions, and export a PDF report."
)

repo_url = st.text_input(
    "Enter GitHub Repository URL",
    value=st.session_state.repo_url,
    placeholder="https://github.com/username/repository",
    key="repository_url_input",
)

if st.button(
    "Analyze Repository",
    key="analyze_repository",
    type="primary",
):
    cleaned_repo_url = repo_url.strip()

    if not cleaned_repo_url:
        st.error("Please enter a GitHub repository URL.")
    else:
        st.session_state.repo_url = cleaned_repo_url

        analysis_result = run_analysis_with_progress(
            cleaned_repo_url
        )

        if analysis_result is not None:
            st.session_state.analysis = analysis_result
            st.session_state.pdf_bytes = None
            st.session_state.last_question = ""
            st.session_state.last_answer = ""
            st.success("✅ Repository analysis completed!")


# ----------------------------------------
# Display Results
# ----------------------------------------

if st.session_state.analysis:
    display_analysis(st.session_state.analysis)