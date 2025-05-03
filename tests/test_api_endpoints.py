import asyncio
import httpx
import pytest
import logging
import sys
from app.models.task import TaskType
import json

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('api_test.log')
    ]
)

logger = logging.getLogger(__name__)

# API endpoint configurations
BASE_URL = "http://localhost:8000"
TASKS_ENDPOINT = f"{BASE_URL}/tasks"

async def test_create_and_execute_research_task():
    """Test the complete workflow of creating and executing a research task."""
    async with httpx.AsyncClient() as client:
        # 1. Create a new research task
        task_data = {
            "type": TaskType.RESEARCH.value,
            "title": "Tech Sector Analysis",
            "description": "Analyze the performance of major tech companies in 2023",
            "input_data": {
                "sector": "Technology",
                "companies": ["Apple", "Microsoft", "Google"],
                "metrics": ["Revenue", "Market Share", "Growth"]
            }
        }
        
        logger.info("Creating new research task...")
        response = await client.post(f"{TASKS_ENDPOINT}/", json=task_data)
        assert response.status_code == 200, f"Failed to create task: {response.text}"
        
        task_id = response.json()["id"]
        logger.info(f"Task created successfully with ID: {task_id}")
        
        # 2. Start task execution
        logger.info(f"Starting task execution for task {task_id}...")
        response = await client.post(f"{TASKS_ENDPOINT}/{task_id}/start")
        assert response.status_code == 200, f"Failed to start task: {response.text}"
        logger.info("Task started successfully")
        
        # 3. Poll task status until completion or failure
        max_retries = 10
        retry_delay = 5
        completed = False
        
        for attempt in range(max_retries):
            logger.info(f"Checking task status (attempt {attempt + 1}/{max_retries})...")
            response = await client.get(f"{TASKS_ENDPOINT}/{task_id}")
            assert response.status_code == 200, f"Failed to get task status: {response.text}"
            
            task_status = response.json()["status"]
            logger.info(f"Current task status: {task_status}")
            
            if task_status in ["COMPLETED", "FAILED"]:
                completed = True
                break
                
            await asyncio.sleep(retry_delay)
            
        assert completed, f"Task did not complete within {max_retries * retry_delay} seconds"
        
        # 4. Get final results
        logger.info("Getting final task results...")
        response = await client.get(f"{TASKS_ENDPOINT}/{task_id}")
        assert response.status_code == 200, f"Failed to get task results: {response.text}"
        
        task_result = response.json()
        logger.info(f"Final task result: {json.dumps(task_result, indent=2)}")
        
        # Verify task completion and results
        assert task_result["status"] in ["COMPLETED", "FAILED"], "Task status should be COMPLETED or FAILED"
        if task_result["status"] == "COMPLETED":
            assert task_result.get("output_data"), "Completed task should have output data"
            
        return task_result

async def test_multiple_concurrent_tasks():
    """Test handling of multiple concurrent research tasks."""
    async with httpx.AsyncClient() as client:
        # Create multiple tasks with different research topics
        topics = [
            "AI Industry Trends",
            "Renewable Energy Market",
            "Healthcare Technology"
        ]
        
        tasks = []
        for topic in topics:
            task_data = {
                "type": TaskType.RESEARCH.value,
                "title": topic,
                "description": f"Analyze market trends and opportunities in {topic}",
                "input_data": {
                    "topic": topic,
                    "timeframe": "2023-2024",
                    "depth": "comprehensive"
                }
            }
            
            logger.info(f"Creating task for topic: {topic}")
            response = await client.post(f"{TASKS_ENDPOINT}/", json=task_data)
            assert response.status_code == 200, f"Failed to create task for {topic}: {response.text}"
            
            task_id = response.json()["id"]
            tasks.append({"id": task_id, "topic": topic})
            logger.info(f"Task created for {topic} with ID: {task_id}")
            
            # Start task execution
            response = await client.post(f"{TASKS_ENDPOINT}/{task_id}/start")
            assert response.status_code == 200, f"Failed to start task for {topic}: {response.text}"
            
        # Monitor all tasks
        max_retries = 15
        retry_delay = 5
        completed_tasks = set()
        
        for attempt in range(max_retries):
            logger.info(f"Checking tasks status (attempt {attempt + 1}/{max_retries})...")
            
            for task in tasks:
                if task["id"] in completed_tasks:
                    continue
                    
                response = await client.get(f"{TASKS_ENDPOINT}/{task['id']}")
                assert response.status_code == 200, f"Failed to get status for task {task['id']}: {response.text}"
                
                status = response.json()["status"]
                logger.info(f"Task {task['id']} ({task['topic']}) status: {status}")
                
                if status in ["COMPLETED", "FAILED"]:
                    completed_tasks.add(task["id"])
                    
            if len(completed_tasks) == len(tasks):
                break
                
            await asyncio.sleep(retry_delay)
            
        # Verify all tasks completed
        assert len(completed_tasks) == len(tasks), "Not all tasks completed within the timeout period"
        
        # Get final results for all tasks
        results = {}
        for task in tasks:
            response = await client.get(f"{TASKS_ENDPOINT}/{task['id']}")
            assert response.status_code == 200, f"Failed to get results for task {task['id']}: {response.text}"
            results[task["topic"]] = response.json()
            
        return results

if __name__ == "__main__":
    try:
        # Run single task test
        logger.info("Starting single task test...")
        single_task_result = asyncio.run(test_create_and_execute_research_task())
        logger.info("Single task test completed successfully")
        
        # Run multiple tasks test
        logger.info("Starting multiple tasks test...")
        multiple_tasks_results = asyncio.run(test_multiple_concurrent_tasks())
        logger.info("Multiple tasks test completed successfully")
        
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
    except Exception as e:
        logger.error(f"Tests failed: {str(e)}")
        raise 