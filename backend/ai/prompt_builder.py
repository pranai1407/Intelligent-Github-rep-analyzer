class PromptBuilder:
    """
    Builds prompts for different AI tasks.

    Supported AI tasks:
    - Repository summary
    - Repository questions
    - Repository recommendations
    - Repository improvements
    """

    def build_summary_prompt(self, analysis):
        """
        Build a prompt for generating a repository summary.
        """

        return f"""
You are an experienced software engineer.

Analyze the following GitHub repository.

Repository Name:
{analysis["repository_name"]}

Languages:
{analysis["languages"]}

Dependencies:
{analysis["dependencies"]}

Repository Structure:
{analysis["structure"]}

Documentation:
{analysis["documentation"]}

Configuration Files:
{analysis.get("configuration_files", [])}

Repository Statistics:
{analysis.get("statistics", {})}

README:
{analysis["readme"]}

IMPORTANT:

Return ONLY valid JSON.

Do not return Markdown.
Do not return explanations.
Do not wrap the JSON in ```.

Return exactly in this format:

{{
    "repository_purpose": "...",
    "technologies_used": [
        "...",
        "..."
    ],
    "project_organization": "...",
    "intended_users": "...",
    "beginner_summary": "..."
}}
"""

    def build_qa_prompt(self, analysis, question):
        """
        Build a prompt for answering a user's question
        about the repository.
        """

        return f"""
You are an experienced software engineer.

Answer the user's question using only the repository
information provided below.

Repository Information:

Repository Name:
{analysis["repository_name"]}

Default Branch:
{analysis.get("default_branch", "Unknown")}

Languages:
{analysis["languages"]}

Dependencies:
{analysis["dependencies"]}

Repository Structure:
{analysis["structure"]}

Documentation:
{analysis["documentation"]}

Configuration Files:
{analysis.get("configuration_files", [])}

Repository Statistics:
{analysis.get("statistics", {})}

README:
{analysis["readme"]}

User Question:

{question}

Instructions:

1. Answer the question clearly and directly.
2. Use only the repository information provided above.
3. Do not invent repository features, files, dependencies,
   or implementation details.
4. If the repository information does not contain enough
   information to answer the question, clearly say so.
5. Explain technical concepts in a beginner-friendly way
   when appropriate.
"""

    def build_recommendation_prompt(self, analysis):
        """
        Build a prompt for generating repository recommendations.
        """

        return f"""
You are an experienced software architect.

Analyze the following GitHub repository.

Repository Name:
{analysis["repository_name"]}

Languages:
{analysis["languages"]}

Dependencies:
{analysis["dependencies"]}

Repository Structure:
{analysis["structure"]}

Documentation:
{analysis["documentation"]}

Configuration Files:
{analysis.get("configuration_files", [])}

Repository Statistics:
{analysis.get("statistics", {})}

README:
{analysis["readme"]}

IMPORTANT:

Return ONLY valid JSON.

Do not return Markdown.
Do not return explanations.
Do not wrap the JSON inside ```.

Return exactly in this format:

{{
    "strengths": [
        "...",
        "..."
    ],
    "areas_for_improvement": [
        "...",
        "..."
    ],
    "best_practices": [
        "...",
        "..."
    ],
    "overall_quality": "Excellent"
}}

The "overall_quality" value should be one of:

"Excellent"
"Good"
"Average"
"Needs Improvement"
"""

    def build_improvement_prompt(self, analysis):
        """
        Build a prompt specifically focused on improving
        the repository.
        """

        return f"""
You are an experienced software architect and code reviewer.

Analyze the following GitHub repository and identify
practical ways to improve it.

Repository Name:
{analysis["repository_name"]}

Languages:
{analysis["languages"]}

Dependencies:
{analysis["dependencies"]}

Repository Structure:
{analysis["structure"]}

Documentation:
{analysis["documentation"]}

Configuration Files:
{analysis.get("configuration_files", [])}

Repository Statistics:
{analysis.get("statistics", {})}

README:
{analysis["readme"]}

IMPORTANT:

Return ONLY valid JSON.

Do not return Markdown.
Do not return explanations.
Do not wrap the JSON inside ```.

Return exactly in this format:

{{
    "code_quality": [
        "...",
        "..."
    ],
    "performance": [
        "...",
        "..."
    ],
    "security": [
        "...",
        "..."
    ],
    "documentation": [
        "...",
        "..."
    ],
    "architecture": [
        "...",
        "..."
    ],
    "priority_improvements": [
        "...",
        "..."
    ]
}}

Only recommend improvements that are reasonably supported
by the repository information provided.
Do not invent files, technologies, vulnerabilities,
or implementation details.
"""