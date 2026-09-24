# Media storage

How coin photos and avatars are stored, processed, shown and protected. Schema of
`media_files`: `data-model.md`. Visibility rules summarised in `../AGENTS.md`, "Image
provenance".

---

## Storage

S3-compatible object storage — **MinIO** in Docker Compose, locally and on the server.
Any S3 provider (R2, B2) would work without code changes.

One bucket, keys by owner of the image:

```
catalog/{catalog_item_id}/{role}/{name}_{300|600|1200}.webp               catalog photos
users/{user_id}/{collection_item_id}/{role}/{name}_{300|600|1200}.webp    a user's own photos
users/{user_id}/avatar/{sha256[:12]}_256.webp                              profile picture
```

The size is part of the key so a bucket listing is readable and a stale variant can't hide
behind a meaningless name (`app/core/media_keys.py`). The database stores **keys only**,
never full URLs — the storage domain can change.

`media_files` separates the two ways an image can exist:

```
storage_key   -- set when the file is in our storage
external_url  -- set when it's a link to someone else's server (a hotlink)
CHECK (storage_key IS NOT NULL OR external_url IS NOT NULL)
```

Some catalog rows imported from uCoin are still hotlinks (`external_url` only). The
frontend neither proxies nor retries them; an unreachable hotlink looks the same as no
photo (`frontend/src/shared/ui/CoinImage.tsx`). Downloading them is not implemented, and
downloading wouldn't change their rights (below).

## Provenance and rights

Storing an image and showing it to everyone are different things. Every `media_files`
row has a `source`, plus `license` and `attribution` when known:

| `source` | What it is | Who sees it |
|---|---|---|
| `nbu` | official NBU catalog photos | everyone |
| `ua_coins` | ua-coins.info photos, used where NBU has none | everyone, with attribution |
| `manual` | added by an admin (e.g. photos of a draft under review) | everyone |
| `user_upload` | photos a user took of their own coin | the owner only |
| `ucoin` | uCoin images, hotlinked or downloaded | only the user who imported them |

Public sources are `PUBLIC_SOURCES` in `app/repositories/media.py`; every other row is
returned only when `owner_id` is the viewer. On a card, a `ucoin` image is never shown to
anyone else — they get the placeholder. Copying a uCoin image into our storage doesn't
change `source`: we don't own the rights.

`attribution` is always filled when the source requires it and is shown under the image.
For Ukrainian coins this matters: NBU allows use of its materials only with a link to the
source, and `coin-parser` sets both NBU and ua-coins attributions when it loads photos.

**Where Ukrainian photos come from** (`coin-parser` picks, in this order): the NBU
full-size PNG (1600 px) → the ua-coins 600 px WebP → the NBU 198 px preview. The 600 px
secondary source ranks above the tiny official preview on purpose: quality matters more
than source preference here.

### User photos belong to the collection item

A `user_upload` row always hangs off `collection_item_id` + `owner_id`, **never** off
`catalog_item_id`. `app/services/collection_photos.py` is the only writer of
`user_upload` rows and can't write anything else, so a user's photo can never attach to a
catalog record or to another account. To show "my own photo" on a catalog card, the
repository joins through the owner's `collection_items`
(`MediaRepository.owned_instance_media_for_catalog_items`).

A new personal position's photos are held in the browser until the purchase is created,
then uploaded against the new collection item — there's no server-side object to hold
them earlier.

## Choosing the card photo

Several rows can exist per role. Per role (`obverse` / `reverse`), the highest-ranked row
the viewer may see wins (`MediaUrlBuilder.pick_catalog_images`); among equals, the
newest:

1. the viewer's own `user_upload` of any of their purchases of the item;
2. `nbu` or `manual`;
3. `ua_coins`;
4. `ucoin` — only ever present for its importer;
5. otherwise a placeholder.

The catalog listing, the coin card and the collection listing share this function
(`images_by_catalog_item`), so the screens can't disagree about which photo wins.

## Roles

`obverse`, `reverse`, `edge`, `additional` exist in the enum. Upload endpoints accept
`obverse` and `reverse` only — one photo per role per collection item (or per catalog
item for admin uploads).

## Processing on upload

`app.core.images.process_image`, Pillow only. The same path serves user photos
(`collection_photos.py`) and admin photos of catalog drafts (`catalog_photos.py`).

