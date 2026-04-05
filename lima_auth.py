"""
LIMA Authentication Module for Testing Suite

This module provides minimal authentication functionality for the regression test suite.
It reads configuration from a user-provided config file and validates license keys
against the LIMA authentication server.
"""

import json
import os
import logging
from typing import Optional, Dict, Any

import requests
from time import sleep


class LimaAuth:
    """Handles license validation and API key retrieval for LIMA testing."""
    
    DEFAULT_CONFIG_PATH = "lima_config.json"
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the authentication module.
        
        Args:
            config_path: Path to config file (default: lima_config.json)
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._api_keys: Dict[str, str] = {}
        self._config: Dict[str, Any] = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from JSON file.
        
        Returns:
            Dict containing configuration values
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is invalid JSON
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}\n"
                f"Please create {self.config_path} with your authentication server URL and license key.\n"
                f"See lima_config.json.example for the expected format."
            )
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def validate_license(self, max_retries: int = 4) -> Dict[str, Any]:
        """
        Validate the license key against the authentication server.
        
        Args:
            max_retries: Maximum number of retry attempts for transient failures
            
        Returns:
            Dict containing validation result and API keys if successful
        """
        # Load config
        try:
            self._config = self._load_config()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return {'valid': False, 'error': str(e)}
        
        # Get license key from config
        license_key = self._config.get('license_key')
        if not license_key or not isinstance(license_key, str) or len(license_key.strip()) == 0:
            return {'valid': False, 'error': 'license_key not found in config file or is empty'}
        
        # Get auth URL from config
        auth_url = self._config.get('auth_url')
        if not auth_url:
            return {'valid': False, 'error': 'auth_url not found in config file'}
        
        payload = {'license_key': license_key.strip()}
        
        retry_delay = 1
        max_retry_delay = 30
        
        for attempt in range(max_retries):
            try:
                response = requests.post(auth_url, json=payload, timeout=20)
                
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
                        'GROQ_API_KEY': data.get('GROQ_API_KEY'),
                        'OPEN_ROUTER_API_KEY': data.get('OPEN_ROUTER_API_KEY'),
                        'CHIRP_API_KEY': data.get('CHIRP_API_KEY')
                    }
                    
                    if 'valid' not in license_info:
                        license_info['valid'] = True
                    
                    license_info['api_keys'] = api_keys
                    self._api_keys = api_keys
                    
                    return license_info
                    
                elif response.status_code in (400, 401, 422):
                    error_msg = data.get('message', 'Validation failed')
                    if 'error' in data:
                        error_msg = data['error']
                    return {'valid': False, 'error': error_msg}
                else:
                    logging.error(f"License validation failed: HTTP {response.status_code}")
                    raise requests.RequestException(f"Unexpected status: {response.status_code}")
                    
            except requests.RequestException as e:
                logging.debug(f"License validation attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return {'valid': False, 'error': str(e)}
                logging.debug(f"Retrying in {retry_delay} seconds")
                sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                
            except ValueError as e:
                logging.debug(f"JSON error attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    return {'valid': False, 'error': str(e)}
                sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
        
        return {'valid': False, 'error': 'Connection timed out'}
    
    def get_api_key(self, key_name: str) -> Optional[str]:
        """
        Get a specific API key by name.
        
        Args:
            key_name: Name of the API key (e.g., 'OPEN_ROUTER_API_KEY')
            
        Returns:
            str: The API key if available, None otherwise
        """
        return self._api_keys.get(key_name)
    
    def get_all_api_keys(self) -> Dict[str, str]:
        """
        Get all retrieved API keys.
        
        Returns:
            Dict containing all API keys
        """
        return self._api_keys.copy()


# Convenience function for backward compatibility
def validate_license(max_retries: int = 4) -> Dict[str, Any]:
    """
    Validate license key (convenience function).
    
    Note: This function reads the license key from lima_config.json file.
    
    Args:
        max_retries: Maximum retry attempts
        
    Returns:
        Dict containing validation result
    """
    auth = LimaAuth()
    return auth.validate_license(max_retries)
