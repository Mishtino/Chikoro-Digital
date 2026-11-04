alter table public.contacts
  add column guardian_activation_pin_hash varchar(255),
  add column guardian_activation_expires_at timestamptz,
  add column guardian_activated_at timestamptz;
