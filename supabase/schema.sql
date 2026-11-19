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

-- ================= C2 : amis =================
-- Chaque profil a un code ami (8 caractères). Le partager = accepter l'amitié : celui qui l'utilise devient ami, des deux côtés.
alter table public.profiles add column if not exists code text unique default upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8));
update public.profiles set code = upper(substr(md5(random()::text || id::text), 1, 8)) where code is null;

create table if not exists public.friends (
  a uuid not null references auth.users(id) on delete cascade,
  b uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (a, b),
  check (a < b)
);
alter table public.friends enable row level security;
drop policy if exists "amis : les miens" on public.friends;
create policy "amis : les miens" on public.friends for select to authenticated
  using ((select auth.uid()) in (a, b));
revoke all on public.friends from anon;
grant select on public.friends to authenticated;

create or replace function public.is_friend(other uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.friends f
    where f.a = least((select auth.uid()), other) and f.b = greatest((select auth.uid()), other));
$$;

-- Mes amis voient les treks que je partage (share = 'friends'), jamais les autres.
drop policy if exists "treks : partagés par mes amis" on public.treks;
create policy "treks : partagés par mes amis" on public.treks for select to authenticated
  using (share = 'friends' and not deleted and public.is_friend(user_id));

create or replace function public.add_friend(friend_code text) returns table (id uuid, name text)
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f uuid;
begin
  if me is null then raise exception 'non_connecte'; end if;
  select p.id into f from public.profiles p where p.code = upper(trim(friend_code));
  if f is null then raise exception 'code_inconnu'; end if;
  if f = me then raise exception 'code_perso'; end if;
  insert into public.friends (a, b) values (least(me, f), greatest(me, f)) on conflict do nothing;
  return query select p.id, p.name from public.profiles p where p.id = f;
end $$;

create or replace function public.my_friends() returns table (id uuid, name text, since timestamptz)
language sql stable security definer set search_path = '' as $$
  select p.id, p.name, f.created_at from public.friends f
  join public.profiles p on p.id = case when f.a = (select auth.uid()) then f.b else f.a end
  where (select auth.uid()) in (f.a, f.b)
  order by p.name;
$$;

create or replace function public.remove_friend(other uuid) returns void
language sql security definer set search_path = '' as $$
  delete from public.friends where a = least((select auth.uid()), other) and b = greatest((select auth.uid()), other);
$$;

revoke all on function public.is_friend(uuid), public.add_friend(text), public.my_friends(), public.remove_friend(uuid) from public, anon;
grant execute on function public.is_friend(uuid), public.add_friend(text), public.my_friends(), public.remove_friend(uuid) to authenticated;

-- ================= C3 : suivi partagé =================
-- Photos choisies une par une, réduites (≤ 1600 px), dans un espace privé : dossier = identifiant du compte.
-- Lisibles par leur auteur et ses amis seulement.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', false, 1572864, array['image/jpeg'])
on conflict (id) do nothing;

drop policy if exists "photos : les miennes" on storage.objects;
create policy "photos : les miennes" on storage.objects for all to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);

create or replace function public.is_friend_txt(other text) returns boolean
language sql stable security definer set search_path = '' as $$
  select other ~ '^[0-9a-f-]{36}$' and public.is_friend(other::uuid);
$$;
drop policy if exists "photos : celles de mes amis" on storage.objects;
create policy "photos : celles de mes amis" on storage.objects for select to authenticated
  using (bucket_id = 'photos' and public.is_friend_txt((storage.foldername(name))[1]));
revoke all on function public.is_friend_txt(text) from public, anon;
grant execute on function public.is_friend_txt(text) to authenticated;

-- « Je suis ici » : la dernière position partagée de chacun, visible de ses amis.
create table if not exists public.checkins (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  lat double precision not null check (lat between -90 and 90),
  lon double precision not null check (lon between -180 and 180),
  at timestamptz not null default now()
);
alter table public.checkins enable row level security;
drop policy if exists "position : la mienne" on public.checkins;
create policy "position : la mienne" on public.checkins for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
drop policy if exists "position : celle de mes amis" on public.checkins;
create policy "position : celle de mes amis" on public.checkins for select to authenticated
  using (public.is_friend(user_id));
revoke all on public.checkins from anon;
grant select, insert, update, delete on public.checkins to authenticated;
