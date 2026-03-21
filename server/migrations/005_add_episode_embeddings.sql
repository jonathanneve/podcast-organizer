ALTER TABLE episodes ADD COLUMN chunks JSONB;
ALTER TABLE episodes ADD COLUMN chunk_embeddings BYTEA;
