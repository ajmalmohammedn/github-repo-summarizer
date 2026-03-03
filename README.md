# GitHub Repository Summarizer

A FastAPI service that takes a public GitHub repository URL and returns a structured summary including what the project does, its core technologies, and its directory structure — powered by an LLM.

---

## Setup & Run

### 1. Create and activate a virtual environment

python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

### 2. Install dependencies

pip install -r requirements.txt

### 3. Set up environment variables

Create a `.env` file in the project root:

NEBIUS_API_KEY=your_nebius_api_key_here

### 4. Run the server

uvicorn main:app --reload


The API will be available at `http://localhost:8000/summarize`.

---

## Usage

curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'


**Response:**
{
  "summary": "**Requests** is a popular Python library for making HTTP requests...",
  "technologies": ["Python", "urllib3", "certifi"],
  "structure": "The main source code lives in `src/requests/`, tests in `tests/`, and docs in `docs/`."
}


**Error response:**

{
  "status": "error",
  "message": "Repository not found"
}

---

## Model Choice

This service uses **Kimi K2.5** (`moonshotai/Kimi-K2.5`) via the Nebius API. It was chosen for its strong instruction following and reliable structured JSON output, which is critical for this use case where the response must be parsed directly into a typed Pydantic model.

---

## Approach to Repository Contents

### What is included

**Repository metadata**
 Name, description, and primary languages from the GitHub API give a fast, reliable output about the project's purpose and tech stack

**README** 
The single best source of truth — most well-maintained projects describe their purpose, usage, and structure here

**Languages API** 
 Provides an accurate list of programming languages without having to scan individual files


### What is skipped

**File tree**
The README reliably describes project structure for well-maintained repositories, making a separate tree fetch unnecessary

**Individual source files**
Too large for the LLM context window and rarely needed for a high-level summary
