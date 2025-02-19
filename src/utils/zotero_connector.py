from pyzotero import zotero
import yaml
from typing import Dict, List, Optional

class ZoteroConnector:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['zotero']
        
        self.zot = zotero.Zotero(
            library_id=self.config['library_id'],
            library_type=self.config['library_type'],
            api_key=self.config['api_key']
        )
        self.collection_name = self.config['collection_name']
        self.auto_tags = self.config['auto_tags']

    def create_item(self, title: str, abstract: str, url: str, tags: Optional[List[str]] = None) -> Dict:
        if tags is None:
            tags = self.auto_tags

        template = self.zot.item_template('journalArticle')
        template['title'] = title
        template['abstractNote'] = abstract
        template['url'] = url
        template['tags'] = [{'tag': tag} for tag in tags]

        try:
            result = self.zot.create_items([template])
            if not result or not isinstance(result, list):
                raise ValueError("Failed to create Zotero item: API returned empty or invalid response")
            return result[0]['data']
        except Exception as e:
            print(f"Error creating Zotero item: {e}")
            print(f"Template data: {template}")
            raise

    def get_collection_items(self, collection_name: Optional[str] = None) -> List[Dict]:
        if collection_name is None:
            collection_name = self.collection_name
        
        collections = self.zot.collections()
        target_collection = next(
            (c for c in collections if c['data']['name'] == collection_name),
            None
        )
        
        if target_collection:
            return self.zot.collection_items(target_collection['key'])
        return []

    def search_items(self, query: str) -> List[Dict]:
        return self.zot.items(q=query)

    def add_tags(self, item_key: str, tags: List[str]):
        current = self.zot.item(item_key)
        current_tags = current['data'].get('tags', [])
        new_tags = [{'tag': tag} for tag in tags]
        current['data']['tags'] = current_tags + new_tags
        self.zot.update_item(current)