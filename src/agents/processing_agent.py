from typing import Dict, List
from langgraph.graph import Graph, StateGraph
from src.utils.llm import LLMManager
import yaml
import logging
import asyncio

logger = logging.getLogger(__name__)

class ProcessingAgent:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['agents']['processing']
        
        self.llm = LLMManager(config_path)
        self.chunk_size = self.config['chunk_size']
        self.overlap = self.config['overlap']
    
    async def process_article(self, article: Dict, progress_callback=None) -> Dict:
        """Process a single article with progress tracking"""
        try:
            # Notify progress
            if progress_callback:
                progress_callback("Analyzing article content...")

            # Generate analysis prompt
            analysis_prompt = f"""
            Analyze this research article and provide a detailed breakdown:
            Title: {article.get('title', 'Unknown')}
            Abstract: {article.get('abstract', 'No abstract available')}
            
            Provide:
            1. Main research contributions
            2. Key findings
            3. Methodology used
            4. Potential applications
            5. Key topics/keywords
            """
            
            if progress_callback:
                progress_callback("Generating analysis...")
            
            analysis = await self.llm.generate_response(analysis_prompt)
            
            # Extract keywords for tagging
            keywords_prompt = f"""
            Based on the analysis, extract 5-7 relevant keywords that best describe this paper.
            Return only the keywords as a comma-separated list.
            
            Analysis: {analysis}
            """
            
            if progress_callback:
                progress_callback("Extracting keywords...")
            
            keywords = await self.llm.generate_response(keywords_prompt)
            
            processed_article = {
                **article,
                "analysis": {
                    "full_analysis": analysis,
                    "keywords": [k.strip() for k in keywords.split(",")]
                }
            }
            
            if progress_callback:
                progress_callback("Processing complete")
            
            return processed_article
        except Exception as e:
            logger.error(f"Error processing article: {str(e)}")
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            return {**article, "error": str(e)}
    
    async def batch_process(self, articles: List[Dict], progress_callback=None) -> List[Dict]:
        """Process multiple articles with progress tracking"""
        processed = []
        total = len(articles)
        
        for idx, article in enumerate(articles, 1):
            if progress_callback:
                progress_callback(f"Processing article {idx}/{total}")
            
            async def update_progress(status: str):
                if progress_callback:
                    progress_callback(f"Article {idx}/{total}: {status}")
            
            result = await self.process_article(article, update_progress)
            processed.append(result)
        
        return processed
    
    def create_processing_graph(self) -> Graph:
        workflow = StateGraph()
        
        # Define processing node
        workflow.add_node("process", self.batch_process)
        
        # Set entry point
        workflow.set_entry_point("process")
        
        return workflow.compile()