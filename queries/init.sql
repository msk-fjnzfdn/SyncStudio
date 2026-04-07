create or replace function set_updated_columns()
    returns trigger as
$$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- -------------------------------------------------------------------------------------------------

create table if not exists role
(
    id           serial primary key,
    name         varchar(250) not null unique,
    is_superuser boolean      not null default false,
    is_staff     boolean      not null default false,
    created_at   timestamptz  not null default now(),
    updated_at   timestamptz  not null default now()
);

create trigger role_update_trigger
    before update
    on role
    for each row
execute procedure set_updated_columns();


-- -------------------------------------------------------------------------------------------------
create table if not exists "user"
(
    id         serial primary key,
    email      varchar(250) not null unique,
    username   varchar(250) not null unique,
    role_id    integer               default 3 references role (id) on delete set default,
    yandex_id varchar(250) unique,
    created_at timestamptz  not null default now(),
    updated_at timestamptz  not null default now()
);



create trigger user_update_trigger
    before update
    on "user"
    for each row
execute procedure set_updated_columns();

-- -------------------------------------------------------------------------------------------------

create table if not exists room
(
    id          serial primary key,
    name        varchar(250) not null,  -- убери unique, проверка через триггер
    max_members integer      not null check ( max_members < 40 ),
    created_by  integer references "user" (id) on delete set null,
    created_at  timestamptz  not null default now(),
    updated_at  timestamptz  not null default now()
);

create or replace function check_admin_room_name()
    returns trigger as
$$
begin
    if (select role_id from "user" where id = new.created_by) in (1, 2) then
        if exists (
            select 1 from room
            where name = new.name
              and created_by = new.created_by
              and id != coalesce(new.id, -1)
        ) then
            raise exception 'Admin already has a room with this name';
        end if;
    end if;
    return new;
end;
$$ language plpgsql;

create trigger room_admin_name_unique_trigger
    before insert or update
    on room
    for each row
execute procedure check_admin_room_name();

create trigger room_update_trigger
    before update
    on room
    for each row
execute procedure set_updated_columns();


-- -------------------------------------------------------------------------------------------------

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

