# XAgentFlow API Documentation

## Overview
XAgentFlow is an AI-driven financial analysis platform that combines multiple AI agents to perform research, develop strategies, and execute backtests for financial markets.

## Quick Start

### Installation
```bash
git clone https://github.com/aryamanan/xagentflow.git
cd xagentflow
pip install -r requirements.txt
```

### Environment Setup
Create a `.env` file with:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/xagentflow
GEMINI_API_KEY=your_gemini_api_key
EXTERNAL_MARKET_DATA_API_KEY=your_market_data_api_key
LOCAL_KB_PATH=/path/to/knowledge/base
```

### Running the Server
```bash
uvicorn app.main:app --reload
```

## API Reference

### Authentication
All endpoints require an API key in the header:
```bash
X-API-Key: your_api_key_here
```

### 1. Task Management

#### Create Task
```http
POST /api/v1/tasks/
```

Request Body:
```json
{
    "title": "DeFi Market Analysis",
    "description": "Analyze DeFi market trends",
    "task_type": "RESEARCH",
    "input_data": {
        "timeframe": "2023",
        "focus": "DeFi",
        "metrics": ["TVL", "Volume", "Users"]
    }
}
```

Response:
```json
{
    "id": "uuid",
    "status": "planning",
    "created_at": "2024-03-20T10:00:00Z",
    "title": "DeFi Market Analysis",
    "task_type": "RESEARCH"
}
```

#### Get Task Status
```http
GET /api/v1/tasks/{task_id}
```

Response:
```json
{
    "id": "uuid",
    "status": "pending_approval",
    "plan": {
        "steps": [...],
        "objectives": [...],
        "timeline": {...}
    },
    "output_data": null
}
```

#### Approve Task Plan
```http
PUT /api/v1/tasks/{task_id}/approve
```

Request Body:
```json
{
    "approved": true,
    "feedback": "Optional feedback"
}
```

#### List Tasks
```http
GET /api/v1/tasks/
```

Query Parameters:
- task_types: List[TaskType]
- statuses: List[TaskStatus]
- start_date: datetime
- end_date: datetime
- skip: int
- limit: int

### 2. Research Workflows

#### Start Research Task
```http
POST /api/v1/tasks/
```

Request Body:
```json
{
    "title": "ETH Market Analysis",
    "description": "Technical and fundamental analysis of ETH",
    "task_type": "RESEARCH",
    "input_data": {
        "asset": "ETH",
        "analysis_type": ["technical", "fundamental"],
        "timeframe": "1y"
    }
}
```

### 3. Strategy Development

#### Create Strategy Task
```http
POST /api/v1/tasks/
```

Request Body:
```json
{
    "title": "Momentum Strategy Development",
    "description": "Develop ETH momentum strategy",
    "task_type": "STRATEGY_DEV",
    "input_data": {
        "asset": "ETH",
        "strategy_type": "momentum",
        "parameters": {
            "lookback": 14,
            "threshold": 0.5
        }
    }
}
```

### 4. Backtesting

#### Start Backtest
```http
POST /api/v1/tasks/
```

Request Body:
```json
{
    "title": "Strategy Backtest",
    "description": "Backtest momentum strategy",
    "task_type": "BACKTEST",
    "input_data": {
        "strategy_id": "uuid",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "initial_capital": 10000
    }
}
```

## Task Types

### RESEARCH
Research tasks analyze market trends, assets, or sectors using:
- Market data analysis
- News sentiment analysis
- Technical indicators
- On-chain metrics

### STRATEGY_DEV
Strategy development tasks create trading strategies with:
- Entry/exit rules
- Position sizing
- Risk management
- Parameter optimization

### BACKTEST
Backtest tasks evaluate strategies using:
- Historical data
- Performance metrics
- Risk analysis
- Transaction costs

## Task States

1. PLANNING
   - Initial state
   - Plan generation in progress

2. PENDING_APPROVAL
   - Plan generated
   - Awaiting user approval

3. IN_PROGRESS
   - Plan approved
   - Execution ongoing

4. COMPLETED
   - Task finished successfully
   - Results available

5. FAILED
   - Task encountered error
   - Error details available

## Agent System

### 1. Planner Agent
- Generates execution plans
- Breaks down complex tasks
- Manages dependencies

### 2. Research Agent
- Conducts market analysis
- Processes data
- Generates insights

### 3. Coordinator Agent
- Manages agent communication
- Handles task delegation
- Monitors progress

### 4. Strategy Agent
- Develops trading strategies
- Optimizes parameters
- Generates documentation

### 5. Backtest Agent
- Implements strategies
- Runs simulations
- Analyzes performance

## Integration Examples

### Python Client
```python
import requests

class XAgentFlowClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}
    
    def create_task(self, task_data):
        response = requests.post(
            f"{self.base_url}/tasks/",
            json=task_data,
            headers=self.headers
        )
        return response.json()
    
    def get_task(self, task_id):
        response = requests.get(
            f"{self.base_url}/tasks/{task_id}",
            headers=self.headers
        )
        return response.json()
    
    def approve_task(self, task_id, approved=True):
        response = requests.put(
            f"{self.base_url}/tasks/{task_id}/approve",
            json={"approved": approved},
            headers=self.headers
        )
        return response.json()

# Usage Example
client = XAgentFlowClient(
    "http://localhost:8000/api/v1",
    "your_api_key"
)

# Create research task
task = client.create_task({
    "title": "ETH Analysis",
    "description": "Complete ETH market analysis",
    "task_type": "RESEARCH",
    "input_data": {
        "asset": "ETH",
        "timeframe": "1y"
    }
})

# Monitor and approve
task_id = task["id"]
status = client.get_task(task_id)
if status["status"] == "pending_approval":
    client.approve_task(task_id)
```

## Error Handling

### HTTP Status Codes
- 200: Success
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 500: Internal Server Error

### Error Response Format
```json
{
    "detail": "Error description"
}
```

## Best Practices

1. Task Creation
   - Provide clear descriptions
   - Include all relevant parameters
   - Set appropriate timeframes

2. Plan Approval
   - Review generated plans carefully
   - Provide feedback if rejecting
   - Monitor task progress

3. Error Handling
   - Implement proper error handling
   - Check task status regularly
   - Handle timeouts appropriately

## Rate Limits

- 100 requests per minute per API key
- 1000 requests per hour per API key
- 5 concurrent tasks per user

## Support

For issues or questions:
- GitHub Issues: https://github.com/aryamanan/xagentflow/issues
- Email: support@xagentflow.com 