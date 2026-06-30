"""RAG store over segmented court decisions (faillissementspauliana, art. 42 Fw)

Runnable scripts:
    python -m rag.db.init_db   # create the schema
    python -m rag.ingest       # populate judgments + sections from XML
    python -m rag.ingest.embed # compute + store feiten/overwegingen embeddings
    python -m rag              # dispatcher over the above (see main.py)
"""
