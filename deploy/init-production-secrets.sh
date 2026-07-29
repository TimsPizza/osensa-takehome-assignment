#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
secrets_directory="$repository_root/deploy/secrets"
password_file="$secrets_directory/mosquitto-passwords"
image="eclipse-mosquitto:2.1.2-alpine"
users="restaurant-backend restaurant-console table-1 table-2 table-3 table-4"

chmod 700 "$secrets_directory"

for user in $users; do
	secret_path="$secrets_directory/mqtt-${user}-password"
	if [ -e "$secret_path" ] || [ -e "$password_file" ]; then
		echo "Production secrets already exist; refusing to overwrite them." >&2
		echo "Remove the files in deploy/secrets intentionally before rotating credentials." >&2
		exit 1
	fi
done

temporary_directory=$(mktemp -d "$secrets_directory/.init.XXXXXX")
trap 'rm -rf "$temporary_directory"' EXIT HUP INT TERM
temporary_password_file="$temporary_directory/mosquitto-passwords"

umask 077
for user in $users; do
	openssl rand -base64 32 | tr -d '\n' >"$temporary_directory/mqtt-${user}-password"
done

first=1
for user in $users; do
	secret_path="$temporary_directory/mqtt-${user}-password"
	if [ "$first" -eq 1 ]; then
		create_flag="-c"
		first=0
	else
		create_flag=""
	fi

	secret_value=$(cat "$secret_path")
	printf '%s\n%s\n' "$secret_value" "$secret_value" | docker run --rm -i \
		--user "$(id -u):$(id -g)" \
		-v "$temporary_directory:/run/generated-secrets" \
		"$image" \
		mosquitto_passwd $create_flag /run/generated-secrets/mosquitto-passwords "$user"
done

chmod 600 "$temporary_directory"/mqtt-*-password "$temporary_password_file"
# File-backed Compose secrets retain their host permissions. These two files
# must be readable by the non-root Mosquitto and backend container users. The
# parent secrets directory remains mode 0700 on the host.
chmod 644 \
	"$temporary_password_file" \
	"$temporary_directory/mqtt-restaurant-backend-password"
for generated_file in "$temporary_directory"/*; do
	mv "$generated_file" "$secrets_directory/"
done

echo "Generated production credentials in deploy/secrets."
echo "Read the console password from deploy/secrets/mqtt-restaurant-console-password."
