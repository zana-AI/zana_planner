"""
Demo script for testing OpenTelemetry tracing with Google Cloud Trace.

This script demonstrates how to:
1. Set up OpenTelemetry with GCP Cloud Trace exporter
2. Create and instrument spans
3. Test tracing functionality before integrating into the main codebase

Usage:
    python demos/demo_tracing.py

Requirements:
    - GCP_PROJECT_ID in .env
    - GCP_CREDENTIALS_B64 in .env (base64 encoded service account JSON)
    - Google Cloud Trace API enabled in your GCP project
    - Service account with "Cloud Trace Agent" role (roles/cloudtrace.agent)
      or "Cloud Trace Writer" permissions
"""

# gcloud projects add-iam-policy-binding boreal-furnace-428317-p5 --member="serviceAccount:YOUR_SERVICE_ACCOUNT@boreal-furnace-428317-p5.iam.gserviceaccount.com" --role="roles/cloudtrace.agent"

import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import from tm_bot
sys.path.insert(0, str(Path(__file__).parent.parent))

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.resources import Resource

from tm_bot.llms.llm_env_utils import load_llm_env
from tm_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Global tracer (will be initialized in setup_tracing)
tracer = None


def setup_tracing(project_id: str, use_console_fallback: bool = True) -> None:
    """
    Initialize OpenTelemetry tracing with Google Cloud Trace exporter.
    
    Args:
        project_id: GCP project ID for Cloud Trace
        use_console_fallback: If True, also export to console for debugging
    """
    global tracer
    
    try:
        # Create resource with service name
        resource = Resource.create({
            "service.name": "zana-planner",
            "service.version": "1.0.0",
        })
        
        # Configure Google Cloud Trace exporter
        cloud_exporter = CloudTraceSpanExporter(project_id=project_id)
        
        # Set up tracer provider
        provider = TracerProvider(resource=resource)
        
        # Add Cloud Trace exporter
        provider.add_span_processor(BatchSpanProcessor(cloud_exporter))
        
        # Optionally add console exporter for debugging (spans will be printed to console)
        if use_console_fallback:
            console_exporter = ConsoleSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Console exporter enabled - spans will also be printed to console")
        
        trace.set_tracer_provider(provider)
        
        # Get tracer
        tracer = trace.get_tracer(__name__)
        
        logger.info(f"Tracing initialized successfully for project: {project_id}")
        logger.info("Note: If you see permission errors during export, ensure your service account")
        logger.info("      has the 'Cloud Trace Agent' role (roles/cloudtrace.agent)")
        
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")
        raise


def simulate_work(duration: float = 0.1) -> None:
    """Simulate some work by sleeping."""
    time.sleep(duration)


def example_function_with_span(message: str) -> str:
    """
    Example function that creates a span to trace its execution.
    
    Args:
        message: Input message
        
    Returns:
        Response string
    """
    with tracer.start_as_current_span("zana_request") as span:
        # Add attributes to the span
        span.set_attribute("message", message)
        span.set_attribute("function", "example_function_with_span")
        
        # Simulate some processing
        with tracer.start_as_current_span("process_message") as process_span:
            process_span.set_attribute("message_length", len(message))
            simulate_work(0.05)
            processed = message.upper()
        
        # Simulate another operation
        with tracer.start_as_current_span("format_response") as format_span:
            format_span.set_attribute("response_length", len(processed))
            simulate_work(0.03)
            response = f"Processed: {processed}"
        
        span.set_attribute("response", response)
        logger.info(f"Processed message: {message} -> {response}")
        
        return response


def example_nested_spans() -> dict:
    """
    Example function demonstrating nested spans for complex operations.
    
    Returns:
        Dictionary with operation results
    """
    with tracer.start_as_current_span("complex_operation") as root_span:
        root_span.set_attribute("operation_type", "nested_processing")
        
        results = {}
        
        # First sub-operation
        with tracer.start_as_current_span("fetch_data") as fetch_span:
            fetch_span.set_attribute("data_source", "database")
            simulate_work(0.1)
            results["data"] = {"items": [1, 2, 3, 4, 5]}
            fetch_span.set_attribute("items_count", len(results["data"]["items"]))
        
        # Second sub-operation
        with tracer.start_as_current_span("process_data") as process_span:
            process_span.set_attribute("algorithm", "aggregation")
            simulate_work(0.15)
            results["processed"] = sum(results["data"]["items"])
            process_span.set_attribute("result", results["processed"])
        
        # Third sub-operation
        with tracer.start_as_current_span("save_results") as save_span:
            save_span.set_attribute("storage_type", "cache")
            simulate_work(0.08)
            results["saved"] = True
            save_span.set_attribute("success", True)
        
        root_span.set_attribute("total_items", len(results["data"]["items"]))
        root_span.set_attribute("final_sum", results["processed"])
        
        logger.info(f"Complex operation completed: {results}")
        return results


