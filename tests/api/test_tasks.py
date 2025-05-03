import pytest
from uuid import uuid4
from app.models.task import TaskType, TaskStatus
import time
import asyncio

@pytest.mark.asyncio
async def test_create_task(test_client, api_key_headers):
    task_data = {
        "task_type": "RESEARCH",
        "title": "Research Apple Stock",
        "input_data": {"prompt": "Research Apple stock", "ticker": "AAPL"}
    }
    response = test_client.post(
        "/api/v1/tasks/",
        headers=api_key_headers,
        json=task_data
    )
    if response.status_code == 422:
        print("Create Task Validation Error:", response.json())
    assert response.status_code == 200
    assert "id" in response.json()

@pytest.mark.asyncio
async def test_get_task(test_client, db_session, api_key_headers):
    # First, create a task
    task_data = {
        "task_type": "RESEARCH",
        "title": "Research Google Stock",
        "input_data": {"prompt": "Research Google stock", "ticker": "GOOGL"}
    }
    create_response = test_client.post(
        "/api/v1/tasks/",
        headers=api_key_headers,
        json=task_data
    )
    if create_response.status_code != 200:
        print("Get Task - Create Validation Error:", create_response.json())
        create_response.raise_for_status()
    task_id = create_response.json()["id"]

    # Then, get the task
    get_response = test_client.get(
        f"/api/v1/tasks/{task_id}", headers=api_key_headers
    )
    if get_response.status_code == 422:
        print("Get Task Validation Error:", get_response.json())
    assert get_response.status_code == 200
    retrieved_task = get_response.json()
    assert retrieved_task["id"] == str(task_id)
    assert retrieved_task["task_type"] == "RESEARCH"

    # Test getting non-existent task
    non_existent_uuid = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    get_response_nonexistent = test_client.get(
        f"/api/v1/tasks/{non_existent_uuid}", headers=api_key_headers
    )
    assert get_response_nonexistent.status_code == 404

@pytest.mark.asyncio
async def test_approve_task_plan(test_client, api_key_headers):
    # Create a task
    task_data = {
        "task_type": "STRATEGY_DEV",
        "title": "Develop TSLA Strategy",
        "input_data": {
            "prompt": "Develop a moving average crossover strategy for TSLA"
        }
    }
    response = test_client.post(
        "/api/v1/tasks/",
        headers=api_key_headers,
        json=task_data
    )
    assert response.status_code == 200
    task_id = response.json()["id"]

    # Wait for task to reach PENDING_APPROVAL status
    timeout = 60  # Increased timeout to 60 seconds
    start_time = time.time()
    actual_status = None
    
    while time.time() - start_time < timeout:
        response = test_client.get(f"/api/v1/tasks/{task_id}", headers=api_key_headers)
        assert response.status_code == 200
        actual_status = response.json()["status"]
        if actual_status == "PENDING_APPROVAL":
            break
        time.sleep(1)  # Poll every second
        
    if actual_status != "PENDING_APPROVAL":
        pytest.fail(f"Task {task_id} did not reach PENDING_APPROVAL status within timeout. Final status: {actual_status}")

    # Approve the task plan
    response = test_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        headers=api_key_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"

@pytest.mark.asyncio
async def test_list_tasks(test_client, api_key_headers):
    # Create a few tasks first
    task_types = ["RESEARCH", "STRATEGY_DEV", "BACKTEST"]
    for task_type in task_types:
        task_data = {
            "task_type": task_type,
            "title": f"Test {task_type} Task",
            "input_data": {"prompt": f"Test {task_type} task"}
        }
        response = test_client.post(
            "/api/v1/tasks/",
            headers=api_key_headers,
            json=task_data
        )
        assert response.status_code == 200

    # Test listing all tasks
    response = test_client.get("/api/v1/tasks/", headers=api_key_headers)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks["items"]) >= len(task_types)  # Should have at least our created tasks

    # Test filtering by task type
    response = test_client.get(
        "/api/v1/tasks/?task_types=RESEARCH",
        headers=api_key_headers
    )
    assert response.status_code == 200
    research_tasks = response.json()
    assert all(task["task_type"] == "RESEARCH" for task in research_tasks["items"])