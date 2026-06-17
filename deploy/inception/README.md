# Deploying INCEpTION

[INCEpTION](https://github.com/inception-project/inception) is an open-source,
web-based text-annotation platform. In the context of this repository it is
useful as the **human annotation front-end** for clinical notes: annotators can
mark up MRSA-related risk signals, and the resulting annotations can be exported
and fed back into the rule-based extraction / prediction pipeline.

This directory provides two reproducible ways to deploy INCEpTION, both pinned
to version **40.6**.

| Method | When to use | Needs |
| ------ | ----------- | ----- |
| **Standalone JAR** (`run-standalone.sh`) | Single-node, quick start, or restricted networks where container CDNs are blocked | Java 17+ (21 recommended), curl |
| **Docker Compose** (`docker-compose.yml`) | Production / multi-user, persistent MariaDB | Docker + Docker Compose |

After startup the UI is available at `http://localhost:8080/`.
The default first-run account is **`admin` / `admin`** — you are prompted to
change the password on first login.

---

## Option A — Standalone JAR (recommended for this environment)

```bash
cd deploy/inception
./run-standalone.sh
```

This downloads the official standalone executable JAR from GitHub Releases into
`deploy/inception/dist/` (git-ignored) and runs it with an embedded server and
embedded database. No external database is required.

Configurable via environment variables:

```bash
INCEPTION_PORT=9090 \
INCEPTION_HOME=/data/inception \
JAVA_OPTS="-Xmx4g -Djava.awt.headless=true" \
./run-standalone.sh
```

`INCEPTION_HOME` holds the document repository, embedded database, settings, and
logs — back this directory up to preserve projects and annotations.

## Option B — Docker Compose (recommended for production)

```bash
cd deploy/inception
cp .env.example .env          # then edit DBPASSWORD etc.
docker compose up -d
docker compose logs -f app    # watch the boot log
```

Stop with `docker compose down` (named volumes `app-data` and `db-data` keep
your data). This runs INCEpTION against a dedicated MariaDB 11.4 container, which
is the supported configuration for multi-user / production use.

---

## Verified deployment

This setup was deployed and verified in this environment using the **standalone
JAR** method:

- Downloaded `inception-app-webapp-40.6-standalone.jar` (~334 MB) from the
  official GitHub release `inception-40.6`.
- Started on Java 21; boot completed in ~31 s
  (`Started INCEpTION in 31.332 seconds`).
- The web UI responded on `http://localhost:8080/` (login page `HTTP 200`,
  `<title>INCEpTION - Log in</title>`).

> **Note on the Docker method in restricted networks:** in sandboxed
> environments the container **image CDNs** (`pkg-containers.githubusercontent.com`
> for ghcr.io and `production.cloudfront.docker.com` for Docker Hub) may be
> blocked even when the registry API endpoints are reachable, so
> `docker pull` fails while downloading image layers (`403 Forbidden`).
> GitHub Release assets remain reachable, so the **standalone JAR** method works
> where the Docker method does not. Use Docker Compose on networks with normal
> outbound access.

## References

- Project: https://inception-project.github.io/
- Releases: https://github.com/inception-project/inception/releases
- Admin guide (Docker / standalone): https://inception-project.github.io/releases/40.6/docs/admin-guide.html
