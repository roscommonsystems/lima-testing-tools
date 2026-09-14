"""
LIMA Authentication Module for Testing Suite

Obtains the API keys the suite needs (notably OPEN_ROUTER_API_KEY, used for vision
verification) by reusing the tester's existing LIMA sign-in, so no browser prompt or
separate credentials are required.

Prerequisites (see lima_config.json.example):
    * The tester must be signed into LIMA once beforehand.
    * Provide the Firebase Web API key via the LIMA_FIREBASE_API_KEY environment variable,
      or a gitignored secret_config.py exposing FIREBASE_API_KEY. It is kept out of source
      control.
    * lima_config.json holds the auth server URL (auth_url).

The public interface (LimaAuth.validate_license() -> dict with an 'api_keys' entry) is
kept stable, so the rest of the suite is unaffected.
"""

import json
import os
import logging
from typing import Optional, Dict, Any

import requests
from time import sleep

# Session storage location and the token-refresh endpoint.
KEYRING_SERVICE = "LIMA"
KEYRING_USERNAME = "firebase_refresh_token"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"


class LimaAuth:
    """Retrieves API keys for the suite by reusing the tester's existing LIMA sign-in."""

    DEFAULT_CONFIG_PATH = "lima_config.json"

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._api_keys: Dict[str, str] = {}
        self._config: Dict[str, Any] = {}

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}\n"
                f"Create it with the auth server URL. See lima_config.json.example."
            )
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _firebase_api_key(self) -> Optional[str]:
        """Firebase Web API key used to refresh the session. Kept out of the repo and
        sourced either way:

          1. the LIMA_FIREBASE_API_KEY environment variable, or
          2. a gitignored secret_config.py on the path exposing FIREBASE_API_KEY.
        """
        env_key = os.environ.get("LIMA_FIREBASE_API_KEY", "").strip()
        if env_key:
            return env_key
        try:
            import secret_config  # gitignored; present in a LIMA dev checkout
            return (getattr(secret_config, "FIREBASE_API_KEY", "") or "").strip() or None
        except Exception:
            return None

    def _load_refresh_token(self) -> Optional[str]:
        """Read the stored LIMA session token."""
        try:
            import keyring
        except Exception as e:
            logging.error("! keyring package unavailable, cannot read LIMA session: %s", e)
            return None
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception as e:
            logging.error("! Failed to read LIMA session from keyring: %s", e)
            return None

    def _refresh_id_token(self, refresh_token: str, api_key: str) -> Optional[str]:
        """Exchange the stored refresh token for a fresh 1-hour Firebase ID token."""
        try:
            resp = requests.post(
                SECURE_TOKEN_URL + "?key=" + api_key,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                timeout=20,
            )
            data = resp.json() if resp.content else {}
        except Exception as e:
            logging.error("! LIMA session refresh request failed: %s", e)
            return None
        if resp.status_code != 200:
            logging.error("! LIMA session refresh failed (HTTP %s): %s",
                          resp.status_code, data.get("error"))
            return None
        return data.get("id_token")

    def validate_license(self, max_retries: int = 4) -> Dict[str, Any]:
        """Authenticate and return license_info with api_keys.

        Name and return shape kept for compatibility with the rest of the suite.
        """
        try:
            self._config = self._load_config()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return {'valid': False, 'error': str(e)}

        auth_url = self._config.get('auth_url')
        if not auth_url:
            return {'valid': False, 'error': 'auth_url not found in config file'}

        refresh_token = self._load_refresh_token()
        if not refresh_token:
            return {'valid': False, 'error':
                    'No LIMA sign-in session found. Sign into LIMA first, then re-run.'}

        api_key = self._firebase_api_key()
        if not api_key:
            return {'valid': False, 'error':
                    'LIMA_FIREBASE_API_KEY is not set. Set it to the Firebase Web API key '
                    'so the stored LIMA session can be refreshed.'}

        id_token = self._refresh_id_token(refresh_token, api_key)
        if not id_token:
            return {'valid': False, 'error':
                    'Could not refresh the LIMA session (it may be expired or revoked). '
                    'Open LIMA, sign in again, then re-run.'}

        headers = {
            'Authorization': 'Bearer ' + id_token,
            'User-Agent': 'LIMA-Regression-Tests',
        }

        retry_delay = 1
        max_retry_delay = 30

        for attempt in range(max_retries):
            try:
                response = requests.post(auth_url, headers=headers, json={}, timeout=20)

                try:
                    data = response.json() if response.content else {}
                except ValueError as e:
                    if attempt == max_retries - 1:
                        return {'valid': False, 'error': f'Invalid JSON response: {str(e)}'}
                    raise ValueError(f"Invalid JSON response: {str(e)}")

                if response.status_code == 200:
                    if not response.content:
                        return {}

                    license_info = data.get('license_info', {})
                    api_keys = {
                        'OPEN_ROUTER_API_KEY': data.get('OPEN_ROUTER_API_KEY'),
                        'LIMA_AI_SERVER_KEY': data.get('LIMA_AI_SERVER_KEY'),
                        'TAVILY_API_KEY': data.get('TAVILY_API_KEY'),
                    }
                    if 'valid' not in license_info:
                        license_info['valid'] = True
                    license_info['api_keys'] = api_keys
                    self._api_keys = api_keys
                    return license_info

                elif response.status_code in (400, 401, 403, 422):
                    error_msg = data.get('error') or data.get('message') or 'Authentication failed'
                    return {'valid': False, 'error': error_msg}
                else:
                    logging.error("Auth server error: HTTP %s", response.status_code)
                    raise requests.RequestException(f"Unexpected status: {response.status_code}")

            except requests.RequestException as e:
                logging.debug("Auth attempt %s failed: %s", attempt + 1, str(e))
                if attempt == max_retries - 1:
                    return {'valid': False, 'error': str(e)}
                sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

            except ValueError as e:
                logging.debug("JSON error attempt %s: %s", attempt + 1, str(e))
                if attempt == max_retries - 1:
                    return {'valid': False, 'error': str(e)}
                sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

        return {'valid': False, 'error': 'Connection timed out'}

    def get_api_key(self, key_name: str) -> Optional[str]:
        """Get a specific API key by name (e.g. 'OPEN_ROUTER_API_KEY')."""
        return self._api_keys.get(key_name)

    def get_all_api_keys(self) -> Dict[str, str]:
        """Get all retrieved API keys."""
        return self._api_keys.copy()


# Convenience function for backward compatibility
def validate_license(max_retries: int = 4) -> Dict[str, Any]:
    """Authenticate and return license_info with api_keys (convenience wrapper)."""
    auth = LimaAuth()
    return auth.validate_license(max_retries)
