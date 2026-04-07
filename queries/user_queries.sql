-- name: get_user_by_id(id)^
select *
from "user"
where id = :id;


-- name: create_user(email, username, role_id, yandex_id)<!
insert into "user"(email, username, role_id, yandex_id)
values (:email, :username, :role_id, :yandex_id)
returning *;


-- name: update_user_data(email, username, role_id, id)<!
update "user"
set email    = coalesce(:email, email),
    username = coalesce(:username, username),
    role_id  = coalesce(:role_id, role_id)
where id = :id
returning *;


-- name: get_user_by_email(email)^
select *
from "user"
where email = :email;


-- name: get_user_by_username(username)^
select *
from "user"
where username = :username;


-- name: delete_user(id)!
delete
from "user"
where id = :id;

-- name: get_user_by_yandex_id(yandex_id)^
select *
from "user"
where yandex_id = :yandex_id;


-- name: is_user_admin(user_id)^
SELECT r.is_superuser
FROM "user" u
         JOIN role r ON u.role_id = r.id
WHERE u.id = :user_id;


-- name: is_user_staff(user_id)^
SELECT r.is_staff
FROM "user" u
         JOIN role r ON u.role_id = r.id
WHERE u.id = :user_id;