def example_error_handling():
    """
    Example function demonstrating error handling in spans.
    """
    with tracer.start_as_current_span("operation_with_error") as span:
        span.set_attribute("operation", "error_demo")
        
        try:
            # Simulate an operation that might fail
            with tracer.start_as_current_span("risky_operation") as risky_span:
                risky_span.set_attribute("risk_level", "high")
                simulate_work(0.05)
                
                # Simulate an error condition
                raise ValueError("Simulated error for testing")
                
        except ValueError as e:
            # Record the exception in the span
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.set_attribute("error_handled", True)
            logger.warning(f"Error handled in span: {e}")
            return {"error": str(e), "handled": True}


def simulate_database_query(query: str, table: str) -> dict:
    """Simulate a database query operation."""
    with tracer.start_as_current_span("db.query") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.name", "zana_db")
        span.set_attribute("db.table", table)
        span.set_attribute("db.statement", query)
        
        simulate_work(0.08)  # Database queries take time
        
        # Simulate query results
        results = {
            "user_id": 12345,
            "username": "demo_user",
            "email": "user@example.com",
            "preferences": {"theme": "dark", "notifications": True}
        }
        
        span.set_attribute("db.rows_returned", 1)
        span.set_attribute("db.query.duration_ms", 80)
        logger.info(f"Database query executed: {query}")
        
        return results


def simulate_external_api_call(endpoint: str, method: str = "GET") -> dict:
    """Simulate an external API call."""
    with tracer.start_as_current_span("http.request") as span:
        span.set_attribute("http.method", method)
        span.set_attribute("http.url", endpoint)
        span.set_attribute("http.scheme", "https")
        span.set_attribute("net.peer.name", "api.external-service.com")
        
        simulate_work(0.12)  # External API calls are slower
        
        # Simulate API response
        response = {
            "status": 200,
            "data": {
                "recommendations": ["item1", "item2", "item3"],
                "score": 0.95
            }
        }
        
        span.set_attribute("http.status_code", response["status"])
        span.set_attribute("http.response_size", 256)
        logger.info(f"External API call completed: {endpoint}")
        
        return response


def process_user_data(user_data: dict, api_data: dict) -> dict:
    """Process and combine user data with API data."""
    with tracer.start_as_current_span("data_processing") as span:
        span.set_attribute("processing.type", "data_merge")
        span.set_attribute("input.user_id", user_data.get("user_id"))
        
        # Simulate data transformation
        with tracer.start_as_current_span("data_transform") as transform_span:
            transform_span.set_attribute("transform.operation", "normalize")
            simulate_work(0.03)
            
            processed = {
                "user": {
                    "id": user_data["user_id"],
                    "name": user_data["username"],
                    "email": user_data["email"]
                },
                "recommendations": api_data["data"]["recommendations"],
                "confidence": api_data["data"]["score"]
            }
            
            transform_span.set_attribute("output.items", len(processed["recommendations"]))
        
        # Simulate validation
        with tracer.start_as_current_span("data_validation") as validation_span:
            validation_span.set_attribute("validation.rules", "required_fields,format_check")
            simulate_work(0.02)
            validation_span.set_attribute("validation.passed", True)
        
        span.set_attribute("output.size", len(str(processed)))
        logger.info("Data processing completed")
        
        return processed


def format_response(processed_data: dict) -> dict:
    """Format the final response."""
    with tracer.start_as_current_span("response_formatting") as span:
        span.set_attribute("format.type", "json")
        
        # Simulate response formatting
        with tracer.start_as_current_span("serialize") as serialize_span:
            serialize_span.set_attribute("serialize.format", "json")
            simulate_work(0.01)
            
            response = {
                "status": "success",
                "timestamp": time.time(),
                "data": processed_data
            }
            
            serialize_span.set_attribute("serialize.size_bytes", len(str(response)))
        
        span.set_attribute("response.status", "success")
        logger.info("Response formatted successfully")
        
        return response


