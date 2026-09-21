# Statamic production container packaging

Packaging only: not an application fork. The Dockerfile downloads unchanged starter
`statamic/statamic` v6.5.1 at `341050105099ead5f0c0db39f5f7d2e7f3239012`.
The committed Composer lock selects CMS v6.33.0 and Laravel v13.32.0.
Composer's upstream install scripts publish the upstream control-panel assets.

Statamic retains its own [license](https://github.com/statamic/cms/blob/6.x/LICENSE.md).
All upstream notices ship in the image. Core is the default, one administrator and one
content form. Licensing code, calls and restrictions are unchanged. Pro production
use requires an appropriate per-site license. This packaging is not vendor-endorsed.

## Runtime

Set APP_KEY (Laravel base64 key), APP_URL, STATAMIC_ADMIN_EMAIL and a randomly generated
STATAMIC_ADMIN_PASSWORD of at least 16 characters. Mount one named volume at /data.
Bootstrap creates the first administrator before HTTP starts and never resets an
existing account. No public first-owner claim flow is needed. Rotate passwords in
Statamic; editing the bootstrap environment does not change existing credentials.
Bind port 80 to host loopback behind a trusted TLS proxy. The proxy must overwrite
X-Forwarded-Proto; do not expose this container directly to untrusted traffic.

## Data and upgrades

/data contains content, users, resources (blueprints, fieldsets, views), config,
storage (sessions, caches, forms, private/public files) and public/assets. These paths
are seeded only if absent, then symlinked from image-owned application code. Vendor,
bootstrap and app code are never volume-masked, so a new image really updates code.
User-owned config/views are never overwritten: review new upstream configuration
requirements explicitly before each upgrade. No in-container Composer upgrades.

Stop the application before archiving the complete /data volume. Back up APP_KEY
and deployment environment separately and securely. Restore the whole volume into
a fresh empty volume with the same image and key before restarting. Do not combine
partial backups from different times. Archives contain user password hashes and
private content. Roll back image plus a coordinated pre-upgrade data snapshot.

## Build and qualification

`docker build -t ghcr.io/neobuilds/statamic:6.33.0-xcloud.3 .`

Release CI builds on native `ubuntu-24.04` (amd64) and `ubuntu-24.04-arm`
(arm64), without QEMU. Each digest must pass anonymous pull, fresh startup,
HTTPS administrator login with secure cookies, control-panel content/media
creation and readback, restart, forced recreation, and stopped-volume backup
restored into an empty replacement volume. Every persistence phase reauthenticates.
Disposable containers, volumes, TLS keys and credentials are removed. Sanitized
JSON gate results and image configs are retained as Actions artifacts.

Only after both native suites pass does the publisher assemble the multiarch
index. Dispatch `release.yml` with a **new** packaging version; both preflight
and publication reject an already-existing tag. Tags through `6.33.0-xcloud.2`
remain amd64-only and are never overwritten. Registry verification anonymously
hashes every platform's config and layer blobs.

Native CI qualification is separate from managed OneClick certification, tracked
in https://github.com/xCloudDev/app-templates/pull/806.
