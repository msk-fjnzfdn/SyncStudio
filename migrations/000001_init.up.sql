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
    password   varchar(250) not null,
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
    name        varchar(250) not null unique,
    max_members integer      not null check ( max_members < 40 ),
    created_at  timestamptz  not null default now(),
    updated_at  timestamptz  not null default now()
);

create trigger room_update_trigger
    before update
    on room
    for each row
execute procedure set_updated_columns();



