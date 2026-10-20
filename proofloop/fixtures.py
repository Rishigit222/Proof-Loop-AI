DEMO_SCENARIOS = {
    "supported": {
        "title": "Supported: offline verification",
        "answer": "ProofLoop AI stores verification cases in SQLite. The core engine runs without external API keys.",
        "sources": [
            {"name": "Product brief", "content": "ProofLoop AI stores verification cases in SQLite. The core engine runs without external API keys."},
            {"name": "Architecture note", "content": "The deterministic verification engine runs locally and does not require a model provider."},
        ],
    },
    "unsupported": {
        "title": "Unsupported: enterprise synchronization",
        "answer": "ProofLoop AI automatically synchronizes evidence with every major enterprise knowledge base.",
        "sources": [
            {"name": "Product brief", "content": "ProofLoop AI accepts pasted text and multiple named source documents. Sources remain local to the case."},
        ],
    },
    "contradicted": {
        "title": "Contradicted: external model required",
        "answer": "ProofLoop AI requires an external generative AI provider to verify claims.",
        "sources": [
            {"name": "Architecture note", "content": "The core verification engine runs offline without model credentials. External model providers are optional future integrations."},
        ],
    },
}
