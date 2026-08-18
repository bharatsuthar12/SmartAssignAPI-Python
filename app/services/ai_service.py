import httpx

from app.core.config import settings


class AIService:

    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.chat_model = settings.ollama_chat_model

    # ---------------------------------------------------------
    # GENERATE EMBEDDING
    # ---------------------------------------------------------

    async def generate_embedding(
        self,
        text: str
    ) -> list[float]:

        payload = {
            "model": self.model,
            "prompt": text
        }

        url = f"{self.base_url}/api/embeddings"

        async with httpx.AsyncClient(
            timeout=120
        ) as client:

            response = await client.post(
                url,
                json=payload
            )

            if response.status_code >= 400:
                print(
                    "OLLAMA EMBEDDING STATUS:",
                    response.status_code
                )
                print(
                    "OLLAMA RESPONSE:",
                    response.text
                )

            response.raise_for_status()

            data = response.json()

        return data.get("embedding", [])

    # ---------------------------------------------------------
    # GENERATE AI REASON
    # ---------------------------------------------------------

    async def generate_reason(
        self,
        new_issue: str,
        existing_issue: str
    ) -> str:

        prompt = f"""
You are an experienced Jira analyst.

Compare the following two Jira issues.

Issue 1:
{new_issue}

Issue 2:
{existing_issue}

Explain why they are similar.

Rules:
- Maximum 30 words.
- Mention only the common problem.
- Do not mention similarity percentage.
- Do not say "Issue 1" or "Issue 2".
- Return only one sentence.
"""

        payload = {
            "model": self.chat_model,
            "prompt": prompt,
            "stream": False
        }

        url = f"{self.base_url}/api/generate"

        async with httpx.AsyncClient(
            timeout=120
        ) as client:

            response = await client.post(
                url,
                json=payload
            )

            if response.status_code >= 400:
                print(
                    "OLLAMA GENERATE STATUS:",
                    response.status_code
                )
                print(
                    "OLLAMA RESPONSE:",
                    response.text
                )

            response.raise_for_status()

            data = response.json()

        return data.get("response", "")