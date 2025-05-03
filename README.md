# xagentflow

A powerful AI-driven financial analysis platform that enables users to research financial assets, generate and execute trading strategies, and perform backtesting.

## Features

- Research financial assets using AI agents
- Generate and edit action plans before execution
- Collaborate with multiple AI agents for execution
- Generate trading strategies based on research
- Backtest strategies using market data
- Retrieve structured results and task history

## Tech Stack

- **Web Framework:** FastAPI
- **LLM:** Google Gemini (via langchain-google-genai)
- **Workflow/Planning:** LangGraph
- **Multi-Agent Communication:** Autogen
- **Local RAG:** LlamaIndex with BM25
- **Database:** SQLite with SQLAlchemy
- **Data Handling:** Pandas, NumPy
- **Fintech Tools:** pandas-ta, scikit-optimize, vectorbt

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/xagentflow.git
cd xagentflow
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file based on `.env.template`:
```bash
cp .env.template .env
```

5. Configure the following environment variables in `.env`:
```bash
DATABASE_URL=sqlite+aiosqlite:///./xagentflow.db
GEMINI_API_KEY=your_gemini_api_key
EXTERNAL_MARKET_DATA_API_URL=your_market_data_api_url
EXTERNAL_MARKET_DATA_API_KEY=your_market_data_api_key
# EXTERNAL_NEWS_API_URL=your_news_api_url # Removed
# EXTERNAL_NEWS_API_KEY=your_news_api_key # Removed
LOCAL_KB_PATH=/path/to/knowledge/base
```

## Running the Application

1. Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

2. Access the API documentation at:
```
http://localhost:8000/docs
```

## Testing

1. Run tests:
```bash
pytest
```

2. Run tests with coverage:
```bash
pytest --cov=app tests/
```

## API Endpoints

### Tasks

- `POST /api/v1/tasks/` - Create a new task
- `GET /api/v1/tasks/{task_id}` - Get task details
- `PUT /api/v1/tasks/{task_id}/approve` - Approve task plan
- `GET /api/v1/tasks/` - List tasks with filtering

### Authentication

All endpoints require an API key passed in the `X-API-Key` header.

## Development

1. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

2. Run linting:
```bash
flake8 app tests
```

3. Run type checking:
```bash
mypy app
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
