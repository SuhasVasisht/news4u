CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug varchar(120) NOT NULL UNIQUE,
  name text NOT NULL,
  homepage_url text,
  icon_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS topics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug varchar(120) NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS articles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  external_id text NOT NULL,
  title text NOT NULL,
  summary text NOT NULL,
  author text,
  url text NOT NULL,
  image_url text,
  published_at timestamptz NOT NULL,
  content_text text NOT NULL,
  score real NOT NULL DEFAULT 0,
  search_document text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT articles_source_external_unique UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS articles_published_at_idx ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS articles_source_idx ON articles (source_id);

CREATE TABLE IF NOT EXISTS article_topics (
  article_id uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  topic_id uuid NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  PRIMARY KEY (article_id, topic_id)
);

CREATE TABLE IF NOT EXISTS article_state (
  article_id uuid PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
  is_read boolean NOT NULL DEFAULT false,
  read_at timestamptz,
  is_saved boolean NOT NULL DEFAULT false,
  saved_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_preferences (
  source_id uuid PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  is_hidden boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS topic_preferences (
  topic_id uuid PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
  is_muted boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_preferences (
  id smallint PRIMARY KEY DEFAULT 1,
  theme varchar(20) NOT NULL DEFAULT 'system',
  feed_density varchar(20) NOT NULL DEFAULT 'comfortable',
  open_original_in_new_tab boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now()
);
