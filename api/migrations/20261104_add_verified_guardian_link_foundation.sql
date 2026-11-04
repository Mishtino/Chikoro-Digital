-- Parent/guardian identity mapping foundation.
-- Links are created only by trusted backend provisioning after a school verifies
-- the contact relationship. No client-side insert/update/delete is permitted.
alter table public.contacts
  add constraint contacts_id_school_id_unique unique (id, school_id);

create table if not exists public.guardian_links (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  contact_id integer not null,
  school_id integer not null references public.schools(id) on delete cascade,
  is_active boolean not null default false,
  verified_by_user_id integer references public.users(id) on delete set null,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  constraint guardian_links_contact_school_fkey
    foreign key (contact_id, school_id)
    references public.contacts(id, school_id) on delete cascade,
  constraint guardian_links_profile_contact_unique unique (profile_id, contact_id)
);

create index if not exists guardian_links_profile_active_idx
  on public.guardian_links(profile_id, is_active);
create index if not exists guardian_links_student_contact_idx
  on public.contacts(student_id, school_id);

alter table public.guardian_links enable row level security;
revoke all privileges on table public.guardian_links from anon, authenticated;
