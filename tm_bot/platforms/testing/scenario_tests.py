"""
Automated scenario tests for bot reasoning and functionality.

This module contains comprehensive test scenarios that test the bot's:
- Command handling
- Natural language understanding
- Reasoning capabilities
- Task management
- Multi-turn conversations
"""

import asyncio
import os
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from platforms.testing import MockPlatformAdapter, CLIPlatformAdapter, TestResponseService
from platforms.types import UserMessage, MessageType
from tm_bot.planner_bot import PlannerBot
from platforms.testing.cli_handler_wrapper import CLIHandlerWrapper
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestScenario:
    """Represents a test scenario."""
    name: str
    description: str
    messages: List[str]  # User messages in sequence
    expected_keywords: List[str] = None  # Keywords that should appear in responses
    expected_behavior: str = None  # Description of expected behavior
    skip_reason: Optional[str] = None  # Reason to skip this test


class ScenarioTestRunner:
    """Runs automated test scenarios against the bot."""
    
    def __init__(self, root_dir: str = None):
        """Initialize test runner."""
        self.root_dir = root_dir or tempfile.mkdtemp(prefix="zana_test_")
        os.makedirs(self.root_dir, exist_ok=True)
        self.bot: Optional[PlannerBot] = None
        self.adapter: Optional[MockPlatformAdapter] = None
        self.handler_wrapper: Optional[CLIHandlerWrapper] = None
        
    async def setup(self):
        """Set up bot and handlers for testing."""
        self.adapter = MockPlatformAdapter()
        self.bot = PlannerBot(self.adapter, root_dir=self.root_dir)
        
        # Create handler wrapper
        if self.bot.message_handlers and self.bot.callback_handlers:
            self.handler_wrapper = CLIHandlerWrapper(
                self.bot.message_handlers,
                self.bot.callback_handlers
            )
    
    async def teardown(self):
        """Clean up after tests."""
        # Cleanup if needed
        pass
    
    async def run_scenario(self, scenario: TestScenario) -> Dict[str, Any]:
        """
        Run a single test scenario.
        
        Returns:
            Dict with test results: {
                'passed': bool,
                'messages': List[Dict],  # All messages sent
                'errors': List[str],     # Any errors encountered
                'assertions': List[str]  # Assertion results
            }
        """
        if scenario.skip_reason:
            return {
                'passed': None,
                'skipped': True,
                'reason': scenario.skip_reason
            }
        
        results = {
            'scenario': scenario.name,
            'passed': False,
            'messages': [],
            'errors': [],
            'assertions': [],
            'response_texts': []
        }
        
        try:
            # Clear previous messages
            self.adapter.response_service.clear()
            
            # Process each message in sequence
            for i, user_message in enumerate(scenario.messages):
                logger.info(f"Scenario '{scenario.name}': Processing message {i+1}/{len(scenario.messages)}: {user_message[:50]}...")
                
                try:
                    if user_message.startswith('/'):
                        # Handle command
                        command = user_message.split()[0][1:]
                        args = user_message.split()[1:] if len(user_message.split()) > 1 else []
                        await self.handler_wrapper.handle_command(command, user_id=1, args=args)
                    else:
                        # Handle regular message
                        await self.handler_wrapper.handle_message(user_message, user_id=1)
                    
                    # Wait a bit for async processing
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    error_msg = f"Error processing message '{user_message}': {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    results['errors'].append(error_msg)
            
            # Get all responses
            messages = self.adapter.response_service.get_messages_for_user(1)
            results['messages'] = messages
            results['response_texts'] = [msg.get('text', '') for msg in messages]
            
            # Check assertions
            if scenario.expected_keywords:
                for keyword in scenario.expected_keywords:
                    found = any(keyword.lower() in msg.get('text', '').lower() for msg in messages)
                    assertion = f"Response contains '{keyword}'"
                    results['assertions'].append({
                        'assertion': assertion,
                        'passed': found
                    })
                    if not found:
                        logger.warning(f"Assertion failed: {assertion}")
            
            # Overall pass if no errors and all assertions passed
            results['passed'] = (
                len(results['errors']) == 0 and
                all(a['passed'] for a in results['assertions'])
            )
            
        except Exception as e:
            error_msg = f"Unexpected error in scenario '{scenario.name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            results['errors'].append(error_msg)
            results['passed'] = False
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print test results in a readable format."""
        print(f"\n{'='*60}")
        print(f"Scenario: {results['scenario']}")
        print(f"{'='*60}")
        
        if results.get('skipped'):
            print(f"⏭️  SKIPPED: {results.get('reason', 'No reason provided')}")
            return
        
        status = "✅ PASSED" if results['passed'] else "❌ FAILED"
        print(f"Status: {status}")
        
        if results.get('errors'):
            print(f"\nErrors ({len(results['errors'])}):")
            for error in results['errors']:
                print(f"  ❌ {error}")
        
        if results.get('assertions'):
            print(f"\nAssertions ({len(results['assertions'])}):")
            for assertion in results['assertions']:
                status_icon = "✅" if assertion['passed'] else "❌"
                print(f"  {status_icon} {assertion['assertion']}")
        
        if results.get('response_texts'):
            print(f"\nBot Responses ({len(results['response_texts'])}):")
            for i, text in enumerate(results['response_texts'][-3:], 1):  # Show last 3
                preview = text[:100] + "..." if len(text) > 100 else text
                print(f"  {i}. {preview}")


# ============================================================================
# TEST SCENARIOS
# ============================================================================

def get_basic_command_scenarios() -> List[TestScenario]:
    """Basic command scenarios."""
    return [
        TestScenario(
            name="start_command",
            description="Test /start command",
            messages=["/start"],
            expected_keywords=["welcome", "language", "choose"],
        ),
        TestScenario(
            name="promises_command",
            description="Test /promises command",
            messages=["/start", "/promises"],
            expected_keywords=["promise", "list"],
        ),
        TestScenario(
            name="me_command",
            description="Test /me command",
            messages=["/start", "/me"],
            expected_keywords=["user", "settings"],
        ),
    ]


def get_task_creation_scenarios() -> List[TestScenario]:
    """Task and promise creation scenarios."""
    return [
        TestScenario(
            name="simple_task_creation",
            description="Create a simple task",
            messages=[
                "/start",
                "Add a task to exercise 30 minutes every day"
            ],
            expected_keywords=["task", "exercise", "created", "added"],
        ),
        TestScenario(
            name="complex_task_with_duration",
            description="Create a task with specific duration",
            messages=[
                "/start",
                "I want to read books for 2 hours per day"
            ],
            expected_keywords=["read", "book", "hour", "day"],
        ),
        TestScenario(
            name="weekly_commitment",
            description="Create a weekly commitment",
            messages=[
                "/start",
                "I promise to practice guitar 5 hours per week"
            ],
            expected_keywords=["guitar", "week", "promise"],
        ),
        TestScenario(
            name="multiple_tasks",
            description="Create multiple tasks in sequence",
            messages=[
                "/start",
                "Add task: meditate 20 minutes daily",
                "Also add: write in journal for 15 minutes every morning"
            ],
            expected_keywords=["meditate", "journal", "write"],
        ),
    ]


def get_reasoning_scenarios() -> List[TestScenario]:
    """Scenarios that test bot's reasoning capabilities."""
    return [
        TestScenario(
            name="contextual_followup",
            description="Test contextual understanding in follow-up",
            messages=[
                "/start",
                "I want to learn Spanish",
                "Make it 1 hour per day",
            ],
            expected_keywords=["spanish", "hour", "day"],
        ),
        TestScenario(
            name="ambiguous_request",
            description="Test handling of ambiguous requests",
            messages=[
                "/start",
                "I need to exercise more"
            ],
            expected_keywords=["exercise", "clarif", "how much", "often"],
        ),
        TestScenario(
            name="time_estimation",
            description="Test time estimation reasoning",
            messages=[
                "/start",
                "I want to read 3 books this month"
            ],
            expected_keywords=["book", "read", "time", "estimate"],
        ),
        TestScenario(
            name="priority_reasoning",
            description="Test priority and scheduling reasoning",
            messages=[
                "/start",
                "I have 3 tasks: exercise, study, and cook. Help me prioritize them for today"
            ],
            expected_keywords=["priorit", "task", "today", "schedule"],
        ),
        TestScenario(
            name="conflict_resolution",
            description="Test conflict detection and resolution",
            messages=[
                "/start",
                "I want to exercise 8 hours per day",
                "But I also need to work 8 hours and sleep 8 hours"
            ],
            expected_keywords=["conflict", "time", "impossible", "suggest"],
        ),
    ]


