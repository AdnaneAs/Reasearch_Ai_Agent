from setuptools import setup, find_packages

setup(
    name="research_ai_agent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "streamlit>=1.32.0",
        "langgraph>=0.1.1",
        "pyzotero>=1.5.18",
        "ollama>=0.1.6",
        "python-dotenv>=1.0.0",
        "pydantic>=2.6.1",
        "PyYAML>=6.0.1",
        "requests>=2.31.0",
        "typing-extensions>=4.9.0",
    ],
)