#!/usr/bin/env python3
"""Test script to verify VD-Flow installation"""

import sys


def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")

    try:
        import vdflow

        print("✓ vdflow")
    except ImportError as e:
        print(f"✗ vdflow: {e}")
        return False

    try:
        from vdflow.config import Config

        print("✓ vdflow.config")
    except ImportError as e:
        print(f"✗ vdflow.config: {e}")
        return False

    try:
        from vdflow.agent import create_agent, ThreadState

        print("✓ vdflow.agent")
    except ImportError as e:
        print(f"✗ vdflow.agent: {e}")
        return False

    try:
        from vdflow.memory import MemoryStorage

        print("✓ vdflow.memory")
    except ImportError as e:
        print(f"✗ vdflow.memory: {e}")
        return False

    try:
        from vdflow.skills import SkillsLoader

        print("✓ vdflow.skills")
    except ImportError as e:
        print(f"✗ vdflow.skills: {e}")
        return False

    try:
        from vdflow.tools import get_builtin_tools

        print("✓ vdflow.tools")
    except ImportError as e:
        print(f"✗ vdflow.tools: {e}")
        return False

    try:
        from vdflow.web import app

        print("✓ vdflow.web")
    except ImportError as e:
        print(f"✗ vdflow.web: {e}")
        return False

    return True


def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")

    try:
        from vdflow.config import Config

        config = Config.from_yaml("config.yaml")
        print(f"✓ Loaded configuration with {len(config.models)} models")

        if config.models:
            print(f"✓ Default model: {config.models[0].name}")
        else:
            print("⚠ No models configured")

        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def test_memory():
    """Test memory storage"""
    print("\nTesting memory system...")

    try:
        from vdflow.config import Config
        from vdflow.memory import MemoryStorage

        config = Config.from_yaml("config.yaml")
        storage = MemoryStorage(config.memory)

        # Test load
        memory = storage.load()
        print("✓ Memory loaded successfully")

        # Test save
        memory["test_key"] = "test_value"
        storage.save(memory)
        print("✓ Memory saved successfully")

        # Test load again
        memory2 = storage.load()
        assert memory2.get("test_key") == "test_value"
        print("✓ Memory persistence verified")

        # Cleanup
        del memory2["test_key"]
        storage.save(memory2)

        return True
    except Exception as e:
        print(f"✗ Memory test failed: {e}")
        return False


def test_skills():
    """Test skills loader"""
    print("\nTesting skills system...")

    try:
        from vdflow.config import Config
        from vdflow.skills import SkillsLoader

        config = Config.from_yaml("config.yaml")
        loader = SkillsLoader(config.skills.path, config.skills.enabled_by_default)

        skills = loader.load_skills()
        print(f"✓ Loaded {len(skills)} skills")

        for skill_name, skill in skills.items():
            print(f"  - {skill_name}: {'enabled' if skill.enabled else 'disabled'}")

        return True
    except Exception as e:
        print(f"✗ Skills test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("VD-Flow Installation Test")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("Memory", test_memory()))
    results.append(("Skills", test_skills()))

    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 All tests passed! VD-Flow is ready to use.")
        print("\nNext steps:")
        print("1. Set your API key: export OPENAI_API_KEY=your-key")
        print("2. Run the server: python run.py")
        print("3. Open http://localhost:8000 in your browser")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
