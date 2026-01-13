#!/usr/bin/env python3
"""
Quick script to run scenario tests with various options.

Usage:
    python -m tm_bot.platforms.testing.run_scenarios                    # Run all
    python -m tm_bot.platforms.testing.run_scenarios --category reasoning # Run category
    python -m tm_bot.platforms.testing.run_scenarios --scenario simple_task_creation  # Run one
    python -m tm_bot.platforms.testing.run_scenarios --list              # List all
"""

import asyncio
import sys
import argparse
from typing import List

from .scenario_tests import (
    run_all_scenarios,
    run_single_scenario,
    get_all_scenarios,
    get_basic_command_scenarios,
    get_task_creation_scenarios,
    get_reasoning_scenarios,
    get_conversation_scenarios,
    get_edge_case_scenarios,
    ScenarioTestRunner,
)


def list_scenarios():
    """List all available scenarios."""
    print("=" * 60)
    print("Available Test Scenarios")
    print("=" * 60)
    
    categories = {
        "Basic Commands": get_basic_command_scenarios(),
        "Task Creation": get_task_creation_scenarios(),
        "Reasoning": get_reasoning_scenarios(),
        "Conversations": get_conversation_scenarios(),
        "Edge Cases": get_edge_case_scenarios(),
    }
    
    for category, scenarios in categories.items():
        print(f"\n{category} ({len(scenarios)} scenarios):")
        for scenario in scenarios:
            skip_marker = " [SKIP]" if scenario.skip_reason else ""
            print(f"  • {scenario.name}{skip_marker}")
            print(f"    {scenario.description}")
            if scenario.expected_keywords:
                print(f"    Expected keywords: {', '.join(scenario.expected_keywords)}")


async def run_category(category: str):
    """Run scenarios from a specific category."""
    category_map = {
        "basic": get_basic_command_scenarios(),
        "commands": get_basic_command_scenarios(),
        "task": get_task_creation_scenarios(),
        "tasks": get_task_creation_scenarios(),
        "creation": get_task_creation_scenarios(),
        "reasoning": get_reasoning_scenarios(),
        "reason": get_reasoning_scenarios(),
        "conversation": get_conversation_scenarios(),
        "conversations": get_conversation_scenarios(),
        "edge": get_edge_case_scenarios(),
        "edgecase": get_edge_case_scenarios(),
        "edgecases": get_edge_case_scenarios(),
    }
    
    category_lower = category.lower()
    if category_lower not in category_map:
        print(f"❌ Unknown category: {category}")
        print(f"Available categories: {', '.join(set(cat.split('_')[0] for cat in category_map.keys()))}")
        return
    
    scenarios = category_map[category_lower]
    print(f"Running {len(scenarios)} scenarios from category: {category}")
    
    runner = ScenarioTestRunner()
    
    try:
        await runner.setup()
        
        passed = 0
        failed = 0
        
        for scenario in scenarios:
            result = await runner.run_scenario(scenario)
            if result.get('skipped'):
                print(f"⏭️  {scenario.name}: Skipped")
            elif result['passed']:
                print(f"✅ {scenario.name}: Passed")
                passed += 1
            else:
                print(f"❌ {scenario.name}: Failed")
                failed += 1
                runner.print_results(result)
        
        print(f"\nSummary: {passed} passed, {failed} failed")
        
    finally:
        await runner.teardown()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run automated scenario tests for Xaana AI bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all scenarios
  python -m tm_bot.platforms.testing.run_scenarios

  # Run a specific scenario
  python -m tm_bot.platforms.testing.run_scenarios --scenario simple_task_creation

  # Run scenarios from a category
  python -m tm_bot.platforms.testing.run_scenarios --category reasoning

  # List all scenarios
  python -m tm_bot.platforms.testing.run_scenarios --list
        """
    )
    
    parser.add_argument(
        '--scenario', '-s',
        help='Run a specific scenario by name'
    )
    
    parser.add_argument(
        '--category', '-c',
        help='Run scenarios from a category (basic, task, reasoning, conversation, edge)'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all available scenarios'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=True,
        help='Show detailed output (default: True)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Show minimal output'
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_scenarios()
        return
    
    if args.scenario:
        asyncio.run(run_single_scenario(args.scenario))
    elif args.category:
        asyncio.run(run_category(args.category))
    else:
        verbose = args.verbose and not args.quiet
        results = asyncio.run(run_all_scenarios(verbose=verbose))
        
        # Exit with error code if tests failed
        if results['failed'] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()

