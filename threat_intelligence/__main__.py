from .models import SourceType
from .store import KnowledgeStore
from .ingestion import IngestionPipeline
from .retriever import Retriever

if __name__ == "__main__":
    store = KnowledgeStore()
    IngestionPipeline(store).ingest([{
        "document_id": "demo-1", "source": "curated-demo", "source_type": SourceType.CURATED,
        "title": "Authentication monitoring", "content": "Repeated authentication failures should be investigated.",
        "tags": ["authentication", "monitoring"],
    }])
    print(Retriever(store).search("authentication"))
