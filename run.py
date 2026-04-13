#!/usr/bin/env python3
"""
VD-Flow Startup Script
Lightweight AI Agent Framework with Memory and Skills
"""

import logging
import sys

import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for VD-Flow"""
    # Load environment variables from .env file BEFORE anything else
    from dotenv import load_dotenv

    load_dotenv()

    logger.info("=" * 60)
    logger.info("Starting VD-Flow - Lightweight AI Agent Framework")
    logger.info("=" * 60)

    try:
        # Load configuration
        from vdflow.config import Config

        config = Config.from_yaml("config.yaml")
        logger.info(f"✓ Loaded configuration from config.yaml")
        available = config.available_models
        skipped = len(config.models) - len(available)
        logger.info(f"  - Models available: {len(available)} (skipped {skipped} without valid API keys)")
        logger.info(f"  - Memory enabled: {config.memory.enabled}")
        logger.info(f"  - Skills path: {config.skills.path}")

        # Display available models
        if available:
            logger.info("\nAvailable Models:")
            for model in available:
                logger.info(f"  ✅ {model.display_name} ({model.name})")
        else:
            logger.warning("⚠ No models with valid API keys! Please check your .env file")

        # Start server
        logger.info(f"\n🌐 Starting web server...")
        logger.info(f"  - Host: {config.server.host}")
        logger.info(f"  - Port: {config.server.port}")
        logger.info(f"  - URL: http://{config.server.host}:{config.server.port}")
        logger.info("\nPress Ctrl+C to stop the server\n")

        uvicorn.run(
            "vdflow.web.app:app",
            host=config.server.host,
            port=config.server.port,
            reload=config.server.reload,
            log_level="info",
        )

    except FileNotFoundError:
        logger.error("❌ Configuration file 'config.yaml' not found!")
        logger.info("Please copy config.yaml and configure your API keys.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start VD-Flow: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
