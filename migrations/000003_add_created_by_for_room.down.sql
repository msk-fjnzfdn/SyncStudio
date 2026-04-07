drop trigger if exists room_admin_name_unique_trigger on room;
drop function if exists check_admin_room_name;
alter table room drop column if exists created_by;