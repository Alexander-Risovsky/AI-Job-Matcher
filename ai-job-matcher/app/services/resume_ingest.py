"""Ingest PDF resume explicitly. Never delete previous collection implicitly."""
from pathlib import Path
from hashlib import sha256
from uuid import uuid5, NAMESPACE_URL
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient, models
from langchain_ollama import OllamaEmbeddings


def ingest_pdf(file: Path, settings, *, replace_document: bool = False):
    doc_id = sha256(file.read_bytes()).hexdigest()
    reader = PdfReader(file)
    content = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not content.strip():
        raise ValueError("PDF contains no extractable text")
    chunks = RecursiveCharacterTextSplitter(chunk_size=650, chunk_overlap=100).split_text(content)
    client = QdrantClient(url=settings.qdrant_url)
    collection = settings.qdrant_collection
    if not client.collection_exists(collection):
        client.create_collection(collection,
            vectors_config=models.VectorParams(size=settings.qdrant_vector_size, distance=models.Distance.COSINE))
    else:
        vectors = client.get_collection(collection).config.params.vectors
        if getattr(vectors, "size", None) != settings.qdrant_vector_size:
            raise ValueError("Existing collection has unexpected vector config")
    embedder = OllamaEmbeddings(model=settings.ollama_embed_model, base_url=settings.ollama_base_url)
    vectors = embedder.embed_documents(chunks)
    points = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        if len(vector) != settings.qdrant_vector_size:
            raise ValueError("Wrong embedding dimensionality")
        points.append(models.PointStruct(id=str(uuid5(NAMESPACE_URL, f"{doc_id}:{index}")),
            vector=vector, payload={"page_content": chunk, "metadata": {
                "document_type": "resume", "source": "candidate_resume", "document_id": doc_id,
                "chunk_index": index}}))
    client.upsert(collection_name=collection, points=points, wait=True)
    return {"document_id": doc_id, "chunks": len(chunks), "note": "existing other documents were not deleted"}
