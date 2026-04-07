-- name: create_room(name, max_members, created_by)<!
insert into room (name, max_members, created_by)
values (:name, :max_members, :created_by)
returning *;


-- name: get_room_by_id(room_id)^
select *
from room
where id = :room_id;


-- name: update_room_data(name, max_members, room_id)<!
update room
set name        = coalesce(:name, name),
    max_members = coalesce(:max_members, max_members)
where id = :room_id
returning *;


-- name: delete_room_by_id(id)!
delete
from room
where id = :id;


-- name: add_user_to_room(room_id, user_id)<!
insert into room_user (room_id, user_id)
values (:room_id, :user_id)
on conflict (room_id, user_id) do nothing
returning id;


-- name: add_file_to_room(path_to_file, user_id, room_id)!
update room_user
set path_to_file = :path_to_file
where user_id = :user_id
  and room_id = :room_id;


-- name: get_room_user_id(room_id, user)^
select *
from room_user
where room_id = :room_id
  and user_id = :user;


-- name: get_all_room_user_id(user_id)<!
select *
from room_user
where user_id = :user_id;

-- name: get_room_members(room_id)<!
select u.id, u.username, u.email, ru.created_at
from room_user ru
         join "user" u on ru.user_id = u.id
where ru.room_id = :room_id;
