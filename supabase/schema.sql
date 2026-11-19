-- Orri : base en ligne (Supabase), pour les comptes facultatifs.
-- À coller une fois dans Supabase : SQL Editor → New query → Run. Le script peut être relancé sans risque.
-- Règle d'or : chacun ne voit et ne modifie que ses propres données (Row Level Security).

-- Profil public minimal : un pseudo (pas l'e-mail)
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text not null default '' check (char_length(name) <= 40),
  created_at timestamptz not null default now()
);

-- Treks du carnet, synchronisés entre les appareils
create table if not exists public.treks (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  id text not null check (char_length(id) between 1 and 40),
  data jsonb,                                   -- le trek tel qu'il est dans le carnet (sans les images)
  deleted boolean not null default false,       -- supprimé sur un appareil : les autres le suppriment aussi
  share text not null default 'private' check (share in ('private', 'friends')),
  updated_at timestamptz not null default now(),
  primary key (user_id, id),
  check (data is null or octet_length(data::text) < 3000000)
);

create or replace function public.orri_touch() returns trigger language plpgsql as $$
begin new.updated_at = clock_timestamp(); return new; end $$;
drop trigger if exists treks_touch on public.treks;
create trigger treks_touch before insert or update on public.treks for each row execute function public.orri_touch();

alter table public.profiles enable row level security;
alter table public.treks enable row level security;

drop policy if exists "profil : le mien" on public.profiles;
create policy "profil : le mien" on public.profiles for all to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

drop policy if exists "treks : les miens" on public.treks;
create policy "treks : les miens" on public.treks for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on public.profiles, public.treks from anon;
grant select, insert, update, delete on public.profiles, public.treks to authenticated;

-- Suppression du compte par son titulaire (RGPD) : efface l'utilisateur, ses treks et son profil suivent (on delete cascade).
create or replace function public.delete_my_account() returns void
language sql security definer set search_path = '' as $$
  delete from auth.users where id = (select auth.uid());
$$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;