def get_conversation_scenarios() -> List[TestScenario]:
    """Multi-turn conversation scenarios."""
    return [
        TestScenario(
            name="conversation_flow",
            description="Natural conversation flow",
            messages=[
                "/start",
                "Hello, I'm new here",
                "I want to get healthier",
                "Can you help me create a fitness plan?",
                "I can exercise 1 hour per day"
            ],
            expected_keywords=["health", "fitness", "plan", "exercise"],
        ),
        TestScenario(
            name="modification_request",
            description="Modify existing task",
            messages=[
                "/start",
                "Add task: run 30 minutes daily",
                "Actually, make it 45 minutes instead"
            ],
            expected_keywords=["run", "minute", "updated", "changed"],
        ),
        TestScenario(
            name="question_answering",
            description="Answer questions about tasks",
            messages=[
                "/start",
                "Add task: study programming 2 hours daily",
                "How much time will I spend on this per week?",
            ],
            expected_keywords=["hour", "week", "time", "14"],
        ),
    ]


def get_edge_case_scenarios() -> List[TestScenario]:
    """Edge cases and error handling."""
    return [
        TestScenario(
            name="empty_message",
            description="Handle empty message",
            messages=["/start", ""],
            expected_keywords=[],
        ),
        TestScenario(
            name="very_long_message",
            description="Handle very long message",
            messages=[
                "/start",
                "I want to " + "do many things " * 50 + "every day"
            ],
            expected_keywords=[],
        ),
        TestScenario(
            name="special_characters",
            description="Handle special characters",
            messages=[
                "/start",
                "Add task: learn C++ & Python (2 hours/day)"
            ],
            expected_keywords=["learn", "python", "hour"],
        ),
        TestScenario(
            name="negative_time",
            description="Handle invalid time values",
            messages=[
                "/start",
                "I want to exercise -5 hours per day"
            ],
            expected_keywords=["invalid", "positive", "error"],
        ),
    ]


