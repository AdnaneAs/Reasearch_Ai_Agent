# Research AI Agent System

An intelligent research assistant system that automates academic literature search, processing, and reference management using LLMs and multi-agent architecture.

## Features

- **Smart Literature Search**: Automated search across academic sources with retry mechanisms and proxy rotation
- **Intelligent Processing**: 
  - Abstract extraction and enhancement
  - Citation parsing and normalization
  - Automatic paper analysis and key findings extraction
- **ArXiv Integration**: Direct paper fetching and metadata enhancement from arXiv
- **Google Scholar Integration**: Advanced scholarly paper search with anti-captcha mechanisms
- **LLM-Powered Analysis**: Uses local LLMs for paper analysis and content generation
- **Resilient Architecture**: 
  - Automatic retries with exponential backoff
  - Proxy rotation and user-agent switching
  - Async operations for better performance

## Prerequisites

- Python 3.9+
- Local LLM setup (via Ollama)
- Active internet connection for academic paper searches

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd Research_Ai_Agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the local LLM:
   - Install Ollama from [ollama.ai](https://ollama.ai)
   - Pull the required model (default: llama2)
   ```bash
   ollama pull llama2
   ```

4. Setup configuration:
   - Copy `config/config.yaml.example` to `config/config.yaml` (if not exists)
   - Update the configuration with your settings:
     - LLM settings
     - Search preferences
     - API keys (if using)

## Project Structure

```
.
├── config/
│   └── config.yaml      # Configuration settings
├── src/
│   ├── agents/         # Agent implementations
│   │   ├── search_agent.py     # Handles academic searches
│   │   ├── processing_agent.py # Processes and analyzes papers
│   │   └── zotero_agent.py    # Reference management
│   ├── utils/          # Utility functions
│   │   ├── llm.py            # LLM integration
│   │   └── zotero_connector.py
│   └── app.py          # Main application entry
└── requirements.txt    # Project dependencies
```

## Usage

1. Start the application:
```bash
python src/app.py
```

2. The system will:
   - Initialize the LLM connection
   - Setup scholarly access with proxy rotation
   - Begin accepting search queries

## Features in Detail

### Search Agent
- Multi-source academic search (Google Scholar, arXiv)
- Automatic proxy rotation and retry mechanisms
- Smart parsing of academic citations and metadata

### Processing Agent
- Intelligent abstract extraction
- LLM-powered paper analysis
- Key findings and contribution extraction

### Error Handling
- Automatic retry with exponential backoff
- Proxy rotation for avoiding rate limits
- User-agent rotation for better request distribution

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.