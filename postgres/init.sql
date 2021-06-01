CREATE TABLE IF NOT EXISTS public.users (
	user_id int8 NOT NULL,
    name text NOT NULL,
	key_salt text NOT NULL,
	is_mod bool NOT NULL DEFAULT false,
	is_banned bool NOT NULL DEFAULT false,
	CONSTRAINT users_pk PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS public.projects (
    project_name text NOT NULL,
    position_x int4 NOT NULL,
    position_y int4 NOT NULL,
    project_priority int4 NOT NULL,
    base64_image text NOT NULL,
);
