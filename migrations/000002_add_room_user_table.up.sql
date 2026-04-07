create table if not exists room_user (
    id serial primary key,
    user_id integer references "user" (id) on delete cascade,
    room_id integer references room(id) on delete cascade,
    created_at  timestamptz  not null default now(),
    updated_at  timestamptz  not null default now(),
    path_to_file varchar(250),
    unique(user_id,room_id)
);


create trigger room_user_update_trigger
    before update
    on room_user
    for each row
execute procedure set_updated_columns();