1. Verify it's an image by content, not extension; accept JPEG / PNG / WebP.
2. Limits: 12 MB, 4000 px on the longer side.
3. **Strip all metadata** (EXIF with geotags, ICC) by copying pixels into a blank canvas.
4. Remove the background if the photo qualifies (below).
5. Save **three sizes** — 300, 600, 1200 px on the longer side, WebP quality 80.
   Nothing is upscaled: a 600 px source yields two variants, and `variants` lists exactly
   what was stored.
6. Record `sha256` of the **source** file (identifies it upstream and tells a re-run
   nothing changed), plus `width`, `height`, `size_bytes`, `mime_type`, `variants`.

The source file isn't kept: coins are small and round, 1200 px is plenty, and NBU PNGs
weigh 3–4 MB each.

**Why three sizes.** A listing shows a coin at ~150 px, a card at ~300, the lightbox as
large as the screen allows. Pages pick the matching size and offer the next one up via
`srcset` for dense screens. Rows from before the three-size layout have no `variants`;
the URL builder answers with the keys they do have.

Replacing a photo writes the new object, points the row at it, and deletes the old
objects last, so a failure part-way never leaves a row naming a missing key. Deleting a
photo removes the row and its objects immediately.

### Cropping in the browser

A user's coin photo is cut to a circle **in the browser**; the server receives a
finished RGBA image. The editor (`CoinPhotoCropDialog.tsx` over the shared
`CropDialog.tsx`) offers zoom up to 5×, rotation ±15°, and a soft blur warning (variance
of the Laplacian over the visible circle, `blurCheck.ts`) that never blocks saving.
`rotatedCircleCrop.ts` renders the rotated source, cuts the selected area, downsizes to
at most 1600 px and masks the circle exactly at its edge. Output is WebP with alpha; if
the browser can't produce real `image/webp`, PNG — never JPEG, which has no alpha.

On the server nothing special happens: an already transparent (non-RGB) image skips
background removal, and Pillow keeps alpha through every variant
(`test_a_transparent_upload_keeps_its_alpha_channel_through_every_variant`).

## Avatars

A profile picture is the one image **outside `media_files`**: that table requires a
catalog or collection item and a provenance, neither of which a portrait has. The key
lives in `users.avatar_key`; whoever sees the profile sees the avatar.

One size, 256 px square (the UI shows it at 26–72 css px, so 256 covers 3× screens). The
key name is the sha256 of the source, so replacing the picture changes the URL and no
cached copy keeps serving the old face. The browser crops (circular mask, drag, zoom
up to 3×), but the server re-validates and center-crops to a square anyway — the endpoint
takes raw bytes from any client. Background removal doesn't apply to avatars.

## Background removal

Classic, no ML: `app/services/media_background.py` (Pillow + stdlib) and the batch
script `backend/scripts/remove_photo_backgrounds.py`. It runs on every upload
(`process_image(remove_background=True)`); a special path that must keep bytes exactly
as given passes `False`.

**Rule: cut only what we're sure of — a uniform background and a round object.**

- **Already transparent input is left alone.** Before anything else, if more than 0.5%
  of pixels have alpha < 250 (`ALREADY_TRANSPARENT_FRACTION_MIN`), the verdict is
  `skip:already_transparent`. Some NBU sources are alpha 0 over an arbitrary black matte;
  this check must see the original alpha before any conversion to RGB, or the matte
  reads as a black background and hidden junk gets exposed.
