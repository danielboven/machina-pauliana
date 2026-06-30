CREATE EXTENSION IF NOT EXISTS vector;             -- pgvector, for section embeddings

DO $$ BEGIN
  CREATE TYPE court AS ENUM ('rechtbank', 'gerechtshof', 'hoge_raad');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE section_label AS ENUM
    ('procesverloop', 'feiten', 'geschil', 'overwegingen', 'beslissing', 'overig');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- one row per decision ----------------------------------------------------
CREATE TABLE IF NOT EXISTS judgment (
  ecli                    text PRIMARY KEY,     -- bare, normalized ECLI
  court                   court,
  strategy                text,                 -- segmentation strategy used
  judgment_date           date,                 -- Uitspraakdatum from the XML
  onverplicht             boolean,              -- true = onverplicht, false = verplicht
  wetenschap              boolean,
  benadeling_schuldeisers boolean
);

-- ordered sections (the RAG chunks) ---------------------------------------
CREATE TABLE IF NOT EXISTS section (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- stable chunk handle
  ecli      text NOT NULL REFERENCES judgment (ecli) ON DELETE CASCADE,
  position  int  NOT NULL,                      -- document order (0-based)
  label     section_label NOT NULL,             -- 6-type section enum (pre retrieval)
  markdown  text NOT NULL,
  embedding vector(2000),  -- Qwen3-Embedding-8B (Matryoshka Representation Learning to 2000 dims through Scaleway)
  UNIQUE (ecli, position)
);
CREATE INDEX IF NOT EXISTS section_ecli_idx ON section (ecli);
CREATE INDEX IF NOT EXISTS section_embedding_idx ON section
  USING hnsw (embedding vector_cosine_ops);      -- 2000 dims = within pgvector's HNSW limit

-- directional citation edges (populated in a 2nd pass) --------------------
CREATE TABLE IF NOT EXISTS relation (
  source_ecli text NOT NULL REFERENCES judgment (ecli) ON DELETE CASCADE,  -- asserting judgment
  target_ecli text NOT NULL REFERENCES judgment (ecli) ON DELETE CASCADE,  -- referenced judgment
  PRIMARY KEY (source_ecli, target_ecli)
);
CREATE INDEX IF NOT EXISTS relation_target_idx ON relation (target_ecli);  -- reverse lookup
