DB_URL=postgres://postgres:postgres@localhost:5432/sync-studio?sslmode=disable

migrate-up:
	migrate -path ./migrations -database "$(DB_URL)" up

migrate-down:
	migrate -path ./migrations -database "$(DB_URL)" down

migrate-create:
	migrate create -ext sql -dir ./migrations -seq $(name)

migrate-version:
	migrate -path ./migrations -database "$(DB_URL)" version

migrate-force:
	migrate -path ./migrations -database "$(DB_URL)" force $(version)

start-server:
	uvicorn main:app --reload