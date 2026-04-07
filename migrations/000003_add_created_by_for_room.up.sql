alter table room add column if not exists created_by integer references "user"(id) on delete set null;

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