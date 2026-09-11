-- Run once in the Supabase SQL editor for a new project.
-- Matches shared/db.py and shared/models.py exactly — if you rename a
-- column here, update both of those files too.

create extension if not exists "pgcrypto";

create table if not exists runs (
  id            uuid primary key,
  run_date      date not null,
  status        text not null default 'running', -- running / done / done_email_failed / failed
  collected_n   int not null default 0,
  reviewed_n    int not null default 0,
  selected_n    int not null default 0,
  error_message text,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz
);
create index if not exists idx_runs_run_date on runs (run_date);

create table if not exists articles (
  id            uuid primary key,
  run_id        uuid references runs (id),
  title         text not null,
  source        text,
  published_at  timestamptz,
  url           text not null,
  url_hash      text not null,
  tier          text not null default 'collected', -- collected / reviewed / selected
  created_at    timestamptz not null default now()
);
create index if not exists idx_articles_run_id on articles (run_id);
create index if not exists idx_articles_url_hash on articles (url_hash);
create index if not exists idx_articles_tier on articles (tier);

create table if not exists evaluations (
  article_id      uuid primary key references articles (id),
  base_score      int,
  bonus_score     int,
  final_score     int,
  tags            text[] not null default '{}',
  is_duplicate    boolean not null default false,
  duplicate_of    uuid references articles (id),
  is_ad           boolean not null default false,
  summary         text,
  interpretation  text,
  application     text,
  insight_quote   text,
  reject_reason   text
);

create table if not exists feedback (
  id          uuid primary key default gen_random_uuid(),
  article_id  uuid not null references articles (id),
  rating      text not null check (rating in ('good', 'bad')),
  rated_at    timestamptz not null default now()
);
create index if not exists idx_feedback_article_id on feedback (article_id);

create table if not exists tag_weights (
  tag                text primary key,
  good_count         int not null default 0,
  total_count        int not null default 0,
  weight_adjustment  numeric not null default 0,
  updated_at         timestamptz not null default now()
);

create table if not exists kakao_sends (
  id            uuid primary key default gen_random_uuid(),
  sent_at       timestamptz not null default now(),
  article_ids   uuid[] not null default '{}',
  status        text not null, -- success / failed
  error_message text
);

-- Single-row table (id is always 1) holding the encrypted Kakao token pair.
create table if not exists kakao_tokens (
  id            int primary key default 1,
  access_token  text not null,
  refresh_token text not null,
  expires_at    text
);

-- Row Level Security: this project is accessed only via the service-role
-- key from the pipeline/web backend, never from the browser directly, so
-- RLS stays enabled with no public policies (default-deny).
alter table runs enable row level security;
alter table articles enable row level security;
alter table evaluations enable row level security;
alter table feedback enable row level security;
alter table tag_weights enable row level security;
alter table kakao_sends enable row level security;
alter table kakao_tokens enable row level security;