def handle_incoming_request(request_data: dict) -> dict:
    """
    Main request handler that demonstrates a full call stack.
    
    This simulates a realistic scenario:
    1. Request comes in
    2. Authentication/validation
    3. Database query
    4. External API call
    5. Data processing
    6. Response formatting
    
    All of this will be visible as a hierarchical trace in Cloud Trace.
    """
    with tracer.start_as_current_span("request_handler") as root_span:
        # Set request-level attributes
        root_span.set_attribute("http.method", request_data.get("method", "POST"))
        root_span.set_attribute("http.route", "/api/user/recommendations")
        root_span.set_attribute("request.id", request_data.get("request_id", "req_123"))
        root_span.set_attribute("user.id", request_data.get("user_id"))
        
        logger.info(f"Processing request: {request_data.get('request_id')}")
        
        # Step 1: Authenticate and validate
        with tracer.start_as_current_span("auth.validate") as auth_span:
            auth_span.set_attribute("auth.type", "token")
            auth_span.set_attribute("auth.token_present", bool(request_data.get("token")))
            simulate_work(0.05)
            auth_span.set_attribute("auth.valid", True)
            logger.info("Authentication successful")
        
        # Step 2: Query database for user data
        user_data = simulate_database_query(
            "SELECT * FROM users WHERE user_id = $1",
            "users"
        )
        
        # Step 3: Call external API for recommendations
        api_response = simulate_external_api_call(
            "https://api.external-service.com/v1/recommendations",
            "GET"
        )
        
        # Step 4: Process and combine the data
        processed_data = process_user_data(user_data, api_response)
        
        # Step 5: Format the response
        final_response = format_response(processed_data)
        
        # Set final attributes on root span
        root_span.set_attribute("response.status_code", 200)
        root_span.set_attribute("response.size_bytes", len(str(final_response)))
        root_span.set_status(trace.Status(trace.StatusCode.OK))
        
        logger.info("Request processed successfully")
        return final_response


def run_demo(project_id: str):
    """Run all demo examples.
    
    Args:
        project_id: GCP project ID for generating trace console URL
    """
    logger.info("=" * 60)
    logger.info("Starting OpenTelemetry Tracing Demo")
    logger.info("=" * 60)
    
    # Test 1: Simple span
    logger.info("\n[Test 1] Simple function with span")
    result1 = example_function_with_span("Hello, Zana!")
    logger.info(f"Result: {result1}")
    
    # Test 2: Nested spans
    logger.info("\n[Test 2] Nested spans example")
    result2 = example_nested_spans()
    logger.info(f"Result: {result2}")
    
    # Test 3: Error handling
    logger.info("\n[Test 3] Error handling in spans")
    result3 = example_error_handling()
    logger.info(f"Result: {result3}")
    
    # Test 4: Full request stack (main demo)
    logger.info("\n" + "=" * 60)
    logger.info("[Test 4] Full Request Stack Demo")
    logger.info("This demonstrates a realistic call stack that you can monitor in Cloud Trace")
    logger.info("=" * 60)
    
    request_data = {
        "request_id": "req_demo_001",
        "user_id": 12345,
        "method": "POST",
        "token": "auth_token_xyz",
        "endpoint": "/api/user/recommendations"
    }
    
    result4 = handle_incoming_request(request_data)
    logger.info(f"Request completed: {result4.get('status')}")
    logger.info(f"Response contains {len(result4.get('data', {}).get('recommendations', []))} recommendations")
    
    logger.info("\n" + "=" * 60)
    logger.info("Demo completed!")
    logger.info("=" * 60)
    
    # Give the batch processor time to export spans
    logger.info("\nWaiting 5 seconds for spans to be exported...")
    logger.info("(Note: If you see permission errors above, check IAM permissions)")
    logger.info("      Required role: roles/cloudtrace.agent")
    time.sleep(5)
    
    logger.info("\n" + "=" * 60)
    logger.info("Check Google Cloud Trace console for spans:")
    logger.info(f"  Direct link: https://console.cloud.google.com/traces/list?project={project_id}")
    logger.info("")
    logger.info("  Or navigate manually:")
    logger.info("  1. Go to: https://console.cloud.google.com/")
    logger.info("  2. Select project: " + project_id)
    logger.info("  3. Navigate to: Observability > Trace")
    logger.info("  4. Or search for 'Trace' in the top search bar")
    logger.info("=" * 60)


def main():
    """Main entry point."""
    try:
        # Load GCP configuration
        logger.info("Loading GCP configuration...")
        cfg = load_llm_env()
        project_id = cfg.get("GCP_PROJECT_ID")
        
        if not project_id:
            raise ValueError("GCP_PROJECT_ID not found in configuration")
        
        logger.info(f"GCP Project ID: {project_id}")
        
        # Set up tracing
        logger.info("Setting up OpenTelemetry tracing...")
        setup_tracing(project_id)
        
        # Run demo
        run_demo(project_id)
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
