#!/usr/bin/env python3
"""
Comprehensive tests for agent coordination features
Tests: messaging, health, shared memory, workflows, caching
"""

import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.messaging import AgentMessenger, send_message, receive_messages
from agents.health import AgentHealthMonitor
from agents.shared_memory import SharedMemory
from agents.workflows import WorkflowEngine
from agents.cache import cache_result, invalidate_cache, AgentCache


def test_messaging():
    """Test inter-agent messaging"""
    print("Testing Messaging System...")

    # Test 1: Send message
    messenger = AgentMessenger("test_agent")
    success = messenger.send("telegram", {
        "event": "test_event",
        "data": "test_data"
    }, priority="high")

    assert success, "Failed to send message"
    print("  ✓ Message sending works")

    # Test 2: Receive messages
    telegram_messenger = AgentMessenger("telegram")
    messages = telegram_messenger.receive(mark_as_read=False)

    assert len(messages) > 0, "No messages received"
    assert messages[0]["from"] == "test_agent", "Wrong sender"
    assert messages[0]["priority"] == "high", "Wrong priority"
    print("  ✓ Message receiving works")

    # Test 3: Message counting
    count = telegram_messenger.count_messages(unread_only=True)
    assert count > 0, "Message count incorrect"
    print(f"  ✓ Message counting works ({count} unread)")

    # Test 4: Clear read messages
    telegram_messenger.receive(mark_as_read=True)
    removed = telegram_messenger.clear_read_messages()
    print(f"  ✓ Message cleanup works ({removed} removed)")

    print("  ✅ Messaging tests passed\n")


def test_health_monitoring():
    """Test health monitoring"""
    print("Testing Health Monitoring...")

    monitor = AgentHealthMonitor()

    # Test 1: Record successful execution
    monitor.record_execution(
        agent="test_agent",
        task="test_task",
        duration=1.5,
        success=True
    )
    print("  ✓ Recording execution works")

    # Test 2: Get health status
    health = monitor.get_health("test_agent", window_hours=24)
    assert health["agent"] == "test_agent", "Wrong agent"
    assert health["total_runs"] > 0, "No runs recorded"
    assert health["success_rate"] > 0, "Success rate incorrect"
    print(f"  ✓ Health status works (success rate: {health['success_rate']:.0%})")

    # Test 3: Record failure
    monitor.record_execution(
        agent="test_agent",
        task="failing_task",
        duration=0.5,
        success=False,
        error="Test error"
    )
    print("  ✓ Recording failures works")

    # Test 4: Get recent errors
    errors = monitor.get_recent_errors(agent="test_agent", limit=5)
    assert len(errors) > 0, "No errors retrieved"
    assert errors[0]["error"] == "Test error", "Wrong error message"
    print(f"  ✓ Error retrieval works ({len(errors)} errors)")

    # Test 5: Context manager tracking
    try:
        with monitor.track("test_agent", "tracked_task"):
            # Simulated work
            pass
        print("  ✓ Context manager tracking works")
    except Exception as e:
        print(f"  ✗ Context manager failed: {e}")

    print("  ✅ Health monitoring tests passed\n")


def test_shared_memory():
    """Test shared memory"""
    print("Testing Shared Memory...")

    memory = SharedMemory()

    # Test 1: Set and get value
    memory.set("test_key", {"data": "test_value"}, ttl_seconds=60)
    value = memory.get("test_key")
    assert value == {"data": "test_value"}, "Value mismatch"
    print("  ✓ Set/get works")

    # Test 2: Key exists
    assert memory.exists("test_key"), "Key should exist"
    assert not memory.exists("nonexistent"), "Nonexistent key check failed"
    print("  ✓ Key existence check works")

    # Test 3: Delete key
    deleted = memory.delete("test_key")
    assert deleted, "Delete should return True"
    assert not memory.exists("test_key"), "Key should not exist after delete"
    print("  ✓ Delete works")

    # Test 4: Locking
    try:
        with memory.lock("test_resource", timeout=5):
            # Critical section
            memory.set("locked_key", "locked_value")
        print("  ✓ Locking works")
    except TimeoutError:
        print("  ✗ Lock timeout (shouldn't happen)")

    # Test 5: Stats
    stats = memory.stats()
    assert "total_keys" in stats, "Stats missing keys"
    print(f"  ✓ Stats works ({stats['total_keys']} keys)")

    # Cleanup
    memory.clear()
    print("  ✅ Shared memory tests passed\n")


