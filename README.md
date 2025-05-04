# XAgentFlow Financial Research Workflow

This project implements a multi-agent financial research workflow using LangGraph and FastAPI. It allows users to create tasks (e.g., stock analysis) which are then processed by a series of AI agents.

## Project Structure

```
├── app/                    # Main application code
│   ├── agents/             # Agent implementations (Planner, Coordinator, Researcher)
│   ├── api/                # FastAPI endpoint definitions
│   ├── core/               # Core components (config, logging)
│   ├── crud/               # Database CRUD operations
│   ├── db/                 # Database session management
│   ├── models/             # Pydantic models and SQLAlchemy tables
│   ├── prompts/            # LLM prompts
│   ├── schemas/            # Pydantic schemas for API validation
│   ├── services/           # Business logic (TaskService)
│   ├── tools/              # Agent tools (financial data, KB query)
│   ├── workflows/          # LangGraph workflow definition
│   ├── main.py             # FastAPI application entry point
│   └── __init__.py
├── tests/                  # Test scripts
│   └── test_execution.py   # Isolated execution test script
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore file
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Features

*   **Task Management API:** Create, retrieve, and approve research tasks via a REST API.
*   **Multi-Agent System:** Uses Planner, Coordinator, and Researcher agents.
*   **Dynamic Planning:** Generates a step-by-step research plan based on the initial request.
*   **Plan Approval:** Requires user approval before executing the generated plan.
*   **Step Execution:** Executes the plan steps, utilizing tools like financial data fetching and technical indicator calculation.
*   **Tool Integration:** Includes tools for fetching stock data (`yfinance`/`yfapi.net`) and calculating indicators (`pandas`).
*   **Workflow Orchestration:** Uses LangGraph to manage the state and flow between agents and steps.
*   **Asynchronous Operations:** Leverages `asyncio` for non-blocking operations.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd xagentflow
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up environment variables:**
    *   Copy `.env.example` to `.env`.
    *   Fill in the required API keys (e.g., `OPENAI_API_KEY`, `EXTERNAL_MARKET_DATA_API_KEY` for yfapi.net) and database URL (`DATABASE_URL`).

## Running the Application

1.  **Start the FastAPI server:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```
    *Note: During debugging, running without `--reload` might be necessary.*

2.  **Interact with the API:**
    *   Use `curl` or an API client (like Postman) to send requests to `http://127.0.0.1:8000/api/v1/...`.
    *   **Create Task:** `POST /api/v1/tasks/`
    *   **Get Task:** `GET /api/v1/tasks/{task_id}`
    *   **Approve Plan:** `POST /api/v1/tasks/{task_id}/approve`

## Current Status & Known Issues

*   The core planning and execution logic has been significantly debugged and refined.
*   Agents interact more directly for step execution.
*   Error handling within the workflow has been improved.
