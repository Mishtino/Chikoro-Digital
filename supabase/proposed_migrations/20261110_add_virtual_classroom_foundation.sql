-- PROPOSED / STAGING ONLY. Never apply directly to production.
-- Classroom metadata only: video media and provider credentials are external.
-- Depends on public.schools, public.users and public.students.
BEGIN;

DO $classroom$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_users_school_id_id' AND conrelid='public.users'::regclass) THEN
    ALTER TABLE public.users ADD CONSTRAINT uq_users_school_id_id UNIQUE (school_id,id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_students_school_id_id' AND conrelid='public.students'::regclass) THEN
    ALTER TABLE public.students ADD CONSTRAINT uq_students_school_id_id UNIQUE (school_id,id);
  END IF;
END $classroom$;

CREATE TABLE public.classroom_settings (
  school_id integer PRIMARY KEY REFERENCES public.schools(id),
  embedded_enabled boolean NOT NULL DEFAULT false,
  external_enabled boolean NOT NULL DEFAULT false,
  recordings_enabled boolean NOT NULL DEFAULT false,
  updated_by_user_id integer NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_classroom_settings_actor FOREIGN KEY (school_id,updated_by_user_id)
    REFERENCES public.users(school_id,id)
);

CREATE TABLE public.classroom_sessions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  school_id integer NOT NULL REFERENCES public.schools(id),
  class_name varchar(80) NOT NULL,
  host_user_id integer NOT NULL,
  created_by_user_id integer NOT NULL,
  mode varchar(16) NOT NULL,
  provider varchar(32) NOT NULL,
  -- Store an opaque provider reference, not a meeting password or bearer token.
  provider_reference text NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'scheduled',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_classroom_sessions_school_id_id UNIQUE(school_id,id),
  CONSTRAINT fk_classroom_host FOREIGN KEY (school_id,host_user_id) REFERENCES public.users(school_id,id),
  CONSTRAINT fk_classroom_creator FOREIGN KEY (school_id,created_by_user_id) REFERENCES public.users(school_id,id),
  CONSTRAINT ck_classroom_class_nonempty CHECK (length(trim(class_name)) > 0),
  CONSTRAINT ck_classroom_duration CHECK (starts_at < ends_at),
  CONSTRAINT ck_classroom_mode CHECK (mode IN ('embedded','external')),
  CONSTRAINT ck_classroom_status CHECK (status IN ('scheduled','live','ended','cancelled'))
);

CREATE INDEX ix_classroom_sessions_schedule ON public.classroom_sessions(school_id,starts_at);

CREATE TABLE public.classroom_attendance_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  school_id integer NOT NULL,
  session_id bigint NOT NULL,
  student_id integer NOT NULL,
  provider_event_id varchar(255) NULL,
  event_type varchar(16) NOT NULL,
  occurred_at timestamptz NOT NULL,
  verification_state varchar(16) NOT NULL DEFAULT 'unverified',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_classroom_event_session FOREIGN KEY (school_id,session_id)
    REFERENCES public.classroom_sessions(school_id,id),
  CONSTRAINT fk_classroom_event_student FOREIGN KEY (school_id,student_id)
    REFERENCES public.students(school_id,id),
  CONSTRAINT ck_classroom_event_type CHECK (event_type IN ('join','leave')),
  CONSTRAINT ck_classroom_event_verification CHECK (verification_state IN ('verified','unverified')),
  CONSTRAINT uq_classroom_provider_event UNIQUE(school_id,session_id,provider_event_id)
);

CREATE INDEX ix_classroom_attendance_session_student
  ON public.classroom_attendance_events(school_id,session_id,student_id,occurred_at);

ALTER TABLE public.classroom_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.classroom_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.classroom_attendance_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.classroom_settings, public.classroom_sessions, public.classroom_attendance_events FROM anon, authenticated;
-- No browser-facing RLS policies or API role grants are introduced.
-- Host assignment, class enrolment, provider URL validation, webhook signatures,
-- and tenant identity MUST be implemented and verified in FastAPI before use.
COMMIT;
