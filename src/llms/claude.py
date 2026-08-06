from anthropic import Anthropic
from anthropic import RateLimitError, APITimeoutError, APIConnectionError
import time
import os
from typing import Tuple, List, Dict
from logger import get_logger

# API model IDs are sourced from the registry (single source of truth).
from .model_registry import get_model_info

_SONNET_MODEL_ID = get_model_info("claude-3.5-sonnet").api_model_id
_HAIKU_MODEL_ID = get_model_info("claude-3.5-haiku").api_model_id
_OPUS_MODEL_ID = get_model_info("claude-3-opus").api_model_id


def calculate_cost(response, model_name):
    """Calculate the cost of an Anthropic Claude API call from the unified registry."""
    from .cost_calculator import calculate_cost_anthropic
    return calculate_cost_anthropic(response, model_name)


def claude_3_5_sonnet(messages: List[Dict], temperature: float = 0.3) -> Tuple[str, float]:
    """
    Call Anthropic Claude-3.5-Sonnet with retry logic and error handling.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content'
        temperature: Sampling temperature (0.0 to 1.0)
        
    Returns:
        Tuple of (Generated text response, Cost in USD)
        
    Raises:
        Exception: If all retry attempts fail
    """
    max_retries = 3
    logger = get_logger()
    last_error = None
    
    for attempt in range(max_retries):
        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            # Convert OpenAI format messages to Claude format
            system_message = None
            user_messages = []
            
            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                elif msg['role'] in ['user', 'assistant']:
                    user_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
            
            # Create the API call
            kwargs = {
                "model": _SONNET_MODEL_ID,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": 4096,
                "timeout": 60
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            response = client.messages.create(**kwargs)
            
            # Calculate cost (logical model name — registry key)
            cost = calculate_cost(response, "claude-3.5-sonnet")
            if logger:
                logger.info(f"LLM call succeeded (attempt {attempt + 1}/{max_retries})")
                logger.llm_call("claude-3.5-sonnet", cost, response.usage.input_tokens + response.usage.output_tokens)
            else:
                print(f"[llm] LLM call succeeded (attempt {attempt + 1}/{max_retries})")

            return response.content[0].text, cost
            
        except RateLimitError as e:
            last_error = e
            if logger:
                logger.error(f"Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            
        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            if logger:
                logger.error(f"Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            if logger:
                logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {error_type}: {e}")
            else:
                print(f"[llm] Unexpected error (attempt {attempt + 1}/{max_retries}): {error_type}: {e}")

        if attempt < max_retries - 1:
            if logger:
                logger.info(f"Retrying in 1 seconds...")
            else:
                print(f"[llm] Retrying in 1 seconds...")
            time.sleep(1)
        else:
            error_msg = f"Claude API call failed after {max_retries} attempts. Last error: {type(last_error).__name__}: {last_error}"
            if logger:
                logger.error(f"All {max_retries} attempts failed")
                logger.error(error_msg)
            else:
                print(f"[llm] All {max_retries} attempts failed")
            raise Exception(error_msg)


def claude_3_5_haiku(messages: List[Dict], temperature: float = 0.3) -> Tuple[str, float]:
    """
    Call Anthropic Claude-3.5-Haiku with retry logic and error handling.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content'
        temperature: Sampling temperature (0.0 to 1.0)
        
    Returns:
        Tuple of (Generated text response, Cost in USD)
        
    Raises:
        Exception: If all retry attempts fail
    """
    max_retries = 3
    logger = get_logger()
    last_error = None
    
    for attempt in range(max_retries):
        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            # Convert OpenAI format messages to Claude format
            system_message = None
            user_messages = []
            
            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                elif msg['role'] in ['user', 'assistant']:
                    user_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
            
            # Create the API call
            kwargs = {
                "model": _HAIKU_MODEL_ID,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": 4096,
                "timeout": 60
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            response = client.messages.create(**kwargs)
            
            # Calculate cost (logical model name — registry key)
            cost = calculate_cost(response, "claude-3.5-haiku")
            if logger:
                logger.info(f"LLM call succeeded (attempt {attempt + 1}/{max_retries})")
                logger.llm_call("claude-3.5-haiku", cost, response.usage.input_tokens + response.usage.output_tokens)
            else:
                print(f"[llm] LLM call succeeded (attempt {attempt + 1}/{max_retries})")

            return response.content[0].text, cost
            
        except RateLimitError as e:
            last_error = e
            if logger:
                logger.error(f"Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            
        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            if logger:
                logger.error(f"Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            if logger:
                logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            if logger:
                logger.info(f"Retrying in 1 seconds...")
            else:
                print(f"[llm] Retrying in 1 seconds...")
            time.sleep(1)
        else:
            error_msg = f"Claude API call failed after {max_retries} attempts. Last error: {type(last_error).__name__}: {last_error}"
            if logger:
                logger.error(f"All {max_retries} attempts failed")
                logger.error(error_msg)
            else:
                print(f"[llm] All {max_retries} attempts failed")
            raise Exception(error_msg)


def claude_3_opus(messages: List[Dict], temperature: float = 0.3) -> Tuple[str, float]:
    """
    Call Anthropic Claude-3-Opus with retry logic and error handling.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content'
        temperature: Sampling temperature (0.0 to 1.0)
        
    Returns:
        Tuple of (Generated text response, Cost in USD)
        
    Raises:
        Exception: If all retry attempts fail
    """
    max_retries = 3
    logger = get_logger()
    last_error = None
    
    for attempt in range(max_retries):
        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            # Convert OpenAI format messages to Claude format
            system_message = None
            user_messages = []
            
            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                elif msg['role'] in ['user', 'assistant']:
                    user_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
            
            # Create the API call
            kwargs = {
                "model": _OPUS_MODEL_ID,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": 4096,
                "timeout": 60
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            response = client.messages.create(**kwargs)
            
            # Calculate cost (logical model name — registry key)
            cost = calculate_cost(response, "claude-3-opus")
            if logger:
                logger.info(f"LLM call succeeded (attempt {attempt + 1}/{max_retries})")
                logger.llm_call("claude-3-opus", cost, response.usage.input_tokens + response.usage.output_tokens)
            else:
                print(f"[llm] LLM call succeeded (attempt {attempt + 1}/{max_retries})")

            return response.content[0].text, cost
            
        except RateLimitError as e:
            last_error = e
            if logger:
                logger.error(f"Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {e}")
            
        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            if logger:
                logger.error(f"Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Connection/timeout error (attempt {attempt + 1}/{max_retries}): {e}")
            
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            if logger:
                logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                print(f"[llm] Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            if logger:
                logger.info(f"Retrying in 1 seconds...")
            else:
                print(f"[llm] Retrying in 1 seconds...")
            time.sleep(1)
        else:
            error_msg = f"Claude API call failed after {max_retries} attempts. Last error: {type(last_error).__name__}: {last_error}"
            if logger:
                logger.error(f"All {max_retries} attempts failed")
                logger.error(error_msg)
            else:
                print(f"[llm] All {max_retries} attempts failed")
            raise Exception(error_msg)

