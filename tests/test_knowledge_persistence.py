from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Base, Document, DocumentChunk


def test_knowledge_schema_can_persist_document_chunk():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doc = Document(source_uri="memory://test", title="Test", sha256="abc", ingest_state="indexed")
        session.add(doc)
        session.flush()
        session.add(DocumentChunk(document_id=doc.id, chunk_index=0, text="hello daypilot", token_count=2))
        session.commit()

        chunk = session.scalars(select(DocumentChunk)).one()
        assert chunk.text == "hello daypilot"
        assert chunk.document_id == doc.id
