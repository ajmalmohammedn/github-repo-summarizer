import re
import base64
import json
from typing import List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import Request

from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import os


load_dotenv()

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
if not NEBIUS_API_KEY:
    raise RuntimeError("NEBIUS_API_KEY is not set")

app = FastAPI(title="Public GitHub Repository Summarizer")

client = OpenAI(
    base_url="https://api.tokenfactory.eu-west1.nebius.com/v1/",
    api_key=os.environ.get("NEBIUS_API_KEY")
)

GITHUB_API_BASE = "https://api.github.com/repos"
HEADERS = {"Accept": "application/vnd.github+json"}

# =============================
# Request / Response Pydantic Models
# =============================

class RepoRequest(BaseModel):
    github_url: str


class RepoResponse(BaseModel):
    summary: str
    technologies: List[str]
    structure: str


# =========================
# Exception Handlers
# =========================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "github_url: URL of a public GitHub repository"
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail
        },
    )


# =============================
# Utility Functions
# =============================

def parse_github_url(url: str):
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError("Invalid GitHub repository URL format")
    return match.group(1), match.group(2)


async def fetch_repository_data(owner: str, repo: str) -> tuple[dict, str]: 
    async with httpx.AsyncClient(timeout=10.0) as http_client:

        # Metadata
        meta_resp = await http_client.get(
            f"{GITHUB_API_BASE}/{owner}/{repo}",
            headers=HEADERS
        )

        if meta_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository not found")

        if meta_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub API error")

        meta = meta_resp.json()

        # README (base64 encoded)
        readme_resp = await http_client.get(
            f"{GITHUB_API_BASE}/{owner}/{repo}/readme",
            headers=HEADERS
        )

        if readme_resp.status_code == 200:
            readme_json = readme_resp.json()
            readme = base64.b64decode(
                readme_json["content"]
            ).decode("utf-8", errors="ignore")
        else:
            readme = ""

        # Languages
        languages_resp = await http_client.get(
            meta["languages_url"],
            headers=HEADERS
        )

        languages = (
            list(languages_resp.json().keys())
            if languages_resp.status_code == 200
            else []
        )

    metadata = {
        "name": meta.get("name", ""),
        "description": meta.get("description", ""),
        "languages": languages,
    }

    return metadata, readme


# =============================
# LLM Summary Generator
# =============================

async def generate_summary(metadata: dict, readme: str) -> dict:

    prompt = f"""
                Analyze this public GitHub repository and return a JSON object with exactly these fields:

                - "summary": A concise human-readable explanation of what the project does.
                    - Bold the project name using **Name** markdown at the start.
                    - Example: "**Requests** is a popular Python library for making HTTP requests..."

                - "technologies": A flat list of the 3-5 most important core technologies only.
                    - Include only: primary programming language(s) and the most essential libraries/frameworks.
                    - Exclude: build tools, Makefiles, charset/encoding libraries, minor utilities, and transitive dependencies.
                    - Example: ["Python", "urllib3", "certifi"]

                - "structure": A one or two sentence description of the project layout.
                    - Wrap all directory and file paths in backticks.
                    - Example: "The main source code lives in `src/requests/`, tests in `tests/`, and docs in `docs/`."

                Repository:
                Name: {metadata.get("name")}
                Description: {metadata.get("description")}
                Primary Language: {metadata.get("languages")}

                README:
                {readme}

                Return ONLY valid JSON with no markdown code fences:
                {
                    {
                        "summary": "...",
                        "technologies": ["..."],
                        "structure": "..."
                    }
                }
        """

    response = client.chat.completions.create(
        model="moonshotai/Kimi-K2.5",
        messages=[
            {"role": "system", "content": "You summarize GitHub repositories and respond in strict JSON only. Never wrap your response in markdown code fences."},
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]
    )

    raw = response.choices[0].message.content
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    return json.loads(raw)


# =============================
# API Endpoint
# =============================

@app.post("/summarize", response_model=RepoResponse)
async def summarize_repository(request: RepoRequest):
    try:
        owner, repo = parse_github_url(request.github_url)

        metadata, readme = await fetch_repository_data(owner, repo)

        result = await generate_summary(metadata, readme)

        return RepoResponse(**result)

    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "error", "message": e.detail}
        )

    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "LLM returned invalid JSON"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )