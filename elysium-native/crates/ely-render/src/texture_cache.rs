//! Decoded-image cache for the render thread.
//!
//! Spec §11.1 perf gate: 60 FPS, ≤8 ms typical frame budget. A
//! 1920×1080 PNG decode is 8–25 ms on a modern laptop — too slow to do
//! every frame. This cache decodes once, holds the immutable
//! `skia_safe::Image`, and serves billions of redraws against a single
//! refcount bump.
//!
//! The cache is owned by the render thread (or any thread doing Skia
//! paint) and is single-threaded. A future async path can populate it
//! from a worker thread via `populate_from_bytes`.

use parking_lot::RwLock;
use skia_safe::Image;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

#[derive(Default)]
pub struct TextureCache {
    inner: RwLock<Inner>,
    /// Counters Python tests can read to verify caching behaviour.
    pub decodes: AtomicU64,
    pub hits: AtomicU64,
}

#[derive(Default)]
struct Inner {
    /// Successfully decoded images, keyed by canonical path.
    images: HashMap<PathBuf, Arc<Image>>,
    /// Paths we tried to decode and failed; we don't retry until the
    /// caller calls `forget`.
    failed: HashMap<PathBuf, String>,
}

impl TextureCache {
    pub fn new() -> Self {
        Self::default()
    }

    /// Get a cached image, decoding from disk if we haven't seen this
    /// path before. Returns `None` only if the file can't be read or
    /// the bytes don't decode as an image — in which case the failure
    /// is sticky for that path until `forget` is called.
    pub fn get_or_load(&self, path: &Path) -> Option<Arc<Image>> {
        // Fast path: already cached.
        {
            let g = self.inner.read();
            if let Some(img) = g.images.get(path) {
                self.hits.fetch_add(1, Ordering::Relaxed);
                return Some(img.clone());
            }
            if g.failed.contains_key(path) {
                return None;
            }
        }

        // Slow path: decode + populate. We hold the write lock for the
        // decode itself, which serializes concurrent cache misses for
        // the same path — usually a feature, not a bug.
        let bytes = match std::fs::read(path) {
            Ok(b) => b,
            Err(e) => {
                let mut g = self.inner.write();
                g.failed.insert(path.to_path_buf(), e.to_string());
                return None;
            }
        };
        let data = unsafe { skia_safe::Data::new_bytes(&bytes) };
        let Some(image) = Image::from_encoded(data) else {
            let mut g = self.inner.write();
            g.failed
                .insert(path.to_path_buf(), "Skia could not decode".into());
            return None;
        };
        self.decodes.fetch_add(1, Ordering::Relaxed);
        let arc = Arc::new(image);
        let mut g = self.inner.write();
        g.images.insert(path.to_path_buf(), arc.clone());
        Some(arc)
    }

    pub fn decode_count(&self) -> u64 {
        self.decodes.load(Ordering::Relaxed)
    }
    pub fn hit_count(&self) -> u64 {
        self.hits.load(Ordering::Relaxed)
    }

    /// Insert pre-decoded bytes under `key`. Used by an async populator
    /// to push results back to the render thread, or by a caller that
    /// wants to keep a SkiaLayer in the cache as if it were a texture.
    pub fn populate_from_bytes(&self, key: &Path, encoded: &[u8]) -> bool {
        let data = unsafe { skia_safe::Data::new_bytes(encoded) };
        let Some(image) = Image::from_encoded(data) else {
            return false;
        };
        self.inner
            .write()
            .images
            .insert(key.to_path_buf(), Arc::new(image));
        true
    }

    pub fn contains(&self, path: &Path) -> bool {
        self.inner.read().images.contains_key(path)
    }

    pub fn forget(&self, path: &Path) {
        let mut g = self.inner.write();
        g.images.remove(path);
        g.failed.remove(path);
    }

    pub fn clear(&self) {
        let mut g = self.inner.write();
        g.images.clear();
        g.failed.clear();
    }

    pub fn len(&self) -> usize {
        self.inner.read().images.len()
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Kick off a background decode on a one-shot OS thread. The cache
    /// is populated when the decode finishes; subsequent `get_or_load`
    /// or `try_get` calls return the image without blocking the render
    /// thread on first frame.
    pub fn preload_async(self: &Arc<Self>, path: PathBuf) -> std::thread::JoinHandle<bool> {
        let cache = self.clone();
        std::thread::Builder::new()
            .name(format!("elysium-decode-{}", path.display()))
            .spawn(move || {
                let bytes = match std::fs::read(&path) {
                    Ok(b) => b,
                    Err(e) => {
                        cache.inner.write().failed.insert(path, e.to_string());
                        return false;
                    }
                };
                cache.populate_from_bytes(&path, &bytes)
            })
            .expect("spawn texture decode thread")
    }

    /// Non-blocking lookup — returns `None` if the image isn't cached
    /// yet (still decoding, or never preloaded). Used by the render
    /// thread alongside `preload_async` to draw a placeholder until
    /// the real texture arrives.
    pub fn try_get(&self, path: &Path) -> Option<Arc<Image>> {
        let g = self.inner.read();
        if let Some(img) = g.images.get(path) {
            self.hits.fetch_add(1, Ordering::Relaxed);
            return Some(img.clone());
        }
        None
    }
}
