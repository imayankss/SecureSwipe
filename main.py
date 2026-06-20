"""Project entry point for the Credit Card Fraud Detection & Risk Scoring System.

On Day 1, this script only verifies that the project is set up correctly:
it loads the configuration file, initializes the logger, and prints basic
project information. It does not load data or train models.
"""

from typing import Any, Dict

from src.utils.config import get_config_value, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> Dict[str, Any]:
    """Run the project initialization check.

    Loads the project configuration, logs basic startup information, and
    prints the project name, version, and a success message.

    Returns:
        The loaded configuration dictionary, for programmatic use (e.g. tests).
    """
    logger.info("Starting project initialization check.")

    config = load_config()

    project_name = get_config_value(config, "project.name", default="Unknown Project")
    project_version = get_config_value(config, "project.version", default="0.0.0")

    print(f"Project Name: {project_name}")
    print(f"Project Version: {project_version}")
    print("Project initialized successfully.")

    logger.info("Project initialization check completed successfully.")

    return config


if __name__ == "__main__":
    main()