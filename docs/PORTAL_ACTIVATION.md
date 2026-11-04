# Student and Parent Portal Activation

Chikoro Digital uses Supabase Auth for all portal sign-ins. A confirmed Supabase email alone does not grant access: the account must also be linked to a school record through a one-time activation PIN.

## Student activation

1. A school staff member enrols the learner through `POST /students` and supplies `student_email` using the email address the learner will use in Supabase Auth.
2. The API creates the local student identity and returns `portal_email` and a one-time eight-digit `pin`. Share the PIN privately with the learner.
3. The learner opens `/portal/student-register`, creates a Supabase Auth account using the same email address, and confirms the email.
4. The learner enters the PIN at `/portal/activate?type=student`.
5. The API links the verified Supabase identity to the student profile and consumes the PIN. The learner can then sign in at `/portal/login`.

Student activation PINs expire after 30 days. If a PIN expires or is lost, an owner or headmaster can issue a fresh one with `POST /students/{student_id}/activation-pin`.

## Parent / guardian activation

1. The learner must have a guardian contact with an email address recorded by the school.
2. A school owner or headmaster obtains the `guardian_contact_id` returned when the learner is enrolled.
3. Using a Supabase-authenticated school administrator session, call:

   `POST /students/{student_id}/guardians/{contact_id}/activation-pin`

4. Share the returned eight-digit PIN privately with the guardian. Do not place it in public notes, tickets, or logs.
5. The guardian opens `/portal/register`, creates a Supabase Auth account using the same email address recorded by the school, and confirms the email.
6. The guardian enters the PIN at `/portal/activate?type=parent`.
7. The API verifies the email and PIN, creates the trusted parent profile, inserts the verified `guardian_links` relationship, and consumes the PIN.

Parent activation PINs expire after seven days. Failed activation attempts are rate-limited; issue a fresh PIN through the school administrator if the limit is reached or the PIN expires.

## Required configuration

- Configure Supabase Auth's allowed redirect URLs to include the deployed portal URL ending in `/portal/activate`, plus the local development URL when needed.
- The FastAPI `DATABASE_URL` must connect to the same Supabase Postgres project that contains `auth.users`, `public.profiles`, `public.guardian_links`, and the Chikoro school tables. The activation endpoints intentionally do not use the browser's Supabase service-role privileges.
- Keep the Supabase service-role key and the administrator bootstrap token server-side only. Never expose either through a `NEXT_PUBLIC_*` variable.
- The activation PIN is returned once to the authenticated school staff member. Deliver it directly to the intended learner or guardian.

## Access boundaries

Parent APIs return only active learners reached through an active, verified guardian link in the same school. Student APIs resolve the student through the verified Supabase profile and the local student mapping. Browser roles have no direct grants to school data tables; protected school-data access goes through FastAPI.
