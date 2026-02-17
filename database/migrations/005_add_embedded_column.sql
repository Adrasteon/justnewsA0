ALTER TABLE articles ADD COLUMN embedded BOOLEAN DEFAULT 0;
CREATE INDEX idx_articles_embedded ON articles(embedded);
