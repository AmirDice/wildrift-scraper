/**
 * Where a memory image goes.
 *
 * Shared-album memories are photos, and photos do not belong in KV -- it stores
 * small JSON values, not megabyte images. They need a blob host. This module is
 * the single seam for that, so the album code stays unaware of which host it is.
 *
 * STATUS: not yet wired to a real store. The project has no blob dependency and
 * no storage token configured (checked before writing this). The natural fit,
 * since the site deploys on Vercel, is Vercel Blob -- one dependency
 * (`@vercel/blob`) and a `BLOB_READ_WRITE_TOKEN`. Until that decision is made
 * this refuses uploads with a clear message rather than pretending to store an
 * image it will lose. Everything AROUND the image -- the memory record, its
 * category, the banner selection, the filtering UI -- is complete and works the
 * moment `put()` below is real.
 *
 * To turn it on:
 *   1. `npm i @vercel/blob` in web-next
 *   2. add BLOB_READ_WRITE_TOKEN to the Vercel project env
 *   3. replace the body of uploadMemoryImage with the put() call shown below
 */

/** Images we accept. Kept tight: a memory is a screenshot, not an SVG payload. */
const ALLOWED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const MAX_BYTES = 8 * 1024 * 1024; // 8 MB: comfortably above any game screenshot

export type UploadResult =
  | { ok: true; url: string }
  | { ok: false; error: string; status: number };

const BLOB_ENABLED = Boolean(process.env.BLOB_READ_WRITE_TOKEN);

export function memoryUploadsEnabled(): boolean {
  return BLOB_ENABLED;
}

export async function uploadMemoryImage(
  file: { type: string; size: number; bytes: ArrayBuffer; name?: string },
  albumId: string,
): Promise<UploadResult> {
  if (!ALLOWED_TYPES.has(file.type)) {
    return { ok: false, status: 415, error: "Only PNG, JPEG, WebP or GIF images." };
  }
  if (file.size > MAX_BYTES) {
    return { ok: false, status: 413, error: "That image is over 8 MB." };
  }
  if (!BLOB_ENABLED) {
    return {
      ok: false,
      status: 501,
      error: "Image uploads are not enabled on this deployment yet.",
    };
  }

  // Wired implementation (uncomment once @vercel/blob and the token are set):
  //
  //   const { put } = await import("@vercel/blob");
  //   const key = `memories/${albumId}/${crypto.randomUUID()}`;
  //   const blob = await put(key, file.bytes, {
  //     access: "public",
  //     contentType: file.type,
  //   });
  //   return { ok: true, url: blob.url };
  //
  void albumId;
  return { ok: false, status: 501, error: "Image upload backend not configured." };
}
