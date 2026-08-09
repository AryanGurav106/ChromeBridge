import json
import re
from core.utils.logger import Logger
logger = Logger()

def escape_js_message(message: str) -> str:
    """Properly escape message for JavaScript while preserving formatting"""
    if not isinstance(message, str):
        message = str(message)
        
    # Convert newlines to actual line breaks for HTML
    message = message.replace('\n', '<br>')
    
    # Escape quotes and wrap in quotes
    message = message.replace('"', '\\"')
    return f'"{message}"'


def beautify_plan_message(message:str) -> str:
    """
    Add a newline between each numbered step in the plan message if it does not already exist.

    Args:
        message (str): The plan message.

    Returns:
        str: The plan message with newlines added between each numbered step.
    """
    logger.debug(f"beautify_plan_message original:\n{message}")
    # Add a newline before each numbered step that is not already preceded by a newline
    plan_with_newlines = re.sub(r'(?<!\n)( \d+\.)', r'\n\1', message)
    logger.debug(f"beautify_plan_message modified:\n{plan_with_newlines}")
    return plan_with_newlines