def get_confirmation_scenarios() -> List[TestScenario]:
    """Scenarios that test promise creation confirmation flows."""
    return [
        TestScenario(
            name="promise_creation_requires_confirmation",
            description="Direct promise creation should require confirmation",
            messages=[
                "/start",
                "I want to call a friend tomorrow"
            ],
            expected_keywords=["confirm", "promise", "call", "friend"],
            expected_behavior="Bot should ask for confirmation before creating the promise",
        ),
        TestScenario(
            name="promise_creation_confirmed",
            description="User confirms promise creation",
            messages=[
                "/start",
                "I want to call a friend tomorrow",
                "yes"
            ],
            expected_keywords=["created", "success", "promise"],
            expected_behavior="After confirmation, promise should be created and success message shown",
        ),
        TestScenario(
            name="promise_creation_canceled",
            description="User cancels promise creation",
            messages=[
                "/start",
                "I want to call a friend tomorrow",
                "no"
            ],
            expected_keywords=["cancel", "canceled"],
            expected_behavior="After cancellation, no promise should be created",
        ),
        TestScenario(
            name="template_subscription_requires_confirmation",
            description="Template subscription should require confirmation",
            messages=[
                "/start",
                "I want to go to gym 2 times this week"
            ],
            expected_keywords=["confirm", "template", "subscribe", "gym"],
            expected_behavior="Bot should ask for confirmation before subscribing to template",
        ),
        TestScenario(
            name="template_subscription_confirmed",
            description="User confirms template subscription",
            messages=[
                "/start",
                "I want to go to gym 2 times this week",
                "confirm"
            ],
            expected_keywords=["subscribed", "success", "template"],
            expected_behavior="After confirmation, template should be subscribed and success message shown",
        ),
        TestScenario(
            name="promise_creation_with_resolved_datetime",
            description="Promise creation with resolved datetime should still require confirmation",
            messages=[
                "/start",
                "I want to walk for twenty minutes tomorrow"
            ],
            expected_keywords=["confirm", "walk", "tomorrow"],
            expected_behavior="Even with resolved datetime, confirmation should be required",
        ),
    ]


