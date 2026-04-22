import structlog
import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

log = structlog.get_logger()


class LegalKnowledgeBase:
    """
    Vector store of German and EU legal sources.
    Retrieves relevant legal context for a given clause type.
    """

    COLLECTION_NAME = "german_law"

    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"  # Handles German + English
        )
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self.ef,
        )

    def retrieve(self, clause_text: str, contract_type: str, n_results: int = 3) -> str:
        """
        Retrieve the most relevant legal provisions for a given clause.
        Returns formatted text ready for injection into the LLM prompt.
        """
        if self.collection.count() == 0:
            log.warning(
                "knowledge_base.empty",
                message="No legal documents indexed. Run scripts/index_legal_docs.py",
            )
            return ""

        query = f"{contract_type} contract: {clause_text[:500]}"

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas"],
        )

        if not results["documents"] or not results["documents"][0]:
            return ""

        context_parts = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            source = meta.get("source", "Unknown")
            context_parts.append(f"[{source}]\n{doc}")

        return "\n\n".join(context_parts)


# Singleton — imported once, reused across all requests
knowledge_base = LegalKnowledgeBase()
