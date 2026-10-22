#!/usr/bin/env python3









import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rest_client import RestClient, RestConfig
from graphql_client import GraphQLClient
from performance import PerformanceTester
from mock_server import MockServer, MockRoute
from reporter import TestReporter, TestReport, TestResult
from assertions import Assertions





def example_rest_api_testing():

    print("\n" + "=" * 60)
    print("Example 1: REST API Testing")
    print("=" * 60)
    
    
    config = RestConfig(
        base_url="https://jsonplaceholder.typicode.com",
        timeout=30,
        retries=3
    )
    
    
    client = RestClient(config)
    
    try:
        
        print("\n1. Testing GET request...")
        response = client.get("/posts/1")
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('content-type')}")
        
        
        Assertions.assert_status_code(response, 200)
        Assertions.assert_json_content_type(response)
        Assertions.assert_json_contains(response, "title")
        print("   ✓ GET request successful")
        
        
        print("\n2. Testing POST request...")
        data = {
            "title": "Test Post",
            "body": "This is a test post",
            "userId": 1
        }
        response = client.post("/posts", json=data)
        print(f"   Status: {response.status_code}")
        Assertions.assert_status_code(response, 201)
        print("   ✓ POST request successful")
        
        
        print("\n3. Testing PUT request...")
        update_data = {
            "id": 1,
            "title": "Updated Title",
            "body": "Updated body",
            "userId": 1
        }
        response = client.put("/posts/1", json=update_data)
        print(f"   Status: {response.status_code}")
        Assertions.assert_ok(response)
        print("   ✓ PUT request successful")
        
        
        print("\n4. Testing DELETE request...")
        response = client.delete("/posts/1")
        print(f"   Status: {response.status_code}")
        Assertions.assert_ok(response)
        print("   ✓ DELETE request successful")
        
    finally:
        client.close()
    
    print("\n✓ REST API Testing completed successfully!")





async def example_async_rest_testing():

    print("\n" + "=" * 60)
    print("Example 2: Async REST API Testing")
    print("=" * 60)
    
    config = RestConfig(
        base_url="https://jsonplaceholder.typicode.com",
        timeout=30
    )
    
    async with RestClient(config).async_session() as client:
        
        print("\n1. Testing concurrent requests...")
        
        tasks = [
            client.get("/posts/1"),
            client.get("/posts/2"),
            client.get("/posts/3"),
        ]
        
        responses = await asyncio.gather(*tasks)
        
        for i, response in enumerate(responses, 1):
            print(f"   Response {i}: Status {response.status_code}")
            Assertions.assert_status_code(response, 200)
        
        print("   ✓ All concurrent requests successful")
    
    print("\n✓ Async REST API Testing completed successfully!")





def example_mock_server():

    print("\n" + "=" * 60)
    print("Example 3: Mock Server")
    print("=" * 60)
    
    
    server = MockServer(host="127.0.0.1", port=8765)
    
    
    server.add_route(
        MockRoute()
        .method("GET")
        .path("/api/users")
        .response(200, {
            "users": [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"}
            ]
        })
    )
    
    server.add_route(
        MockRoute()
        .method("GET")
        .path("/api/users/1")
        .response(200, {"id": 1, "name": "Alice", "email": "alice@example.com"})
    )
    
    server.add_route(
        MockRoute()
        .method("POST")
        .path("/api/users")
        .response(201, {"id": 3, "name": "Charlie", "email": "charlie@example.com"})
    )
    
    
    print("\n1. Starting mock server...")
    server.start()
    
    try:
        import time
        time.sleep(1)  
        
        
        print("\n2. Testing against mock server...")
        
        client = RestClient(RestConfig(base_url="http://127.0.0.1:8765"))
        
        
        response = client.get("/api/users")
        print(f"   GET /api/users: {response.status_code}")
        Assertions.assert_status_code(response, 200)
        Assertions.assert_json_length(response, "users", 2)
        print("   ✓ Users list endpoint works")
        
        
        response = client.get("/api/users/1")
        print(f"   GET /api/users/1: {response.status_code}")
        Assertions.assert_json_path(response, "name", "Alice")
        print("   ✓ Single user endpoint works")
        
        
        response = client.post("/api/users", json={"name": "Charlie"})
        print(f"   POST /api/users: {response.status_code}")
        Assertions.assert_status_code(response, 201)
        print("   ✓ Create user endpoint works")
        
        client.close()
        
        
        print("\n3. Request log:")
        for log in server.get_request_log():
            print(f"   {log['method']} {log['path']}")
        
    finally:
        print("\n4. Stopping mock server...")
        server.stop()
    
    print("\n✓ Mock Server Testing completed successfully!")





