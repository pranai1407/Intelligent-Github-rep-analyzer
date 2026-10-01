import json
import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


class GeminiClient:
    """
    Handles communication with the Gemini API.

    The client:
    - Loads GEMINI_API_KEY from the .env file
    - Initializes Gemini safely
    - Sends prompts to Gemini
    - Parses JSON responses when possible
    - Returns normal text when JSON is not returned
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. "
                "Please add GEMINI_API_KEY=your_api_key "
                "to the project's .env file."
            )

        self.client = genai.Client(
            api_key=self.api_key
        )

        self.model = "gemini-flash-latest"

    def _clean_response_text(self, text):
        """
        Remove Markdown code fences and surrounding whitespace.
        """

        if not text:
            return ""

        text = text.strip()

        if text.startswith("```json"):
            text = text[len("```json"):].strip()

        elif text.startswith("```"):
            text = text[3:].strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        return text

    def _try_parse_json(self, text):
        """
        Try to convert Gemini's response into a Python object.

        Returns:
            dict/list when valid JSON is found
            None when the response is not JSON
        """

        if not text:
            return None

        # First try the entire response.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Gemini sometimes places explanatory text around
        # the JSON object.
        object_start = text.find("{")
        object_end = text.rfind("}")

        if (
            object_start != -1
            and object_end != -1
            and object_end > object_start
        ):
            json_text = text[
                object_start:object_end + 1
            ]

            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

        # Also support JSON arrays.
        array_start = text.find("[")
        array_end = text.rfind("]")

        if (
            array_start != -1
            and array_end != -1
            and array_end > array_start
        ):
            json_text = text[
                array_start:array_end + 1
            ]

            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

        return None

    def generate_response(self, prompt):
        """
        Send a prompt to Gemini.

        Returns:
            dict/list when Gemini returns valid JSON,
            otherwise a string response.

        Raises:
            ValueError for invalid input.
            RuntimeError when Gemini cannot generate a response.
        """

        if not isinstance(prompt, str):
            raise ValueError(
                "Gemini prompt must be a string."
            )

        prompt = prompt.strip()

        if not prompt:
            raise ValueError(
                "Gemini prompt cannot be empty."
            )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

        except Exception as exc:
            raise RuntimeError(
                f"Gemini API request failed: {exc}"
            ) from exc

        # Safely obtain response text.
        text = getattr(response, "text", None)

        if text is None:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        text = self._clean_response_text(text)

        if not text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        parsed_json = self._try_parse_json(text)

        if parsed_json is not None:
            return parsed_json

        return text