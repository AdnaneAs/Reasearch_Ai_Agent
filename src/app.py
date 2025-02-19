import streamlit as st
import asyncio
from src.agents.search_agent import SearchAgent
from src.agents.processing_agent import ProcessingAgent
from src.agents.zotero_agent import ZoteroAgent
import yaml
import time

# Initialize session state
if 'search_running' not in st.session_state:
    st.session_state.search_running = False
if 'stop_search' not in st.session_state:
    st.session_state.stop_search = False
if 'processed_articles' not in st.session_state:
    st.session_state.processed_articles = []
if 'current_status' not in st.session_state:
    st.session_state.current_status = ""
if 'error_count' not in st.session_state:
    st.session_state.error_count = 0
if 'current_operation' not in st.session_state:
    st.session_state.current_operation = None
if 'total_operations' not in st.session_state:
    st.session_state.total_operations = 0
if 'completion_status' not in st.session_state:
    st.session_state.completion_status = {}

def update_status(message: str, is_error: bool = False):
    st.session_state.current_status = message
    if is_error:
        status_container.error(message)
    else:
        status_container.info(message)

def stop_operations():
    """Safely stop all running operations"""
    st.session_state.stop_search = True
    st.session_state.search_running = False
    status_container.warning("⏹️ Stopping... Please wait for current operation to complete...")

def update_operation_status(operation: str, status: str, total: int = None):
    """Update the status of a specific operation"""
    if total:
        st.session_state.total_operations = total
    st.session_state.current_operation = operation
    st.session_state.completion_status[operation] = status
    
    # Update progress indicators
    status_container.info(f"🔄 {operation}: {status}")
    if total:
        progress = len([s for s in st.session_state.completion_status.values() if s == "completed"]) / total
        overall_progress.progress(progress)

# Load configuration
with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Initialize agents
search_agent = SearchAgent()
processing_agent = ProcessingAgent()
zotero_agent = ZoteroAgent()

st.title("Research AI Assistant")

# Create sidebar for settings
with st.sidebar:
    st.header("Settings")
    max_results = st.slider("Max results", 5, 50, 10)
    retry_on_error = st.checkbox("Retry on errors", value=True)
    show_errors = st.checkbox("Show detailed errors", value=False)
    
    with st.expander("Advanced Settings"):
        st.write("**LLM Model:**", config['llm']['model'])
        st.write("**Zotero Collection:**", config['zotero']['collection_name'])

# Main search interface
st.header("Article Search")

# Input area with example
example = """RAG
Agentic RAG
Retrieval Generation Augmentation"""
keywords = st.text_area("Enter keywords (one per line)", 
                       height=100,
                       placeholder=example)

# Create columns for search and stop buttons
col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    search_button = st.button("🔍 Search and Process", 
                             disabled=st.session_state.search_running,
                             use_container_width=True)
with col2:
    stop_button = st.button("⏹️ Stop", 
                           disabled=not st.session_state.search_running,
                           use_container_width=True)
with col3:
    if st.session_state.error_count > 0:
        st.error(f"Errors: {st.session_state.error_count}")

# Create containers for various UI elements
status_container = st.empty()
overall_progress = st.empty()
article_progress = st.empty()
current_article_status = st.empty()
results_container = st.container()

if stop_button:
    stop_operations()

