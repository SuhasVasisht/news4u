CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
  id text PRIMARY KEY,
  name text,
  email text UNIQUE,
  email_verified timestamptz,
  image text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  is_active boolean NOT NULL DEFAULT true,
  last_login_at timestamptz
);

CREATE TABLE IF NOT EXISTS accounts (
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type text NOT NULL,
  provider text NOT NULL,
  provider_account_id text NOT NULL,
  refresh_token text,
  access_token text,
  expires_at integer,
  token_type text,
  scope text,
  id_token text,
  session_state text,
  PRIMARY KEY (provider, provider_account_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  session_token text PRIMARY KEY,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_tokens (
  identifier text NOT NULL,
  token text NOT NULL,
  expires timestamptz NOT NULL,
  PRIMARY KEY (identifier, token)
);

ALTER TABLE sources ADD COLUMN IF NOT EXISTS domain text;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS stories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_headline text NOT NULL,
  canonical_summary text NOT NULL,
  normalized_headline text NOT NULL,
  fingerprint varchar(255) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'active',
  first_published_at timestamptz NOT NULL,
  last_updated_at timestamptz NOT NULL,
  importance_score real NOT NULL DEFAULT 0,
  update_count integer NOT NULL DEFAULT 0,
  source_count integer NOT NULL DEFAULT 0,
  representative_article_id uuid,
  search_document text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE articles ADD COLUMN IF NOT EXISTS story_id uuid REFERENCES stories(id) ON DELETE SET NULL;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE articles ADD COLUMN IF NOT EXISTS payload_json jsonb;
ALTER TABLE articles ADD CONSTRAINT articles_url_unique UNIQUE NULLS NOT DISTINCT (url);

CREATE TABLE IF NOT EXISTS story_articles (
  story_id uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  article_id uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  PRIMARY KEY (story_id, article_id)
);

CREATE TABLE IF NOT EXISTS daily_feed_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  feed_date date NOT NULL UNIQUE,
  generated_at timestamptz NOT NULL DEFAULT now(),
  algorithm_version varchar(64) NOT NULL,
  notes text
);

CREATE TABLE IF NOT EXISTS daily_feed_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  feed_run_id uuid NOT NULL REFERENCES daily_feed_runs(id) ON DELETE CASCADE,
  story_id uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  section varchar(32) NOT NULL,
  rank_score real NOT NULL,
  rank_position integer NOT NULL,
  compact_summary text,
  reason_json jsonb,
  CONSTRAINT daily_feed_items_unique UNIQUE (feed_run_id, story_id, section)
);

CREATE TABLE IF NOT EXISTS user_daily_feeds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  feed_date date NOT NULL,
  generated_from_feed_run_id uuid NOT NULL REFERENCES daily_feed_runs(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  cleared_at timestamptz,
  status varchar(24) NOT NULL DEFAULT 'active',
  CONSTRAINT user_daily_feeds_unique UNIQUE (user_id, feed_date)
);

CREATE TABLE IF NOT EXISTS user_daily_feed_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_daily_feed_id uuid NOT NULL REFERENCES user_daily_feeds(id) ON DELETE CASCADE,
  story_id uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  tab varchar(24) NOT NULL,
  section varchar(24) NOT NULL,
  rank_position integer NOT NULL,
  is_read boolean NOT NULL DEFAULT false,
  is_dismissed boolean NOT NULL DEFAULT false,
  is_archived boolean NOT NULL DEFAULT false,
  surfaced_reason text,
  summary_override text,
  CONSTRAINT user_daily_feed_items_unique UNIQUE (user_daily_feed_id, story_id, tab)
);

CREATE TABLE IF NOT EXISTS user_story_state (
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_read_at timestamptz,
  is_read boolean NOT NULL DEFAULT false,
  is_saved boolean NOT NULL DEFAULT false,
  is_archived boolean NOT NULL DEFAULT false,
  is_dismissed boolean NOT NULL DEFAULT false,
  is_hidden boolean NOT NULL DEFAULT false,
  archived_at timestamptz,
  carryover_count integer NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, story_id)
);

CREATE TABLE IF NOT EXISTS user_source_preferences (
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  is_hidden boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, source_id)
);

CREATE TABLE IF NOT EXISTS user_topic_preferences (
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id uuid NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  is_muted boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  theme varchar(20) NOT NULL DEFAULT 'system',
  feed_density varchar(20) NOT NULL DEFAULT 'comfortable',
  open_original_in_new_tab boolean NOT NULL DEFAULT true,
  timezone varchar(64) NOT NULL DEFAULT 'America/Los_Angeles',
  daily_reset_hour smallint NOT NULL DEFAULT 5,
  catchup_days smallint NOT NULL DEFAULT 3,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS accounts_user_id_idx ON accounts (user_id);
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions (user_id);
CREATE INDEX IF NOT EXISTS stories_last_updated_at_idx ON stories (last_updated_at DESC);
CREATE INDEX IF NOT EXISTS stories_importance_score_idx ON stories (importance_score DESC);
CREATE INDEX IF NOT EXISTS stories_fingerprint_idx ON stories (fingerprint);
CREATE INDEX IF NOT EXISTS articles_story_id_idx ON articles (story_id);
CREATE INDEX IF NOT EXISTS daily_feed_runs_date_idx ON daily_feed_runs (feed_date);
CREATE INDEX IF NOT EXISTS daily_feed_items_section_rank_idx ON daily_feed_items (feed_run_id, section, rank_position);
CREATE INDEX IF NOT EXISTS user_daily_feeds_user_date_idx ON user_daily_feeds (user_id, feed_date);
CREATE INDEX IF NOT EXISTS user_daily_feed_items_tab_rank_idx ON user_daily_feed_items (user_daily_feed_id, tab, section, rank_position);
CREATE INDEX IF NOT EXISTS user_story_state_user_flags_idx ON user_story_state (user_id, is_read, is_archived, is_saved);
CREATE INDEX IF NOT EXISTS user_story_state_user_seen_idx ON user_story_state (user_id, last_seen_at DESC);