async def example_performance_testing():

    print("\n" + "=" * 60)
    print("Example 4: Performance Testing")
    print("=" * 60)
    
    
    tester = PerformanceTester(
        base_url="https://jsonplaceholder.typicode.com",
        concurrency=10,
        duration=10
    )
    
    
    async def test_scenario():
        async with httpx.AsyncClient() as client:
            response = await client.get("https://jsonplaceholder.typicode.com/posts/1")
            return response.status_code == 200
    
    
    print("\n1. Running load test (100 requests, 10 concurrent)...")
    results = await tester.run_load_test(test_scenario, total_requests=100)
    
    print(f"\n   Total Requests: {results.total_requests}")
    print(f"   Successful: {results.successful_requests}")
    print(f"   Failed: {results.failed_requests}")
    print(f"   Error Rate: {results.error_rate:.2f}%")
    print(f"   Avg Response Time: {results.avg_response_time * 1000:.2f}ms")
    print(f"   Min Response Time: {results.min_response_time * 1000:.2f}ms")
    print(f"   Max Response Time: {results.max_response_time * 1000:.2f}ms")
    print(f"   Throughput: {results.throughput:.2f} req/s")
    
    print("\n   Percentiles:")
    percentiles = results.percentiles
    for p, v in percentiles.items():
        print(f"   {p.upper()}: {v * 1000:.2f}ms")
    
    print("\n✓ Performance Testing completed successfully!")





def example_test_reporting():

    print("\n" + "=" * 60)
    print("Example 5: Test Report Generation")
    print("=" * 60)
    
    
    results = [
        TestResult(name="test_get_user", status="passed", duration=0.123),
        TestResult(name="test_create_user", status="passed", duration=0.234),
        TestResult(name="test_update_user", status="passed", duration=0.189),
        TestResult(name="test_delete_user", status="failed", duration=0.456, 
                  message="User not found", output="Traceback..."),
        TestResult(name="test_list_users", status="passed", duration=0.567),
        TestResult(name="test_search_users", status="skipped", duration=0.0,
                  message="Search feature not implemented"),
    ]
    
    
    from datetime import datetime
    report = TestReport(
        timestamp=datetime.now(),
        results=results,
        total_duration=1.569
    )
    
    
    reporter = TestReporter(output_dir="./reports")
    
    
    print("\n1. Generating HTML report...")
    html_path = reporter.generate_html_report(report, "example_report.html")
    print(f"   ✓ HTML report: {html_path}")
    
    print("\n2. Generating JSON report...")
    json_path = reporter.generate_json_report(report, "example_report.json")
    print(f"   ✓ JSON report: {json_path}")
    
    print("\n3. Generating JUnit XML report...")
    xml_path = reporter.generate_junit_xml(report, "example_junit.xml")
    print(f"   ✓ JUnit XML report: {xml_path}")
    
    print("\n4. Generating Allure results...")
    reporter.generate_allure_report(report)
    print("   ✓ Allure results in ./reports/allure-results/")
    
    print("\n   Summary:")
    print(f"   Total: {report.total}")
    print(f"   Passed: {report.passed}")
    print(f"   Failed: {report.failed}")
    print(f"   Skipped: {report.skipped}")
    print(f"   Pass Rate: {report.pass_rate:.1f}%")
    
    print("\n✓ Test Reporting completed successfully!")





def example_graphql_testing():

    print("\n" + "=" * 60)
    print("Example 6: GraphQL Testing")
    print("=" * 60)
    
    
    
    
    print("\nNote: This example uses a mock GraphQL client.")
    print("Replace with your actual GraphQL endpoint.")
    
    
    client = GraphQLClient(
        endpoint="https://api.example.com/graphql",
        headers={"Accept": "application/json"}
    )
    
    
    query = """
    query GetUser($id: ID!) {
        user(id: $id) {
            id
            name
            email
            posts {
                id
                title
            }
        }
    }
    """
    
    print("\n1. Example Query:")
    print(query)
    
    
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
        createPost(input: $input) {
            id
            title
            content
            author {
                name
            }
        }
    }
    """
    
    print("\n2. Example Mutation:")
    print(mutation)
    
    
    print("\n3. Query validation:")
    is_valid = client.validate_query(query)
    print(f"   Query is valid: {is_valid}")
    
    print("\n✓ GraphQL Testing example completed!")





async def main():

    print("\n" + "=" * 60)
    print("API Test Automation - Usage Examples")
    print("=" * 60)
    
    
    example_rest_api_testing()
    await example_async_rest_testing()
    example_mock_server()
    await example_performance_testing()
    example_test_reporting()
    example_graphql_testing()
    
    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
