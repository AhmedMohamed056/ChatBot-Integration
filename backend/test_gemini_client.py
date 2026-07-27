"""
Standalone test for the Gemini client.

This test verifies that the GeminiClient works correctly.
"""

from dotenv import load_dotenv
import os
import sys

# Load environment variables
load_dotenv()

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gemini_client import (
    GeminiClient,
    GeminiClientError,
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiTimeoutError,
    GeminiNetworkError
)

def test_gemini_client():
    """
    Standalone test for the Gemini client.

    This test sends a simple request to verify the client works correctly.
    """
    print("Testing Gemini Client...")

    try:
        # Initialize client
        client = GeminiClient()

        # Send test request
        system_prompt = "You are a helpful assistant."
        user_prompt = "Say Hello"

        print(f"Sending request with system_prompt: '{system_prompt}'")
        print(f"Sending request with user_prompt: '{user_prompt}'")

        response = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        print(f"Response: '{response}'")

        # Verify response is not empty
        if not response:
            print("ERROR: Empty response received")
            return False

        # Verify response is a string
        if not isinstance(response, str):
            print(f"ERROR: Response is not a string, got {type(response)}")
            return False

        print("✓ Test passed! Gemini client is working correctly.")
        return True

    except GeminiAuthenticationError as e:
        print(f"✗ Authentication error: {e}")
        return False
    except GeminiRateLimitError as e:
        print(f"✗ Rate limit error: {e}")
        return False
    except GeminiTimeoutError as e:
        print(f"✗ Timeout error: {e}")
        return False
    except GeminiNetworkError as e:
        print(f"✗ Network error: {e}")
        return False
    except GeminiResponseError as e:
        print(f"✗ Response error: {e}")
        return False
    except GeminiClientError as e:
        print(f"✗ Client error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    # Run the test when executed directly
    success = test_gemini_client()
    exit(0 if success else 1)