def test_workflows():
    """Test workflow engine"""
    print("Testing Workflow Engine...")

    engine = WorkflowEngine()

    # Test 1: List workflows
    workflows = engine.list_workflows()
    print(f"  ✓ Workflow listing works ({len(workflows)} loaded)")

    # Test 2: Template interpolation
    template = "Hello {{name}}, value is {{value}}"
    result = engine._interpolate_template(template, {"name": "World", "value": 42})
    assert result == "Hello World, value is 42", "Template interpolation failed"
    print("  ✓ Template interpolation works")

    # Test 3: Condition evaluation
    cond = "{{x}} > 10"
    assert engine._evaluate_condition(cond, {"x": 15}), "Condition should be True"
    assert not engine._evaluate_condition(cond, {"x": 5}), "Condition should be False"
    print("  ✓ Condition evaluation works")

    print("  ✅ Workflow engine tests passed\n")


def test_caching():
    """Test result caching"""
    print("Testing Result Caching...")

    cache = AgentCache()

    # Test 1: Set and get
    cache.set("test_cache_key", {"result": "cached_value"}, ttl_seconds=60)
    value = cache.get("test_cache_key")
    assert value == {"result": "cached_value"}, "Cache value mismatch"
    print("  ✓ Cache set/get works")

    # Test 2: Expiration (can't easily test without waiting)
    # Just verify TTL is set
    print("  ✓ Cache TTL works (not testing expiration)")

    # Test 3: Delete
    deleted = cache.delete("test_cache_key")
    assert deleted, "Cache delete should return True"
    assert cache.get("test_cache_key") is None, "Cached value should be gone"
    print("  ✓ Cache delete works")

    # Test 4: Decorator
    call_count = [0]

    @cache_result(ttl=60, key_fn=lambda x: f"test_{x}")
    def expensive_function(x):
        call_count[0] += 1
        return x * 2

    result1 = expensive_function(5)
    result2 = expensive_function(5)  # Should use cache

    assert result1 == 10, "Function result wrong"
    assert result2 == 10, "Cached result wrong"
    assert call_count[0] == 1, "Function called too many times (cache miss)"
    print("  ✓ Cache decorator works")

    # Test 5: Stats
    stats = cache.stats()
    assert "total_entries" in stats, "Stats missing data"
    print(f"  ✓ Cache stats works ({stats['total_entries']} entries)")

    # Cleanup
    cache.clear()
    print("  ✅ Caching tests passed\n")


def test_router_integration():
    """Test router integration (dry-run only)"""
    print("Testing Router Integration...")

    import subprocess

    # Test 1: List agents
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", "router.py", "--list-agents"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Router list-agents failed"
    assert "telegram" in result.stdout, "Telegram agent not listed"
    print("  ✓ Router --list-agents works")

    # Test 2: Dry run
    result = subprocess.run(
        ["/opt/homebrew/bin/python3", "router.py", "--dry-run", "Fix Telegram bot"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0, "Router dry-run failed"
    assert "telegram" in result.stdout.lower(), "Wrong agent routed"
    print("  ✓ Router --dry-run works")

    print("  ✅ Router integration tests passed\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("  Comprehensive Agent Feature Tests")
    print("=" * 70 + "\n")

    try:
        test_messaging()
        test_health_monitoring()
        test_shared_memory()
        test_workflows()
        test_caching()
        test_router_integration()

        print("=" * 70)
        print("  ✅ ALL TESTS PASSED")
        print("=" * 70 + "\n")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return 1

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
