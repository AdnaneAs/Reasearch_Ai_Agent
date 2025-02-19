import ollama
from typing import Dict, Any, List
import yaml
import logging
import time
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, calls_per_second: int = 2):
        self.calls_per_second = calls_per_second
        self.last_call = datetime.now()
    
    async def wait(self):
        now = datetime.now()
        time_since_last = (now - self.last_call).total_seconds()
        if time_since_last < (1.0 / self.calls_per_second):
            wait_time = (1.0 / self.calls_per_second) - time_since_last
            await asyncio.sleep(wait_time)
        self.last_call = datetime.now()

class LLMManager:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['llm']
        
        self.model = self.config['model']
        self.max_tokens = self.config['max_tokens']
        self.rate_limiter = RateLimiter()
        logger.info(f"Initialized LLMManager with model: {self.model}")
    
    async def _check_ollama_service(self) -> bool:
        """Verify that ollama service is running and responding"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/", timeout=5.0)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama service check failed: {e}")
            return False

    async def _list_models(self) -> List[str]:
        """Get list of available models from ollama"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [model['name'] for model in data.get('models', [])]
                return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def ensure_model_loaded(self, max_retries: int = 3) -> bool:
        """Ensure the model is loaded and ready to use"""
        if not await self._check_ollama_service():
            logger.error("Ollama service is not running")
            return False
            
        for attempt in range(max_retries):
            try:
                logger.info(f"Checking if model {self.model} is loaded (attempt {attempt + 1}/{max_retries})")
                
                available_models = await self._list_models()
                model_name = self.model.split(':')[0]
                
                if model_name in available_models:
                    logger.info(f"Model {self.model} is available")
                    return True
                
                # If model not found, try to pull it
                logger.warning(f"Model {self.model} not found, attempting to pull...")
                await self._pull_model()
                return True
                
            except Exception as e:
                logger.error(f"Error checking/pulling model: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
        return False

    async def _pull_model(self) -> bool:
        """Pull the model from ollama"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/pull",
                    json={"name": self.model},
                    timeout=300.0  # 5 minutes timeout for model pulling
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False

    async def generate_response(self, prompt: str) -> str:
        # Rate limit our requests
        await self.rate_limiter.wait()
        
        if not await self._check_ollama_service():
            error_msg = "Error: Ollama service is not running. Please start ollama first."
            logger.error(error_msg)
            return error_msg
        
        # Ensure model is loaded
        if not await self.ensure_model_loaded():
            error_msg = f"Error: Failed to load model {self.model}"
            logger.error(error_msg)
            return error_msg
            
        try:
            logger.debug(f"Generating response with model {self.model}")
            options = {
                "num_predict": self.max_tokens,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "options": options
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('response', '')
                else:
                    raise Exception(f"Ollama API error: {response.status_code}")
                    
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    async def analyze_text(self, text: str, task: str) -> Dict[str, Any]:
        logger.debug(f"Analyzing text for task: {task}")
        prompt = f"Task: {task}\n\nText to analyze: {text}"
        response = await self.generate_response(prompt)
        return {"analysis": response}