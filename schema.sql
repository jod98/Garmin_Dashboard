-- Run this once in the Supabase SQL editor (free tier project)

create table if not exists weekly_plans (
    id serial primary key,
    week_start date not null unique,
    sessions jsonb not null,        -- list of session objects (see plan_generator.py for
                                     -- the shape); each session may carry a
                                     -- "garmin_workout_id" once pushed to Garmin Connect
                                     -- (see garmin_client.sync_workouts)
    rationale text,                 -- short explanation the AI gave for this week's plan
    created_at timestamptz default now()
);

create table if not exists weekly_feedback (
    id serial primary key,
    week_start date not null unique,   -- the week being reported on
    energy_level int,                  -- 1-5
    soreness_level int,                -- 1-5
    injury_flag boolean default false,
    injury_notes text,
    missed_sessions text,              -- free text or comma list
    notes text,
    submitted_at timestamptz default now()
);

create table if not exists athlete_profile (
    id int primary key default 1,
    goal text,                 -- e.g. "sub-50 10k by October"
    constraints text,          -- e.g. "max 4 sessions/week, no pool access Mondays"
    updated_at timestamptz default now()
);

insert into athlete_profile (id, goal, constraints)
values (1, 'General fitness and endurance improvement', 'Edit this row with your real goal and constraints')
on conflict (id) do nothing;
