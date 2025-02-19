from typing import Dict, List, Optional
import yaml
from src.utils.llm import LLMManager
from scholarly import scholarly, ProxyGenerator
import logging
import bibtexparser
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import arxiv
import random
import asyncio
from aiohttp import ClientSession
import backoff

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of user agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.48 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

class SearchAgent:
    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['agents']['search']
        
        self.llm = LLMManager(config_path)
        self.max_results = self.config['max_results']
        self._setup_scholarly()
    
    def _setup_scholarly(self):
        """Setup scholarly with proxy and user agent rotation"""
        try:
            # Initialize proxy generator
            pg = ProxyGenerator()
            
            # Try using free proxies first
            if pg.FreeProxies():
                scholarly.use_proxy(pg)
            
            # Set random user agent
            scholarly.set_headers({'User-Agent': random.choice(USER_AGENTS)})
            
        except Exception as e:
            logger.error(f"Error setting up scholarly: {e}")

    async def _retry_search(self, keywords: str, max_retries: int = 3) -> List[Dict]:
        """Retry search with different user agents and proxies"""
        for attempt in range(max_retries):
            try:
                # Rotate user agent
                scholarly.set_headers({'User-Agent': random.choice(USER_AGENTS)})
                
                # Try search
                search_query = scholarly.search_pubs(keywords)
                return search_query
            
            except Exception as e:
                logger.error(f"Search attempt {attempt + 1} failed: {e}")
                if "captcha" in str(e).lower():
                    # If we hit a captcha, try rotating proxy
                    pg = ProxyGenerator()
                    if pg.FreeProxies():
                        scholarly.use_proxy(pg)
                
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to search after {max_retries} attempts")
                
                # Wait before retrying
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    def _parse_bibtex(self, bibtex_str: str) -> Dict:
        """Parse BibTeX string into a dictionary"""
        try:
            # Clean up the BibTeX string
            cleaned_bibtex = bibtex_str.strip()
            if not cleaned_bibtex.startswith('@'):
                cleaned_bibtex = '@article{' + cleaned_bibtex
            
            bib_database = bibtexparser.loads(cleaned_bibtex)
            if bib_database.entries:
                return bib_database.entries[0]
            return {}
        except Exception as e:
            logger.error(f"Error parsing BibTeX: {e}")
            return {}

    @backoff.on_exception(backoff.expo,
                         Exception,
                         max_tries=3)
    async def _parse_bibtex_entry(self, bibtex_str: str, query: str) -> Dict:
        """Parse and enhance BibTeX entry using LLM with retries"""
        try:
            # First try standard BibTeX parsing
            parsed_data = self._parse_bibtex(bibtex_str)
            if not parsed_data:
                # If parsing fails, use LLM to extract information
                prompt = f"""
                Extract the following information from this citation entry:
                {bibtex_str}
                
                Format as JSON with these fields:
                - title: the paper title
                - authors: list of authors
                - year: publication year
                - abstract: paper abstract (if available)
                - journal/venue: publication venue
                - url: paper URL (if available)
                - doi: DOI (if available)
                """
                
                llm_response = await self.llm.generate_response(prompt)
                try:
                    # Try to parse LLM response as JSON
                    import json
                    enhanced_data = json.loads(llm_response)
                    return enhanced_data
                except:
                    logger.warning("Failed to parse LLM response as JSON")
                    return {}
            
            # Try to find or generate URL
            if 'doi' in parsed_data and not parsed_data.get('url'):
                parsed_data['url'] = f"https://doi.org/{parsed_data['doi']}"
            elif 'eprint' in parsed_data:
                parsed_data['url'] = f"https://arxiv.org/abs/{parsed_data['eprint']}"
            
            # If no abstract, try to generate one using LLM
            if not parsed_data.get('abstract'):
                prompt = f"""
                Based on this paper's title and the search query, generate a brief academic abstract:
                Title: {parsed_data.get('title', '')}
                Search Query: {query}
                Relevant Fields: {', '.join(f'{k}: {v}' for k, v in parsed_data.items() if k in ['year', 'journal', 'author'])}
                
                Generate a concise academic abstract that might fit this paper.
                """
                parsed_data['abstract'] = await self.llm.generate_response(prompt)
                parsed_data['abstract_generated'] = True
            
            return parsed_data
        except Exception as e:
            logger.error(f"Error parsing BibTeX entry: {e}")
            return {}

    def _extract_citation_info(self, citation_text: str) -> Dict:
        """Extract information from citation text using LLM"""
        try:
            prompt = f"""Extract the following information from this citation:
            Citation: {citation_text}
            
            Return only these fields in your response:
            - Title
            - Authors (as a comma-separated list)
            - Journal/Source
            - Year
            - DOI or URL if present
            """
            
            response = self.llm.generate_response(prompt)
            # Parse the response into structured data
            # You might need to adjust this based on your LLM's output format
            return response
        except Exception as e:
            logger.error(f"Error extracting citation info: {e}")
            return {}

    async def _fetch_arxiv_details(self, arxiv_id: str) -> Optional[Dict]:
        """Fetch detailed information from arXiv API"""
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(search.results())
            return {
                'title': paper.title,
                'abstract': paper.summary,
                'authors': [author.name for author in paper.authors],
                'url': paper.entry_id,
                'published': paper.published.strftime('%Y-%m-%d'),
                'doi': paper.doi if paper.doi else None,
                'categories': paper.categories
            }
        except Exception as e:
            logger.error(f"Error fetching arXiv details: {e}")
            return None

    async def _enhance_with_arxiv(self, result: Dict) -> Dict:
        """Enhance result with arXiv data if available"""
        try:
            # Check if URL or any field contains arXiv ID
            arxiv_patterns = [
                r'arxiv.org/abs/(\d+\.\d+)',
                r'arxiv.org/pdf/(\d+\.\d+)',
                r'arXiv:(\d+\.\d+)'
            ]
            
            arxiv_id = None
            for pattern in arxiv_patterns:
                # Check URL
                if result.get('url'):
                    match = re.search(pattern, result.get('url'))
                    if match:
                        arxiv_id = match.group(1)
                        break
                
                # Check BibTeX
                if result.get('bibtex'):
                    match = re.search(pattern, result.get('bibtex'))
                    if match:
                        arxiv_id = match.group(1)
                        break
            
            if arxiv_id:
                arxiv_data = await self._fetch_arxiv_details(arxiv_id)
                if arxiv_data:
                    # Update or fill missing information
                    if not result.get('abstract') or len(result['abstract']) < len(arxiv_data['abstract']):
                        result['abstract'] = arxiv_data['abstract']
                    if not result.get('authors'):
                        result['authors'] = arxiv_data['authors']
                    if not result.get('doi') and arxiv_data.get('doi'):
                        result['doi'] = arxiv_data['doi']
                    result['categories'] = arxiv_data.get('categories', [])
                    result['source'] = 'arXiv'
            
            return result
        except Exception as e:
            logger.error(f"Error enhancing with arXiv: {e}")
            return result

    async def search_articles(self, keywords: List[str]) -> List[Dict]:
        try:
            formatted_keywords = " ".join(keywords)
            logger.info(f"Searching for: {formatted_keywords}")
            
            # Use retry mechanism for searching
            try:
                search_query = await self._retry_search(formatted_keywords)
            except Exception as e:
                logger.error(f"Search failed completely: {e}")
                return []
            
            results = []
            
            for i in range(self.max_results):
                try:
                    pub = next(search_query)
                    logger.info(f"Processing publication {i+1}/{self.max_results}")
                    
                    # Get the citation in BibTeX format with retries
                    try:
                        detailed_pub = None
                        for retry in range(3):  # Try 3 times to get detailed publication
                            try:
                                detailed_pub = scholarly.fill(pub)
                                break
                            except Exception as e:
                                if "captcha" in str(e).lower():
                                    # Rotate proxy and user agent
                                    self._setup_scholarly()
                                    await asyncio.sleep(2 ** retry)
                                    continue
                                raise e
                        
                        if not detailed_pub:
                            raise Exception("Failed to get detailed publication info")
                        
                        # Process the publication data
                        bibtex = detailed_pub.get('bdata', {}).get('bibtex', '')
                        
                        # Try Google Scholar specific parsing first
                        gs_data = self._process_google_scholar_bibtex(bibtex)
                        if gs_data and gs_data.get('title'):
                            # Successfully parsed Google Scholar BibTeX
                            result = {
                                "title": gs_data['title'],
                                "authors": gs_data['authors'],
                                "year": gs_data['year'],
                                "venue": gs_data['venue'],
                                "url": gs_data.get('url', detailed_pub.get('pub_url', '')),
                                "doi": gs_data.get('doi', ''),
                                "citations": detailed_pub.get('citedby', 0),
                                "keywords": keywords,
                                "search_date": datetime.now().isoformat(),
                                "bibtex": gs_data['raw_bibtex']
                            }
                        else:
                            # Fall back to regular parsing
                            parsed_data = await self._parse_bibtex_entry(bibtex, formatted_keywords)
                            result = {
                                "title": parsed_data.get('title', detailed_pub.get('bdata', {}).get('title', '')),
                                "abstract": parsed_data.get('abstract', ''),
                                "url": parsed_data.get('url', detailed_pub.get('pub_url', '')),
                                "year": parsed_data.get('year', detailed_pub.get('bdata', {}).get('year', '')),
                                "authors": parsed_data.get('author', detailed_pub.get('bdata', {}).get('author', [])),
                                "citations": detailed_pub.get('citedby', 0),
                                "keywords": keywords,
                                "search_date": datetime.now().isoformat(),
                                "bibtex": bibtex,
                                "venue": parsed_data.get('journal', detailed_pub.get('bdata', {}).get('venue', '')),
                                "doi": parsed_data.get('doi', '')
                            }
                        
                        # Try to enhance with arXiv data regardless of source
                        result = await self._enhance_with_arxiv(result)
                        
                        # Get abstract if missing
                        if not result.get('abstract') and result.get('url'):
                            result['abstract'] = await self._extract_abstract_with_retry(result['url'])
                        
                        # Add result only if we have at least a title and some content
                        if result['title'] and (result.get('abstract') or result.get('url')):
                            results.append(result)
                            logger.info(f"Successfully processed article: {result['title']}")
                        else:
                            logger.warning(f"Skipping article due to insufficient data")
                    
                    except Exception as e:
                        logger.error(f"Error processing detailed publication: {str(e)}")
                        continue
                    
                except StopIteration:
                    break
                except Exception as e:
                    logger.error(f"Error processing publication: {str(e)}")
                    continue
            
            return results
        except Exception as e:
            logger.error(f"Error in search_articles: {str(e)}")
            return []

    async def _extract_abstract_with_retry(self, url: str, max_retries: int = 3) -> str:
        """Extract abstract from URL with retries"""
        for attempt in range(max_retries):
            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                return await self._extract_abstract_from_url(url, headers)
            except Exception as e:
                logger.error(f"Error extracting abstract (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
        return ""

    @backoff.on_exception(backoff.expo,
                         Exception,
                         max_tries=3)
    async def _async_request(self, url: str, headers: Dict = None) -> str:
        """Make async HTTP request with retries"""
        if headers is None:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
        
        async with ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                return await response.text()

    async def _extract_abstract_from_url(self, url: str, headers: Dict = None) -> str:
        """Extract abstract from publication URL using async requests"""
        try:
            # Check if it's an arXiv paper
            arxiv_id_match = re.search(r'arxiv.org/abs/(\d+\.\d+)', url)
            if arxiv_id_match:
                arxiv_id = arxiv_id_match.group(1)
                search = arxiv.Search(id_list=[arxiv_id])
                paper = next(search.results())
                return paper.summary

            # For other URLs, try to extract from webpage
            if headers is None:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
            
            html = await self._async_request(url, headers)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Common abstract selectors
            abstract_selectors = [
                'div.abstract',
                'div#abstract',
                'section.abstract',
                'p.abstract',
                'meta[name="description"]',
                'meta[property="og:description"]'
            ]
            
            for selector in abstract_selectors:
                elements = soup.select(selector)
                if elements:
                    content = elements[0].get_text() if not elements[0].get('content') else elements[0]['content']
                    return content.strip()
            
            # If no abstract found, use LLM to find it
            prompt = f"""
            Given this webpage content, find and extract ONLY the research paper's abstract.
            If you can't find a clear abstract, return an empty string.
            
            Webpage content:
            {soup.get_text()[:2000]}  # First 2000 chars should be enough
            """
            
            abstract = await self.llm.generate_response(prompt)
            return abstract.strip()
            
        except Exception as e:
            logger.error(f"Error extracting abstract from URL {url}: {e}")
            raise

    async def process_results(self, results: List[Dict]) -> List[Dict]:
        """Process and enrich the search results with LLM analysis"""
        processed_results = []
        
        for result in results:
            try:
                analysis_prompt = f"""
                Analyze this research article and extract key information:
                Title: {result['title']}
                Abstract: {result['abstract']}
                
                Please provide:
                1. Main research contributions
                2. Key findings
                3. Methodology used
                4. Potential applications
                """
                
                analysis = await self.llm.generate_response(analysis_prompt)
                result['analysis'] = analysis
                processed_results.append(result)
            except Exception as e:
                print(f"Error processing result {result.get('title', '')}: {str(e)}")
                result['analysis'] = "Error during analysis"
                processed_results.append(result)
        
        return processed_results

    def _process_google_scholar_bibtex(self, bibtex_str: str) -> Dict:
        """Specifically process Google Scholar BibTeX format"""
        try:
            # Clean up the BibTeX entry
            bibtex_str = bibtex_str.strip()
            if not bibtex_str.startswith('@'):
                return {}

            # Extract key components using regex
            title_match = re.search(r'title={([^}]+)}', bibtex_str)
            author_match = re.search(r'author={([^}]+)}', bibtex_str)
            year_match = re.search(r'year={([^}]+)}', bibtex_str)
            journal_match = re.search(r'journal={([^}]+)}', bibtex_str)
            
            # Build result dictionary
            result = {
                'title': title_match.group(1) if title_match else '',
                'authors': [auth.strip() for auth in author_match.group(1).split(',')] if author_match else [],
                'year': year_match.group(1) if year_match else '',
                'venue': journal_match.group(1) if journal_match else '',
                'raw_bibtex': bibtex_str
            }

            # Extract any DOI or URL if present
            doi_match = re.search(r'doi={([^}]+)}', bibtex_str)
            if doi_match:
                result['doi'] = doi_match.group(1)
                result['url'] = f"https://doi.org/{doi_match.group(1)}"
            
            # Extract arXiv identifier if present
            arxiv_match = re.search(r'eprint={([^}]+)}', bibtex_str) or re.search(r'arxiv:(\d+\.\d+)', bibtex_str, re.IGNORECASE)
            if arxiv_match:
                result['arxiv_id'] = arxiv_match.group(1)
                result['url'] = f"https://arxiv.org/abs/{arxiv_match.group(1)}"

            return result
        except Exception as e:
            logger.error(f"Error processing Google Scholar BibTeX: {e}")
            return {}