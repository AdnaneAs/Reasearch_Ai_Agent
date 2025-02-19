from typing import Dict, List
from langgraph.graph import Graph, StateGraph
from src.utils.zotero_connector import ZoteroConnector
import yaml

class ZoteroAgent:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            self.config = config['zotero']
        
        self.zotero = ZoteroConnector(config_path)
    
    async def save_article(self, article_data: Dict) -> Dict:
        # Validate required fields
        title = article_data.get('title', '').strip()
        abstract = article_data.get('abstract', '').strip()
        url = article_data.get('url', '').strip()
        
        # Skip articles with missing essential data
        if not title:
            return {
                **article_data,
                "saved_to_zotero": False,
                "error": "Missing title"
            }
            
        if not abstract:
            abstract = "No abstract available"
            
        # Extract keywords from analysis if available
        tags = self.config['auto_tags']
        if 'analysis' in article_data:
            # Add keywords from the analysis
            try:
                # Extract potential keywords from the analysis
                analysis_text = article_data['analysis']
                if isinstance(analysis_text, str) and analysis_text.strip():
                    # Use LLM to extract keywords if available
                    tags.extend([
                        tag.strip() 
                        for tag in analysis_text.lower().split() 
                        if len(tag.strip()) > 3
                    ][:5])  # Add up to 5 relevant terms as tags
            except Exception as e:
                print(f"Error extracting keywords from analysis: {e}")
        
        try:
            saved_item = self.zotero.create_item(
                title=title,
                abstract=abstract,
                url=url,
                tags=list(set(tags))  # Remove duplicate tags
            )
            
            return {
                **article_data,
                "zotero_key": saved_item.get('key'),
                "saved_to_zotero": True
            }
        except Exception as e:
            print(f"Failed to save article '{title}': {str(e)}")
            return {
                **article_data,
                "saved_to_zotero": False,
                "error": str(e)
            }
    
    async def batch_save(self, processed_articles: List[Dict]) -> List[Dict]:
        saved_articles = []
        for article in processed_articles:
            saved = await self.save_article(article)
            saved_articles.append(saved)
        return saved_articles
    
    def create_zotero_graph(self) -> Graph:
        workflow = StateGraph()
        
        # Define Zotero interaction nodes
        workflow.add_node("save_to_zotero", self.batch_save)
        
        # Set entry point
        workflow.set_entry_point("save_to_zotero")
        
        return workflow.compile()