def get_routing_scenarios() -> List[TestScenario]:
    """Scenarios that test routing and mode behaviors."""
    return [
        TestScenario(
            name="routing_engagement_mode",
            description="Casual chat should route to engagement mode",
            messages=[
                "/start",
                "tell me a joke"
            ],
            expected_keywords=["joke", "fun", "laugh"],
            expected_behavior="Should route to engagement mode and respond without tool calls",
        ),
        TestScenario(
            name="routing_operator_mode",
            description="Transactional action should route to operator mode",
            messages=[
                "/start",
                "log 2 hours on reading"
            ],
            expected_keywords=["logged", "reading", "hours"],
            expected_behavior="Should route to operator mode and execute tool calls",
        ),
        TestScenario(
            name="routing_strategist_mode",
            description="Coaching question should route to strategist mode",
            messages=[
                "/start",
                "what should I focus on this week?"
            ],
            expected_keywords=["focus", "goal", "week", "suggest"],
            expected_behavior="Should route to strategist mode and provide coaching/advice",
        ),
        TestScenario(
            name="routing_social_mode",
            description="Community query should route to social mode",
            messages=[
                "/start",
                "who follows me?"
            ],
            expected_keywords=["follow", "follower", "community"],
            expected_behavior="Should route to social mode and query social data",
        ),
        TestScenario(
            name="strategist_blocks_mutations",
            description="Strategist mode should block mutation tools",
            messages=[
                "/start",
                "how can I improve my productivity?",
                "create a promise to exercise daily"
            ],
            expected_keywords=["block", "operator", "mode", "switch"],
            expected_behavior="Strategist should block mutation and suggest switching to operator",
        ),
    ]


def get_all_scenarios() -> List[TestScenario]:
    """Get all test scenarios."""
    scenarios = []
    scenarios.extend(get_basic_command_scenarios())
    scenarios.extend(get_task_creation_scenarios())
    scenarios.extend(get_reasoning_scenarios())
    scenarios.extend(get_conversation_scenarios())
    scenarios.extend(get_edge_case_scenarios())
    scenarios.extend(get_confirmation_scenarios())
    scenarios.extend(get_routing_scenarios())
    return scenarios


# ============================================================================
# TEST RUNNER
# ============================================================================

async def run_all_scenarios(
    scenario_filter: Optional[List[str]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Run all test scenarios.
    
    Args:
        scenario_filter: Optional list of scenario names to run (if None, run all)
        verbose: Whether to print detailed results
    
    Returns:
        Summary of all test results
    """
    runner = ScenarioTestRunner()
    
    try:
        await runner.setup()
        
        all_scenarios = get_all_scenarios()
        
        # Filter scenarios if requested
        if scenario_filter:
            all_scenarios = [s for s in all_scenarios if s.name in scenario_filter]
        
        print("=" * 60)
        print(f"Running {len(all_scenarios)} Test Scenarios")
        print("=" * 60)
        
        results = []
        passed = 0
        failed = 0
        skipped = 0
        
        for scenario in all_scenarios:
            if verbose:
                print(f"\n▶ Running: {scenario.name} - {scenario.description}")
            
            result = await runner.run_scenario(scenario)
            results.append(result)
            
            if result.get('skipped'):
                skipped += 1
                if verbose:
                    print(f"⏭️  Skipped: {result.get('reason', 'No reason')}")
            elif result['passed']:
                passed += 1
                if verbose:
                    print(f"✅ Passed")
            else:
                failed += 1
                if verbose:
                    print(f"❌ Failed")
            
            if verbose:
                runner.print_results(result)
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total scenarios: {len(all_scenarios)}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⏭️  Skipped: {skipped}")
        print(f"Success rate: {(passed / (passed + failed) * 100):.1f}%" if (passed + failed) > 0 else "N/A")
        
        return {
            'total': len(all_scenarios),
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'results': results
        }
        
    finally:
        await runner.teardown()


async def run_single_scenario(scenario_name: str):
    """Run a single scenario by name."""
    all_scenarios = get_all_scenarios()
    scenario = next((s for s in all_scenarios if s.name == scenario_name), None)
    
    if not scenario:
        print(f"❌ Scenario '{scenario_name}' not found")
        print(f"Available scenarios: {[s.name for s in all_scenarios]}")
        return
    
    runner = ScenarioTestRunner()
    try:
        await runner.setup()
        result = await runner.run_scenario(scenario)
        runner.print_results(result)
    finally:
        await runner.teardown()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Run specific scenario
        scenario_name = sys.argv[1]
        asyncio.run(run_single_scenario(scenario_name))
    else:
        # Run all scenarios
        asyncio.run(run_all_scenarios())