- **Background kind.** All four corners must be near-white (conservative per-channel
  threshold and low channel spread, so cream or bluish backgrounds don't pass) or
  near-black (≈30/255 per channel, same spread rule — proofs are often shot on black
  velvet). Otherwise `skip:not_white_bg` (name kept for comparable reports).
- **Flood fill** from the image border builds the background mask; small noise is removed
  morphologically. The dark branch uses a much stricter tolerance: a proof's mirror field
  reflects the same black studio, and a loose tolerance would eat into the coin.
- **Border:** background must cover ≥ 75% of the frame perimeter, else
  `skip:object_touches_border`.
- **One object:** exactly one connected component, else `skip:fragments`.
- **Roundness:** object area / bounding-box area in 0.60–0.87 (a disc is ≈0.785, a
  rectangle 1.0). Above → `skip:not_round` (blister packs, souvenir packaging); below →
  `skip:odd_shape`.
- **Cut:** mask → alpha channel, 1–2 px feathered edge. Verdict `cut` (white) or
  `cut:dark`.
- **Trim:** crop to the alpha bounding box plus a uniform ~2% margin (≥ 2 px), so every
  round coin fills its frame the same way under `object-fit: contain`.

Colored, textured, uneven or mid-grey backgrounds and rectangular objects are never
touched — a deliberate limit, not a classifier gap.

**Keys and rollback.** A cut image is stored under a **new** key: the old base plus
`-nobg` (`…/ab12cd34_1200.webp` → `…/ab12cd34-nobg_1200.webp`) for every size. The
original is never deleted or overwritten, so the old→new key pair is the rollback plan.
The `-nobg` suffix is also the "already processed" marker — there's no schema column for
it.

### Runbook

Never run two passes of the script at once (any mode) — they read and write the same
`media_files` rows. Run long passes in tmux. Reports go to `--out-dir`
(`migration-reports/` by default); mount it when running in the container:

```bash
R="-v /home/deploy/coinkeeper/migration-reports:/app/migration-reports"
docker compose run --no-deps $R api python scripts/remove_photo_backgrounds.py --dry-run   # classify, write nothing
docker compose run --no-deps $R api python scripts/remove_photo_backgrounds.py --apply     # cut the cut/cut:dark rows
docker compose run --no-deps $R api python scripts/remove_photo_backgrounds.py --apply --only-ids 101,102
```

`--dry-run` writes `nobg-review.csv` (UTF-8 with BOM, opens in Excel; per-row metrics
`bgKind`, `borderBackgroundFraction`, `circularity`, `cornerWhiteness` for tuning
thresholds) and `nobg-review.html` (before/after sheets for `cut` and `cut:dark`, skips
by reason). Review `cut:dark` especially carefully. Re-runs are idempotent: rows with
`-nobg` are skipped without touching storage. Roll back a row by setting
`storage_key` / `thumbnail_key` / `variants` back to the old keys from the CSV.

Two maintenance modes walk only rows already marked `-nobg`:

- **`--trim`** re-trims cut images made before the trim step existed: downloads the
  largest `-nobg` variant, applies the alpha trim, and rewrites all sizes under the same
  key if the size changed (`trim-review.csv` / `.html`).
- **`--revert-transparent-originals`** undoes cuts of originals that were already
  transparent (the matte problem above). For each row it checks the **original**
  (without `-nobg`) with the same transparency test; if the original was transparent,
  the row is pointed back at the original's keys — missing original sizes are rebuilt
  from the largest surviving one; if no original size survives, the row is left alone and
  reported as `missing_original`. `-nobg` objects are not deleted
  (`revert-review.csv`).

Both accept `--dry-run`, `--apply`, `--only-ids`, and are idempotent.

## Serving

The API never streams image bytes. Every stored file is returned as a **presigned GET
URL** (1 hour, `MediaUrlBuilder`), issued only for rows the viewer may see; hotlinks are
returned as they are.

### `S3_PUBLIC_ENDPOINT`

The backend reaches MinIO at `S3_ENDPOINT=http://minio:9000`, a Docker-network name the
browser can't resolve, and boto3 signs URLs for whatever host it was given. So when
`S3_PUBLIC_ENDPOINT` is set (`https://<domain>/media`), a second boto3 client is used
**only for signing** (`ObjectStorage.presign_client` in `app/core/storage.py`); reads and
writes stay on `S3_ENDPOINT`. Locally it's unset: `docker-compose.dev.yml` publishes
MinIO on `localhost:9000`.

Behind the reverse proxy, `/media/<bucket>/<key>` must reach MinIO as
`/<bucket>/<key>` (path-style addressing). Caddy strips the prefix with `handle_path`
(`infra.md`, "Caddy") and must **not** rewrite `Host`: the signature covers it
(`X-Amz-SignedHeaders=host`).

A public-read bucket for catalog photos was considered and rejected: it would need two
serving paths (public and presigned) in one URL builder or a second bucket, while
`S3_PUBLIC_ENDPOINT` solves the problem without changing the access model.