if search_button and keywords:
    st.session_state.search_running = True
    st.session_state.stop_search = False
    st.session_state.processed_articles = []
    st.session_state.error_count = 0
    st.session_state.completion_status = {}
    results_container.empty()
    
    try:
        # Convert keywords to list
        keyword_list = [k.strip() for k in keywords.split("\n") if k.strip()]
        st.session_state.total_operations = len(keyword_list)
        
        all_results = []
        
        for idx, keyword in enumerate(keyword_list, 1):
            if st.session_state.stop_search:
                update_operation_status("Search", "stopped")
                break
            
            # Update status for current keyword
            update_operation_status(
                "Searching",
                f"Processing '{keyword}' ({idx}/{len(keyword_list)})",
                len(keyword_list)
            )
            
            # Search for articles
            try:
                search_results = asyncio.run(search_agent.search_articles([keyword]))
                
                if search_results:
                    # Process each result in real-time
                    for result_idx, result in enumerate(search_results, 1):
                        if st.session_state.stop_search:
                            break
                            
                        update_operation_status(
                            "Processing",
                            f"Article {result_idx}/{len(search_results)} for '{keyword}'"
                        )
                        
                        try:
                            # Process and save article
                            processed = asyncio.run(processing_agent.process_article(result))
                            saved = asyncio.run(zotero_agent.save_article(processed))
                            
                            # Display result immediately
                            with results_container:
                                with st.expander(
                                    f"📄 {saved.get('title', 'Untitled')} ({idx}/{len(keyword_list)})", 
                                    expanded=True
                                ):
                                    if saved.get('saved_to_zotero'):
                                        st.success("✅ Saved to Zotero")
                                        
                                        # Display article details
                                        col1, col2 = st.columns([3, 1])
                                        with col1:
                                            st.markdown("**Abstract:**")
                                            st.markdown(saved.get('abstract', 'No abstract available'))
                                            if isinstance(saved.get('analysis'), dict):
                                                st.markdown("**Analysis:**")
                                                st.markdown(saved['analysis'].get('full_analysis', ''))
                                        with col2:
                                            st.markdown("**Info:**")
                                            st.markdown(f"**Year:** {saved.get('year', 'N/A')}")
                                            st.markdown(f"**Citations:** {saved.get('citations', 'N/A')}")
                                            if saved.get('url'):
                                                st.markdown(f"[View Article]({saved['url']})")
                                            if saved.get('analysis', {}).get('keywords'):
                                                st.markdown("**Keywords:**")
                                                st.markdown(", ".join(saved['analysis']['keywords']))
                                    else:
                                        st.error("❌ Failed to save to Zotero")
                                        if 'error' in saved:
                                            st.error(f"Error: {saved['error']}")
                            
                            all_results.append(saved)
                            
                        except Exception as e:
                            st.error(f"Error processing article: {str(e)}")
                            if not retry_on_error:
                                continue
                else:
                    st.warning(f"No results found for '{keyword}'")
            
            except Exception as e:
                if "captcha" in str(e).lower():
                    st.error("⚠️ Google Scholar is blocking requests. Please wait a few minutes.")
                    break
                else:
                    st.error(f"Error searching for '{keyword}': {str(e)}")
                if not retry_on_error:
                    continue
            
            # Mark operation as completed
            st.session_state.completion_status[f"Keyword {idx}"] = "completed"
        
        # Show final summary
        if all_results:
            saved_count = sum(1 for r in all_results if r.get('saved_to_zotero'))
            if saved_count == len(all_results):
                status_container.success(f"✅ Successfully saved all {len(all_results)} articles")
            else:
                status_container.warning(f"⚠️ Saved {saved_count} out of {len(all_results)} articles")
        elif not st.session_state.stop_search:
            status_container.error("❌ No articles were found or saved")
        
    except Exception as e:
        if "connection refused" in str(e).lower():
            status_container.error("❌ Error: Ollama service is not running. Please start ollama first.")
        else:
            status_container.error(f"❌ An error occurred: {str(e)}")
    
    finally:
        st.session_state.search_running = False
        st.session_state.stop_search = False
        overall_progress.empty()
        current_article_status.empty()

# Zotero Management section at the bottom
st.header("📚 Saved Articles")
if st.button("View Saved Articles"):
    with st.spinner("Loading saved articles..."):
        saved_articles = zotero_agent.zotero.get_collection_items()
        
        if not saved_articles:
            st.info("No articles found in Zotero collection")
        else:
            for article in saved_articles:
                with st.expander(f"📚 {article['data'].get('title', 'Untitled')}"):
                    st.write("**Abstract:**", article['data'].get('abstractNote', 'No abstract available'))
                    st.write("**Tags:**", ", ".join([t['tag'] for t in article['data'].get('tags', [])]))
                    st.write("**URL:**", article['data'].get('url', 'No URL available'))